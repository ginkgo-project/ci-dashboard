"""clang-tidy findings of Ginkgo's open pull requests. The clang-tidy job checks
the lines a pull request changes; its findings are read from the job's log."""

import re
from datetime import datetime, timedelta

from . import github
from .fetch import FetchError, paged

CHECK = "clang-tidy / clang-tidy on changed lines"
KEY = f"github:{CHECK}"
# older pull requests are left out
MAX_AGE = timedelta(days=60)

_TIMESTAMP = re.compile(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ")
_FINDING = re.compile(r"^(.+?):(\d+):(\d+): (warning|error): (.*) \[([^\]]+)\]$")
# the job's last line; a log cut short has fewer findings than this
_REPORTED = re.compile(r"^(\d+) clang-tidy finding\(s\) on changed lines$")
# the checkout of a GitHub-hosted runner
_WORKSPACE = re.compile(r"^/home/runner/work/[^/]+/[^/]+/")


def parse_log(log: str) -> tuple[list[dict], int | None]:
    """The findings in a clang-tidy job log, each once, and the count the job reported."""
    findings: list[dict] = []
    seen = set()
    reported = None
    for line in log.splitlines():
        line = _TIMESTAMP.sub("", line).rstrip()
        count = _REPORTED.match(line)
        if count:
            reported = int(count.group(1))
            continue
        match = _FINDING.match(line)
        if not match or match.groups() in seen:
            continue
        seen.add(match.groups())
        path, row, col, severity, message, check = match.groups()
        findings.append({"path": _WORKSPACE.sub("", path), "line": int(row), "col": int(col),
                         "severity": severity, "check": check, "message": message})
    return findings, reported


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Pulls:
    def __init__(self, fetcher, repo: str):
        self.fetcher = fetcher
        self.base = f"{github.API}/repos/{repo}"

    def collect(self, now: datetime) -> list[dict]:
        """The open pull requests updated within MAX_AGE, newest first, with
        their latest clang-tidy result and its findings."""
        pulls = paged(self.fetcher, f"{self.base}/pulls",
                      {"state": "open", "sort": "updated", "direction": "desc"})
        return [self.entry(pull) for pull in pulls if now - _time(pull["updated_at"]) <= MAX_AGE]

    def entry(self, pull: dict) -> dict:
        """findings is None when they are unknown: no finished run, or an
        unreadable log."""
        sha = pull["head"]["sha"]
        runs = self.fetcher.json(f"{self.base}/commits/{sha}/check-runs",
                                 {"check_name": CHECK})["check_runs"]
        run = max(runs, key=lambda run: run["id"], default=None)
        result = github.result(run, sha, f"PR #{pull['number']}") if run else None
        findings, reported = None, None
        if result and result["status"] == "success":
            findings = []
        elif run and run.get("conclusion") == "failure":
            try:
                findings, reported = parse_log(
                    self.fetcher.text(f"{self.base}/actions/jobs/{run['id']}/logs"))
            except FetchError:
                pass
        return {"number": pull["number"], "title": pull["title"],
                "author": (pull.get("user") or {}).get("login"), "url": pull["html_url"],
                "draft": bool(pull.get("draft")), "updated_at": pull["updated_at"], "sha": sha,
                "result": result, "findings": findings, "reported": reported}


def newest_result(pulls: list[dict]) -> dict[str, dict]:
    """The newest finished clang-tidy result, for the job's row on the status page."""
    finished = [pull["result"] for pull in pulls
                if pull["result"] and pull["result"]["finished_at"]
                and pull["result"]["status"] != "skipped"]
    return {KEY: max(finished, key=lambda result: result["finished_at"])} if finished else {}
