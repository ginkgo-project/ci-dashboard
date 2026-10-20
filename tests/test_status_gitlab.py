from status import gitlab
from tests.fakes import FakeFetcher

API = "https://gitlab.com/api/v4/projects/1"


def job(job_id, name, status, runner="ginkgo-cluster-meta-runner-nvidia_rocinante",
        failure_reason=None, duration=600.4):
    return {"id": job_id, "name": name, "status": status, "failure_reason": failure_reason,
            "runner": {"description": runner} if runner else None, "duration": duration,
            "queued_duration": 12.0, "finished_at": "2026-10-12T08:00:00Z",
            "web_url": f"https://gitlab.com/g/p/-/jobs/{job_id}"}


def responses():
    empty = {"test_suites": []}
    return {
        f"{API}/pipelines?ref=develop": [
            {"id": 30, "sha": "aaa", "ref": "develop", "status": "failed"},
            {"id": 29, "sha": "aaa", "ref": "develop", "status": "canceled"},
            {"id": 20, "sha": "bbb", "ref": "develop", "status": "success"},
            {"id": 10, "sha": "old", "ref": "develop", "status": "success"},
        ],
        f"{API}/pipelines/30/jobs": [
            job(301, "build/a", "failed", failure_reason="script_failure"),
            job(302, "build/b", "success"),
            job(303, "build/c", "running", duration=None),
        ],
        f"{API}/pipelines/30/test_report_summary": {"test_suites": [
            {"name": "build/b", "total_count": 10, "failed_count": 1, "error_count": 1}]},
        "https://gitlab.com/g/p/-/jobs/301/raw":
            "ninja: build stopped\nld: final link failed: No space left on device\n",
        f"{API}/pipelines/20/jobs": [
            job(201, "build/a", "failed", runner="ginkgo-cluster-meta-runner-nvidia_l40s",
                failure_reason="script_failure"),
        ],
        f"{API}/pipelines/20/test_report_summary": empty,
        f"{API}/pipelines": [
            {"id": 31, "sha": "ccc", "ref": "__CSCSCI__pr2114", "status": "success"},
            {"id": 30, "sha": "aaa", "ref": "develop", "status": "failed"},
            {"id": 26, "sha": "eee", "ref": "feat/x", "status": "skipped"},
            {"id": 25, "sha": "ddd", "ref": "fix/ci-issues", "status": "failed"},
        ],
        f"{API}/pipelines/31/jobs": [
            job(311, "build/pr-only", "success", runner="Dispatch jobs through firecrest"),
            job(312, "build/a", "success"),
        ],
        f"{API}/pipelines/31/test_report_summary": empty,
        f"{API}/pipelines/25/jobs": [
            job(251, "build/other", "failed", runner=None, failure_reason="stuck_or_timeout_failure"),
        ],
        f"{API}/pipelines/25/test_report_summary": empty,
    }


def test_ref_label():
    assert gitlab.ref_label("__CSCSCI__pr2114") == "PR #2114"
    assert gitlab.ref_label("fix/ci-issues") == "fix/ci-issues"


def test_develop_history_uses_the_newest_pipeline_per_commit(hw):
    fetcher = FakeFetcher(responses())
    history = gitlab.Project(fetcher, 1, "gitlab", hw).develop_history(["aaa", "bbb", "ccc"], 20)
    newest = history["gitlab:build/a"]["aaa"]
    assert newest == {
        "sha": "aaa", "ref": "develop", "status": "failed", "reason": "disk",
        "machine": "tum-rocinante-nvidia", "duration_s": 600, "queued_s": 12,
        "finished_at": "2026-10-12T08:00:00Z", "tests": None,
        "url": "https://gitlab.com/g/p/-/jobs/301",
    }
    older = history["gitlab:build/a"]["bbb"]
    assert (older["machine"], older["status"]) == ("tum-l40s", "failed")
    # the log is only read for the newest commit
    assert older["reason"] == "unknown"
    assert history["gitlab:build/b"]["aaa"]["tests"] == {"total": 10, "failed": 2}
    # a running job is not a failure; a commit without a pipeline has no entry
    assert history["gitlab:build/c"]["aaa"]["status"] == "running"
    assert history["gitlab:build/c"]["aaa"]["reason"] is None
    assert "ccc" not in history["gitlab:build/a"]
    assert f"{API}/pipelines/29/jobs" not in fetcher.requested


def test_develop_history_skips_the_empty_twin_of_a_cscs_pipeline(hw):
    fetcher = FakeFetcher({
        f"{API}/pipelines?ref=develop": [
            {"id": 41, "sha": "aaa", "ref": "develop", "status": "skipped"},
            {"id": 40, "sha": "aaa", "ref": "develop", "status": "success"},
            {"id": 39, "sha": "bbb", "ref": "develop", "status": "skipped"},
        ],
        f"{API}/pipelines/40/jobs": [job(401, "beverin/x", "success", runner=None)],
        f"{API}/pipelines/40/test_report_summary": {"test_suites": []},
        f"{API}/pipelines/39/jobs": [],
        f"{API}/pipelines/39/test_report_summary": {"test_suites": []},
    })
    history = gitlab.Project(fetcher, 1, "cscs", hw).develop_history(["aaa", "bbb"], 20)
    assert list(history) == ["cscs:beverin/x"]
    assert list(history["cscs:beverin/x"]) == ["aaa"]
    assert history["cscs:beverin/x"]["aaa"]["status"] == "success"
    assert f"{API}/pipelines/41/jobs" not in fetcher.requested


def test_latest_elsewhere_skips_develop_and_skipped_pipelines(hw):
    fetcher = FakeFetcher(responses())
    found = gitlab.Project(fetcher, 1, "gitlab", hw).latest_elsewhere(
        {"gitlab:build/pr-only", "gitlab:build/other"}, 50)
    assert found["gitlab:build/pr-only"]["ref"] == "PR #2114"
    assert found["gitlab:build/pr-only"]["machine"] is None
    assert found["gitlab:build/other"]["reason"] == "stuck"
    assert found["gitlab:build/other"]["ref"] == "fix/ci-issues"
    assert f"{API}/pipelines/30/jobs" not in fetcher.requested
    assert f"{API}/pipelines/26/jobs" not in fetcher.requested


def test_latest_elsewhere_stops_when_everything_is_found(hw):
    fetcher = FakeFetcher(responses())
    project = gitlab.Project(fetcher, 1, "gitlab", hw)
    assert set(project.latest_elsewhere({"gitlab:build/pr-only"}, 50)) == {"gitlab:build/pr-only"}
    assert f"{API}/pipelines/25/jobs" not in fetcher.requested
    assert project.latest_elsewhere(set(), 50) == {}


def test_missing_test_report_is_not_an_error(hw):
    data = responses()
    del data[f"{API}/pipelines/20/test_report_summary"]
    history = gitlab.Project(FakeFetcher(data), 1, "gitlab", hw).develop_history(["bbb"], 20)
    assert history["gitlab:build/a"]["bbb"]["tests"] is None
