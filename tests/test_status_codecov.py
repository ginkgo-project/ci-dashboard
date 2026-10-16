from datetime import datetime, timezone

from status import codecov
from tests.fakes import FakeFetcher, key

API = "https://api.codecov.io/api/v2/github/o/repos/r"
GITHUB = "https://api.github.com/repos/o/r"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def totals(coverage, lines=100, hits=90):
    return {"files": 5, "lines": lines, "hits": hits, "misses": lines - hits, "partials": 0,
            "coverage": coverage}


def commit(sha, timestamp, state="complete", coverage=90.0):
    return {"commitid": sha, "timestamp": timestamp, "state": state,
            "message": f"title {sha}\n\nbody", "totals": totals(coverage) if coverage else None}


def report(number, patch, head=92.5, base=88.48):
    return {"pullid": number, "state": "open", "updatestamp": "2026-10-16T21:16:41Z",
            "head_totals": totals(head) if head else None,
            "base_totals": totals(base) if base else None, "patch": patch}


def pull(number, sha, base):
    return {"number": number, "title": f"title {number}", "user": {"login": "dev"},
            "html_url": f"https://github.com/o/r/pull/{number}", "draft": False,
            "updated_at": "2026-10-16T20:00:00Z", "head": {"sha": sha}, "base": {"sha": base}}


def check_runs(sha):
    return key(f"{GITHUB}/commits/{sha}/check-runs", {"check_name": codecov.CHECK})


def run(run_id, conclusion, status="completed"):
    return {"id": run_id, "name": codecov.CHECK, "status": status, "conclusion": conclusion,
            "started_at": "2026-10-16T20:00:00Z", "completed_at": "2026-10-16T21:16:00Z",
            "html_url": f"https://github.com/o/r/actions/runs/1/job/{run_id}"}


def responses():
    return {
        key(f"{API}/commits/", {"branch": "develop"}): {"next": "page 2", "results": [
            commit("d3", "2026-10-16T09:00:00Z", coverage=92.67),
            # an upload that is still being processed
            commit("d2", "2026-10-15T09:00:00Z", state="pending", coverage=None),
            commit("d1", "2026-10-06T15:51:46Z", coverage=88.48),
            commit("d0", "2025-10-01T00:00:00Z"),
        ]},
        key(f"{API}/pulls/", {"state": "open"}): {"next": None, "results": [
            report(2126, {"hits": 930, "misses": 108, "partials": 0, "coverage": 89.6}),
            report(2125, {}, head=None, base=None),
            report(2124, {"hits": 10, "misses": 0, "partials": 0, "coverage": 100.0}),
        ]},
        check_runs("h6"): {"check_runs": [run(1, "success")]},
        check_runs("h5"): {"check_runs": [run(2, None, status="in_progress")]},
        check_runs("h4"): {"check_runs": []},
        check_runs("h3"): {"check_runs": []},
    }


def test_develop_history_keeps_the_finished_reports_of_the_last_year():
    fetcher = FakeFetcher(responses())
    history = codecov.Codecov(fetcher, "o/r").develop_history(NOW)
    assert [(commit["sha"], commit["coverage"]) for commit in history] == [("d3", 92.67), ("d1", 88.48)]
    assert history[0] == {"sha": "d3", "date": "2026-10-16T09:00:00Z", "title": "title d3",
                          "coverage": 92.67, "lines": 100, "hits": 90, "partials": 0, "misses": 10,
                          "files": 5, "url": "https://app.codecov.io/gh/o/r/commit/d3"}


def test_pulls_have_their_coverage_job_and_the_changed_lines_codecov_counted():
    fetcher = FakeFetcher(responses())
    lines = codecov.Codecov(fetcher, "o/r")
    develop = lines.develop_history(NOW)
    pulls = lines.pulls([pull(2126, "h6", "d3"), pull(2125, "h5", "d3"), pull(2124, "h4", "elsewhere"),
                         pull(2100, "h3", "d3")], develop)
    by_number = {pull["number"]: pull for pull in pulls}

    covered = by_number[2126]
    assert (covered["title"], covered["sha"], covered["result"]["status"]) == ("title 2126", "h6", "success")
    assert covered["codecov"] == {
        "coverage": 92.5, "base_coverage": 88.48, "base_has_report": True,
        "changed": {"hits": 930, "partials": 0, "misses": 108, "lines": 1038},
        "updated_at": "2026-10-16T21:16:41Z", "url": "https://app.codecov.io/gh/o/r/pull/2126"}
    # Codecov knows the pull request but has no report for it yet
    assert (by_number[2125]["result"]["status"], by_number[2125]["codecov"]) == ("running", None)
    # compared with an older develop commit than its base
    assert by_number[2124]["codecov"]["base_has_report"] is False
    # no coverage run and unknown to Codecov
    assert (by_number[2100]["result"], by_number[2100]["codecov"]) == (None, None)
