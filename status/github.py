"""Results of the GitHub Actions jobs of ginkgo-project/ginkgo."""

from datetime import datetime

from .fetch import paged

API = "https://api.github.com"

CONCLUSIONS = {
    "success": "success", "neutral": "success",
    "failure": "failed", "timed_out": "failed", "startup_failure": "failed",
    "cancelled": "canceled", "stale": "canceled",
    "skipped": "skipped", "action_required": "manual",
}
STATES = {"queued": "pending", "waiting": "pending", "pending": "pending",
          "requested": "pending", "in_progress": "running"}


def status_of(conclusion: str | None, state: str) -> str:
    if conclusion is None:
        return STATES.get(state, "running")
    return CONCLUSIONS.get(conclusion, "failed")


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def result(run: dict, sha: str, ref: str) -> dict:
    """A check run or workflow job as a result."""
    status = status_of(run.get("conclusion"), run.get("status", ""))
    start, end = _time(run.get("started_at")), _time(run.get("completed_at"))
    reason = None
    if run.get("conclusion") == "timed_out":
        reason = "timeout"
    elif status == "canceled":
        reason = "canceled"
    return {
        "sha": sha, "ref": ref, "status": status, "reason": reason, "machine": None,
        "duration_s": round((end - start).total_seconds()) if start and end else None,
        "queued_s": None, "finished_at": run.get("completed_at"), "tests": None,
        "url": run["html_url"],
    }


class Repo:
    def __init__(self, fetcher, repo: str):
        self.fetcher = fetcher
        self.base = f"{API}/repos/{repo}"

    def pushed_commits(self, branch: str, count: int) -> list[dict]:
        """The commits pushed to branch, newest first: the head commits of the
        push runs of all workflows. CI runs once per push, so a merge that
        brings several commits counts once, and every entry has results.
        Several workflows run per push, hence 100 runs for count pushes."""
        runs = self.fetcher.json(f"{self.base}/actions/runs",
                                 {"branch": branch, "event": "push",
                                  "per_page": 100})["workflow_runs"]
        commits: list[dict] = []
        for run in runs:
            if any(commit["sha"] == run["head_sha"] for commit in commits):
                continue
            head = run.get("head_commit") or {}
            message = head.get("message") or ""
            commits.append({"sha": run["head_sha"],
                            "title": message.splitlines()[0] if message else "",
                            "date": head.get("timestamp") or run.get("created_at")})
            if len(commits) == count:
                break
        return commits

    def check_runs(self, sha: str) -> dict[str, dict]:
        """The newest check run of each name. Skipped jobs whose name GitHub
        never evaluated (arm / matrix.config.name) are left out."""
        newest: dict[str, dict] = {}
        for run in paged(self.fetcher, f"{self.base}/commits/{sha}/check-runs", key="check_runs"):
            if "matrix." in run["name"]:
                continue
            key = f"github:{run['name']}"
            if key not in newest or run["id"] > newest[key]["id"]:
                newest[key] = run
        return newest

    def develop_history(self, shas: list[str]) -> dict[str, dict[str, dict]]:
        history: dict[str, dict[str, dict]] = {}
        for sha in shas:
            for key, run in self.check_runs(sha).items():
                history.setdefault(key, {})[sha] = result(run, sha, "develop")
        return history

    def latest_elsewhere(self, wanted: set[str], workflow: str = "ci-extra.yml",
                         count: int = 100) -> dict[str, dict]:
        """The newest result of each wanted job from completed runs of workflow.
        Most CI-Extra runs are skipped as a whole (no full-test label); their
        jobs are not fetched, and the window is wide enough to reach the
        labelled pull requests."""
        found: dict[str, dict] = {}
        if not wanted:
            return found
        runs = self.fetcher.json(f"{self.base}/actions/workflows/{workflow}/runs",
                                 {"per_page": count, "status": "completed"})["workflow_runs"]
        for run in runs:
            if not wanted - found.keys():
                break
            if run.get("conclusion") == "skipped":
                continue
            pulls = run.get("pull_requests") or []
            ref = f"PR #{pulls[0]['number']}" if pulls else run.get("head_branch")
            for job in paged(self.fetcher, f"{self.base}/actions/runs/{run['id']}/jobs", key="jobs"):
                key = f"github:{job['name']}"
                job_result = result(job, run["head_sha"], ref)
                if key in wanted and key not in found and job_result["status"] != "skipped":
                    found[key] = job_result
        return found
