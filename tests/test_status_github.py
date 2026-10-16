from datetime import datetime, timezone

from status import github
from tests.fakes import FakeFetcher, key

API = "https://api.github.com/repos/o/r"


def run(run_id, name, conclusion, status="completed"):
    return {"id": run_id, "name": name, "status": status, "conclusion": conclusion,
            "started_at": "2026-10-12T08:00:00Z", "completed_at": "2026-10-12T08:20:30Z",
            "html_url": f"https://github.com/o/r/runs/{run_id}"}


def responses():
    push_run = lambda run_id, sha, message: {
        "id": run_id, "head_sha": sha, "created_at": "2026-10-09T21:48:05Z",
        "head_commit": {"id": sha, "message": message, "timestamp": "2026-10-09T21:48:00Z"}}
    return {
        f"{API}/actions/runs?branch=develop&event=push": {"workflow_runs": [
            push_run(12, "aaa", "Merge (#2110): nullspace\n\nbody"),
            push_run(11, "aaa", "Merge (#2110): nullspace\n\nbody"),
            push_run(10, "bbb", "older"),
            push_run(9, "ccc", "oldest"),
        ]},
        f"{API}/commits/aaa/check-runs": {"total_count": 4, "check_runs": [
            run(1, "arm / arm/omp/release/shared-16bit", "failure"),
            run(2, "arm / arm/omp/release/shared-16bit", "success"),
            run(3, "arm / matrix.config.name", "skipped"),
            run(4, "osx / omp/release/static", None, status="in_progress"),
        ]},
        f"{API}/commits/bbb/check-runs": {"total_count": 0, "check_runs": []},
        f"{API}/actions/workflows/ci-extra.yml/runs?status=completed": {"workflow_runs": [
            # a run whose jobs were all skipped (no full-test label); its jobs are not fetched
            {"id": 950, "conclusion": "skipped", "head_sha": "ggg", "head_branch": "feat/z", "pull_requests": []},
            {"id": 900, "head_sha": "eee", "head_branch": "feat/x", "pull_requests": [{"number": 2117}]},
            {"id": 800, "head_sha": "fff", "head_branch": "feat/y", "pull_requests": []},
        ]},
        f"{API}/actions/runs/900/jobs": {"total_count": 2, "jobs": [
            run(91, "arm / arm/omp/debug/shared", "skipped"),
            run(92, "osx / omp/debug/shared", "timed_out"),
        ]},
        f"{API}/actions/runs/800/jobs": {"total_count": 1, "jobs": [
            run(81, "arm / arm/omp/debug/shared", "success"),
        ]},
    }


def test_status_of():
    assert github.status_of("success", "completed") == "success"
    assert github.status_of("failure", "completed") == "failed"
    assert github.status_of("cancelled", "completed") == "canceled"
    assert github.status_of(None, "queued") == "pending"
    assert github.status_of(None, "in_progress") == "running"
    assert github.status_of("startup_failure", "completed") == "failed"


def test_pushed_commits_are_the_heads_of_push_runs_once_each():
    repo = github.Repo(FakeFetcher(responses()), "o/r")
    assert repo.pushed_commits("develop", 2) == [
        {"sha": "aaa", "title": "Merge (#2110): nullspace", "date": "2026-10-09T21:48:00Z"},
        {"sha": "bbb", "title": "older", "date": "2026-10-09T21:48:00Z"},
    ]


def test_develop_history_keeps_the_newest_run_and_drops_unevaluated_names():
    history = github.Repo(FakeFetcher(responses()), "o/r").develop_history(["aaa", "bbb"])
    assert set(history) == {"github:arm / arm/omp/release/shared-16bit",
                            "github:osx / omp/release/static"}
    arm = history["github:arm / arm/omp/release/shared-16bit"]["aaa"]
    assert (arm["status"], arm["duration_s"], arm["url"]) == (
        "success", 1230, "https://github.com/o/r/runs/2")
    assert history["github:osx / omp/release/static"]["aaa"]["status"] == "running"


def test_latest_elsewhere_skips_skipped_jobs():
    found = github.Repo(FakeFetcher(responses()), "o/r").latest_elsewhere(
        {"github:arm / arm/omp/debug/shared", "github:osx / omp/debug/shared"})
    assert (found["github:osx / omp/debug/shared"]["status"],
            found["github:osx / omp/debug/shared"]["reason"],
            found["github:osx / omp/debug/shared"]["ref"]) == ("failed", "timeout", "PR #2117")
    assert (found["github:arm / arm/omp/debug/shared"]["status"],
            found["github:arm / arm/omp/debug/shared"]["ref"]) == ("success", "feat/y")


def test_latest_elsewhere_without_wanted_jobs_makes_no_requests():
    fetcher = FakeFetcher(responses())
    assert github.Repo(fetcher, "o/r").latest_elsewhere(set()) == {}
    assert fetcher.requested == []


def test_open_pulls_leaves_out_the_ones_not_updated_since():
    pulls = [{"number": n, "updated_at": updated} for n, updated in
             [(3, "2026-10-14T19:40:18Z"), (2, "2026-09-01T00:00:00Z"), (1, "2026-06-01T08:00:00Z")]]
    fetcher = FakeFetcher({key(f"{API}/pulls", {"state": "open", "sort": "updated", "direction": "desc"}): pulls})
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert [pull["number"] for pull in github.Repo(fetcher, "o/r").open_pulls(since)] == [3, 2]
