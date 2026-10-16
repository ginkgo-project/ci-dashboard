"""Ginkgo's line coverage from Codecov, which the coverage job uploads to: the
history of develop, and how many of the lines each open pull request changes
the tests cover. Codecov's API needs no token for a public repository."""

from datetime import datetime, timedelta

from . import github

API = "https://api.codecov.io/api/v2/github"
APP = "https://app.codecov.io/gh"
CHECK = "coverage / coverage of the reference, OpenMP and MPI code"
# develop's older reports are left out
HISTORY = timedelta(days=365)
PAGE_SIZE = 100


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _totals(totals: dict) -> dict:
    return {"coverage": totals["coverage"], "lines": totals["lines"], "hits": totals["hits"],
            "partials": totals["partials"], "misses": totals["misses"], "files": totals["files"]}


class Codecov:
    def __init__(self, fetcher, repo: str):
        owner, name = repo.split("/")
        self.fetcher = fetcher
        self.base = f"{API}/{owner}/repos/{name}"
        self.app = f"{APP}/{repo}"
        self.repo = github.Repo(fetcher, repo)

    def _results(self, path: str, params: dict, stop=lambda item: False) -> list:
        """The items of a paginated Codecov list, up to the first one stop accepts."""
        items: list = []
        page = 1
        while True:
            data = self.fetcher.json(f"{self.base}/{path}",
                                     {**params, "page_size": PAGE_SIZE, "page": page})
            for item in data["results"]:
                if stop(item):
                    return items
                items.append(item)
            if not data.get("next"):
                return items
            page += 1

    def develop_history(self, now: datetime) -> list[dict]:
        """develop's commits with a finished report from the last HISTORY, newest first."""
        since = now - HISTORY
        commits = self._results("commits/", {"branch": "develop"},
                                stop=lambda commit: _time(commit["timestamp"]) < since)
        return [{"sha": commit["commitid"], "date": commit["timestamp"],
                 "title": (commit.get("message") or "").partition("\n")[0],
                 **_totals(commit["totals"]), "url": f"{self.app}/commit/{commit['commitid']}"}
                for commit in commits if commit.get("state") == "complete"
                and (commit.get("totals") or {}).get("coverage") is not None]

    def pulls(self, pulls: list[dict], develop: list[dict]) -> list[dict]:
        """The pull requests with their newest coverage job and Codecov's numbers."""
        reports = {report["pullid"]: report for report in self._results("pulls/", {"state": "open"})}
        with_report = {commit["sha"] for commit in develop}
        return [self.entry(pull, reports.get(pull["number"]), with_report) for pull in pulls]

    def entry(self, pull: dict, report: dict | None, with_report: set[str]) -> dict:
        """codecov is None while Codecov has no report for the pull request.
        Without a report for its base commit, Codecov compares it with an older
        develop commit, and the changed lines include what develop changed since."""
        sha = pull["head"]["sha"]
        run = self.repo.newest_check_run(sha, CHECK)
        numbers = None
        if report and report.get("head_totals"):
            patch = report.get("patch") or {}
            changed = None
            if "hits" in patch:
                changed = {"hits": patch["hits"], "partials": patch["partials"],
                           "misses": patch["misses"]}
                changed["lines"] = sum(changed.values())
            numbers = {"coverage": report["head_totals"]["coverage"],
                       "base_coverage": (report.get("base_totals") or {}).get("coverage"),
                       "changed": changed,
                       "base_has_report": pull["base"]["sha"] in with_report,
                       "updated_at": report.get("updatestamp"),
                       "url": f"{self.app}/pull/{pull['number']}"}
        return {**github.pull_fields(pull),
                "result": github.result(run, sha, f"PR #{pull['number']}") if run else None,
                "codecov": numbers}
