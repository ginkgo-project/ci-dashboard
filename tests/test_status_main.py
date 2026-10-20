import datetime
import json

from status import codecov, merge, tidy
from status.__main__ import PROJECTS, collect, main
from tests.fakes import FakeFetcher, key as request_key

NOW = datetime.datetime(2026, 10, 12, 8, 0, tzinfo=datetime.timezone.utc)
GITLAB = f"https://gitlab.com/api/v4/projects/{PROJECTS['gitlab']}"
CSCS = f"https://gitlab.com/api/v4/projects/{PROJECTS['cscs']}"
GITHUB = "https://api.github.com/repos/ginkgo-project/ginkgo"
CODECOV = "https://api.codecov.io/api/v2/github/ginkgo-project/repos/ginkgo"


def r(status, sha="aaa"):
    return {"sha": sha, "status": status, "url": f"https://x/{status}/{sha}"}


def coverage_job(key, pipelines):
    return {"key": key, "ci": key.split(":")[0], "pipelines": pipelines, "disabled": False}


COVERAGE = {"jobs": [
    coverage_job("gitlab:build/a", ["develop", "pr-full"]),
    coverage_job("cscs:daint/x", ["pr-cscs"]),
    coverage_job("cscs:beverin/2-nodes", ["develop"]),
    coverage_job("github:arm / a", ["develop", "pr-quick"]),
    coverage_job(tidy.KEY, ["pr-quick"]),
]}


def test_assemble_aligns_history_with_commits_and_lists_unmatched_jobs():
    commits = [{"sha": "aaa"}, {"sha": "bbb"}]
    histories = [{"gitlab:build/a": {"aaa": r("failed"), "bbb": r("success", "bbb")},
                  "gitlab:gone": {"aaa": r("success")},
                  "github:arm": {"aaa": r("skipped")}},
                 {"github:arm / a": {"bbb": r("success", "bbb")}}]
    doc = merge.assemble(COVERAGE, commits, histories, [{"cscs:daint/x": r("success", "zzz")}], NOW)
    assert doc["generated_at"] == "2026-10-12T08:00:00+00:00"
    assert doc["jobs"]["gitlab:build/a"] == {"history": [r("failed"), r("success", "bbb")],
                                             "elsewhere": None}
    assert doc["jobs"]["github:arm / a"]["history"] == [None, r("success", "bbb")]
    assert doc["jobs"]["cscs:daint/x"] == {"history": [None, None], "elsewhere": r("success", "zzz")}
    assert doc["unmatched"] == [{"key": "gitlab:gone", "status": "success",
                                 "url": "https://x/success/aaa"}]


def gitlab_job(job_id, name, status):
    return {"id": job_id, "name": name, "status": status, "failure_reason": None,
            "runner": None, "duration": 60, "queued_duration": 1, "finished_at": None,
            "web_url": f"https://gitlab.com/j/{job_id}"}


def responses():
    return {
        f"{GITHUB}/actions/runs?branch=develop&event=push": {"workflow_runs": [{
            "id": 3, "head_sha": "aaa", "created_at": "2026-10-12T07:00:05Z",
            "head_commit": {"id": "aaa", "message": "newest", "timestamp": "2026-10-12T07:00:00Z"}}]},
        f"{GITHUB}/commits/aaa/check-runs": {"check_runs": [{
            "id": 1, "name": "arm / a", "status": "completed", "conclusion": "success",
            "started_at": None, "completed_at": None, "html_url": "https://github.com/r/1"}]},
        f"{GITLAB}/pipelines?ref=develop": [{"id": 5, "sha": "aaa", "ref": "develop", "status": "success"}],
        f"{GITLAB}/pipelines/5/jobs": [gitlab_job(51, "build/a", "success")],
        f"{GITLAB}/pipelines/5/test_report_summary": {"test_suites": []},
        f"{CSCS}/pipelines?ref=develop": [{"id": 9, "sha": "aaa", "ref": "develop", "status": "skipped"},
                                          {"id": 8, "sha": "aaa", "ref": "develop", "status": "success"}],
        f"{CSCS}/pipelines/8/jobs": [gitlab_job(81, "beverin/2-nodes", "success")],
        f"{CSCS}/pipelines/8/test_report_summary": {"test_suites": []},
        f"{CSCS}/pipelines": [{"id": 7, "sha": "ccc", "ref": "__CSCSCI__pr2114", "status": "success"}],
        f"{CSCS}/pipelines/7/jobs": [gitlab_job(71, "daint/x", "success")],
        f"{CSCS}/pipelines/7/test_report_summary": {"test_suites": []},
        request_key(f"{GITHUB}/pulls", {"state": "open", "sort": "updated", "direction": "desc"}): [{
            "number": 2124, "title": "t", "user": {"login": "dev"}, "draft": False,
            "html_url": "https://github.com/ginkgo-project/ginkgo/pull/2124",
            "updated_at": "2026-10-12T07:30:00Z", "head": {"sha": "ppp"}, "base": {"sha": "aaa"}}],
        request_key(f"{GITHUB}/commits/ppp/check-runs", {"check_name": tidy.CHECK}): {"check_runs": [{
            "id": 9, "name": tidy.CHECK, "status": "completed", "conclusion": "success",
            "started_at": "2026-10-12T07:30:00Z", "completed_at": "2026-10-12T07:40:00Z",
            "html_url": "https://github.com/r/9"}]},
        request_key(f"{GITHUB}/commits/ppp/check-runs", {"check_name": codecov.CHECK}): {"check_runs": []},
        request_key(f"{CODECOV}/commits/", {"branch": "develop"}): {"next": None, "results": [{
            "commitid": "aaa", "timestamp": "2026-10-12T07:00:00Z", "state": "complete", "message": "newest",
            "totals": {"files": 5, "lines": 100, "hits": 93, "misses": 7, "partials": 0, "coverage": 93.0}}]},
        request_key(f"{CODECOV}/pulls/", {"state": "open"}): {"next": None, "results": []},
    }


def test_collect(hw):
    doc = collect(COVERAGE, FakeFetcher(responses()), hw, NOW)
    assert doc["commits"] == [{"sha": "aaa", "title": "newest", "date": "2026-10-12T07:00:00Z"}]
    assert doc["jobs"]["gitlab:build/a"]["history"][0]["status"] == "success"
    assert doc["jobs"]["github:arm / a"]["history"][0]["status"] == "success"
    assert doc["jobs"]["cscs:daint/x"]["elsewhere"]["ref"] == "PR #2114"
    assert doc["jobs"]["cscs:beverin/2-nodes"]["history"][0]["status"] == "success"
    # from the pull requests, without searching CI-Extra for it
    assert doc["jobs"][tidy.KEY]["elsewhere"]["ref"] == "PR #2124"
    assert [(pull["number"], pull["findings"]) for pull in doc["clang_tidy"]["pulls"]] == [(2124, [])]
    assert [(commit["sha"], commit["coverage"]) for commit in doc["code_coverage"]["develop"]] == [("aaa", 93.0)]
    assert [(pull["number"], pull["result"], pull["codecov"]) for pull in doc["code_coverage"]["pulls"]] == [
        (2124, None, None)]
    assert doc["unmatched"] == []


def test_main_writes_the_file(tmp_path, config_dir):
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps(COVERAGE))
    output = tmp_path / "status.json"
    code = main([str(coverage), str(output), "--config-dir", str(config_dir)],
                fetcher=FakeFetcher(responses()))
    assert code == 0
    assert set(json.loads(output.read_text())["jobs"]) == {"gitlab:build/a", "cscs:daint/x",
                                                            "cscs:beverin/2-nodes",
                                                            "github:arm / a", tidy.KEY}


def test_main_fails_without_writing_when_an_api_fails(tmp_path, config_dir, capsys):
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps(COVERAGE))
    output = tmp_path / "status.json"
    data = responses()
    del data[f"{GITLAB}/pipelines?ref=develop"]
    code = main([str(coverage), str(output), "--config-dir", str(config_dir)],
                fetcher=FakeFetcher(data))
    assert code == 1
    assert not output.exists()
    assert "error:" in capsys.readouterr().err
