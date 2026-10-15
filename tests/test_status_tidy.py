from datetime import datetime, timezone

from status import tidy
from tests.fakes import FakeFetcher, key

API = "https://api.github.com/repos/o/r"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
WORKSPACE = "/home/runner/work/ginkgo/ginkgo"

LOG = f"""﻿2026-10-15T13:12:44.8623293Z Current runner version: '2.337.0'
2026-10-15T13:20:01.0000000Z {WORKSPACE}/include/ginkgo/core/base/mpi.hpp:444:5: warning: constructor does not initialize these fields: force_host_buffer_ [cppcoreguidelines-pro-type-member-init]
2026-10-15T13:20:01.0000001Z   444 |     communicator(const MPI_Comm& comm, int color, int key)
2026-10-15T13:20:01.0000002Z       |     ^
2026-10-15T13:20:01.0000003Z {WORKSPACE}/core/matrix/csr.cpp:211:9: warning: std::move of the variable 'strategy' has no effect; remove std::move() [performance-move-const-arg]
2026-10-15T13:20:01.0000004Z {WORKSPACE}/core/matrix/csr.cpp:200:5: note: 'strategy' declared here
2026-10-15T13:20:01.0000005Z {WORKSPACE}/include/ginkgo/core/base/mpi.hpp:444:5: warning: constructor does not initialize these fields: force_host_buffer_ [cppcoreguidelines-pro-type-member-init]
2026-10-15T13:20:01.0000006Z {WORKSPACE}/core/base/new.cpp:3:10: error: 'missing.hpp' file not found [clang-diagnostic-error]
2026-10-15T13:20:02.0000000Z ##[warning]constructor does not initialize these fields: force_host_buffer_
2026-10-15T13:20:02.0000001Z 3 clang-tidy finding(s) on changed lines
"""


def test_parse_log_reads_each_finding_once_with_its_path_in_the_repository():
    findings, reported = tidy.parse_log(LOG)
    assert reported == 3
    assert findings == [
        {"path": "include/ginkgo/core/base/mpi.hpp", "line": 444, "col": 5, "severity": "warning",
         "check": "cppcoreguidelines-pro-type-member-init",
         "message": "constructor does not initialize these fields: force_host_buffer_"},
        {"path": "core/matrix/csr.cpp", "line": 211, "col": 9, "severity": "warning",
         "check": "performance-move-const-arg",
         "message": "std::move of the variable 'strategy' has no effect; remove std::move()"},
        {"path": "core/base/new.cpp", "line": 3, "col": 10, "severity": "error",
         "check": "clang-diagnostic-error", "message": "'missing.hpp' file not found"},
    ]


def test_parse_log_without_the_count_line():
    assert tidy.parse_log("2026-10-15T13:12:44.8623293Z Run cmake\n") == ([], None)


def run(run_id, conclusion, completed="2026-10-14T10:20:00Z"):
    return {"id": run_id, "name": tidy.CHECK, "status": "completed", "conclusion": conclusion,
            "started_at": "2026-10-14T10:00:00Z", "completed_at": completed,
            "html_url": f"https://github.com/o/r/actions/runs/1/job/{run_id}"}


def pull(number, sha, updated):
    return {"number": number, "title": f"title {number}", "user": {"login": "dev"},
            "html_url": f"https://github.com/o/r/pull/{number}", "draft": False,
            "updated_at": updated, "head": {"sha": sha}}


def check_runs(sha):
    return key(f"{API}/commits/{sha}/check-runs", {"check_name": tidy.CHECK})


def responses():
    return {
        key(f"{API}/pulls", {"state": "open", "sort": "updated", "direction": "desc"}): [
            pull(2124, "h1", "2026-10-14T19:40:18Z"),
            pull(2120, "h2", "2026-10-10T08:00:00Z"),
            pull(2110, "h3", "2026-10-01T08:00:00Z"),
            pull(2105, "h4", "2026-09-30T08:00:00Z"),
            pull(1900, "old", "2026-06-01T08:00:00Z"),
        ],
        check_runs("h1"): {"check_runs": [run(501, "failure")]},
        f"{API}/actions/jobs/501/logs": LOG,
        check_runs("h2"): {"check_runs": [run(300, "failure"), run(400, "success", "2026-10-14T11:00:00Z")]},
        check_runs("h3"): {"check_runs": []},
        # a log that can't be read: the findings stay unknown
        check_runs("h4"): {"check_runs": [run(600, "failure")]},
    }


def test_collect_reads_the_findings_of_failed_runs_of_recent_pull_requests():
    fetcher = FakeFetcher(responses())
    pulls = tidy.Pulls(fetcher, "o/r").collect(NOW)
    by_number = {pull["number"]: pull for pull in pulls}
    assert list(by_number) == [2124, 2120, 2110, 2105]
    assert check_runs("old") not in fetcher.requested

    failed = by_number[2124]
    assert (failed["title"], failed["author"], failed["sha"]) == ("title 2124", "dev", "h1")
    assert (failed["result"]["status"], failed["result"]["ref"]) == ("failed", "PR #2124")
    assert [finding["check"] for finding in failed["findings"]] == [
        "cppcoreguidelines-pro-type-member-init", "performance-move-const-arg", "clang-diagnostic-error"]
    assert failed["reported"] == 3

    assert (by_number[2120]["result"]["status"], by_number[2120]["findings"]) == ("success", [])
    assert f"{API}/actions/jobs/300/logs" not in fetcher.requested
    assert (by_number[2110]["result"], by_number[2110]["findings"]) == (None, None)
    assert (by_number[2105]["result"]["status"], by_number[2105]["findings"]) == ("failed", None)


def test_newest_result_is_the_last_finished_run():
    pulls = tidy.Pulls(FakeFetcher(responses()), "o/r").collect(NOW)
    newest = tidy.newest_result(pulls)
    assert list(newest) == [tidy.KEY]
    assert (newest[tidy.KEY]["status"], newest[tidy.KEY]["ref"]) == ("success", "PR #2120")
    assert tidy.newest_result([]) == {}
