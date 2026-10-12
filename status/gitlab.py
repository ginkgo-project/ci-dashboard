"""Results of GitLab CI jobs on gitlab.com: the TUM, HoreKa and private-runner
jobs in ginkgo-public-ci, and the CSCS jobs in CSCS's public mirror project."""

import re

from . import reasons
from .fetch import FetchError, paged

API = "https://gitlab.com/api/v4"
LOG_TAIL = 200_000   # characters of a log searched for the failure reason
_CSCS_PR = re.compile(r"__CSCSCI__pr(\d+)$")


def ref_label(ref: str) -> str:
    match = _CSCS_PR.search(ref or "")
    return f"PR #{match.group(1)}" if match else ref


def _seconds(value) -> int | None:
    return round(value) if value else None


def result(job: dict, pipeline: dict, tests: dict | None, machine: str | None,
           reason: str | None) -> dict:
    return {
        "sha": pipeline["sha"],
        "ref": ref_label(pipeline["ref"]),
        "status": job["status"],
        "reason": reason,
        "machine": machine,
        "duration_s": _seconds(job.get("duration")),
        "queued_s": _seconds(job.get("queued_duration")),
        "finished_at": job.get("finished_at"),
        "tests": tests,
        "url": job["web_url"],
    }


class Project:
    def __init__(self, fetcher, project_id: int, ci: str, hardware):
        self.fetcher = fetcher
        self.base = f"{API}/projects/{project_id}"
        self.ci = ci
        self.hardware = hardware

    def pipelines(self, ref: str | None, count: int) -> list[dict]:
        """The newest pipelines, newest first."""
        params = {"ref": ref} if ref else {}
        return paged(self.fetcher, f"{self.base}/pipelines", params, per_page=count, limit=count)

    def tests(self, pipeline_id: int) -> dict[str, dict]:
        try:
            summary = self.fetcher.json(f"{self.base}/pipelines/{pipeline_id}/test_report_summary")
        except FetchError:
            return {}
        return {suite["name"]: {"total": suite["total_count"],
                                "failed": suite["failed_count"] + suite["error_count"]}
                for suite in summary.get("test_suites", [])}

    def reason(self, job: dict, read_log: bool) -> str | None:
        log = None
        if (read_log and job["status"] == "failed"
                and job.get("failure_reason") in (None, "script_failure", "unknown_failure")):
            try:
                log = self.fetcher.text(job["web_url"] + "/raw")[-LOG_TAIL:]
            except FetchError:
                log = None
        return reasons.classify(job["status"], job.get("failure_reason"), log)

    def results_of(self, pipeline: dict, read_logs: bool) -> dict[str, dict]:
        tests = self.tests(pipeline["id"])
        results = {}
        for job in paged(self.fetcher, f"{self.base}/pipelines/{pipeline['id']}/jobs"):
            machine = self.hardware.machine_of_runner((job.get("runner") or {}).get("description"))
            results[f"{self.ci}:{job['name']}"] = result(
                job, pipeline, tests.get(job["name"]), machine, self.reason(job, read_logs))
        return results

    def develop_history(self, shas: list[str], count: int) -> dict[str, dict[str, dict]]:
        """key -> sha -> result, from the newest develop pipeline of each commit.
        Logs are read for the newest commit only."""
        newest: dict[str, dict] = {}
        for pipeline in self.pipelines("develop", count):
            sha = pipeline["sha"]
            if sha in shas and (sha not in newest or pipeline["id"] > newest[sha]["id"]):
                newest[sha] = pipeline
        history: dict[str, dict[str, dict]] = {}
        for sha, pipeline in newest.items():
            for key, job_result in self.results_of(pipeline, read_logs=sha == shas[0]).items():
                history.setdefault(key, {})[sha] = job_result
        return history

    def latest_elsewhere(self, wanted: set[str], count: int) -> dict[str, dict]:
        """The newest result of each wanted job from pipelines not on develop."""
        found: dict[str, dict] = {}
        if not wanted:
            return found
        for pipeline in self.pipelines(None, count):
            if not wanted - found.keys():
                break
            if pipeline["ref"] == "develop" or pipeline["status"] in ("skipped", "created"):
                continue
            for key, job_result in self.results_of(pipeline, read_logs=False).items():
                if (key in wanted and key not in found
                        and job_result["status"] not in ("skipped", "manual", "created")):
                    found[key] = job_result
        return found
