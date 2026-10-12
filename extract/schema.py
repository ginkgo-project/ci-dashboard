"""Shape checks for coverage.json and status.json, so that a broken file
fails the update instead of reaching the page."""

COVERAGE_FIELDS = {"generated_at": str, "warnings": list, "machines": dict, "columns": list,
                   "supported": dict, "jobs": list}
JOB_FIELDS = {"key": str, "ci": str, "name": str, "kind": str, "pipelines": list,
              "machines": list, "dispatched_to": list, "compile_only": bool, "disabled": bool}
STATUS_FIELDS = {"generated_at": str, "commits": list, "jobs": dict, "unmatched": list}
RESULT_FIELDS = {"status": str, "url": str}


def _require(obj, fields: dict, where: str) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f"{where}: not an object")
    for name, kind in fields.items():
        if name not in obj:
            raise ValueError(f"{where}: missing {name}")
        if not isinstance(obj[name], kind):
            raise ValueError(f"{where}: {name} should be a {kind.__name__}")


def check_coverage(doc: dict) -> None:
    _require(doc, COVERAGE_FIELDS, "coverage")
    keys = set()
    for job in doc["jobs"]:
        _require(job, JOB_FIELDS, f"job {job.get('key')}")
        if job["key"] in keys:
            raise ValueError(f"duplicate job key {job['key']}")
        keys.add(job["key"])
        if job["kind"] == "build" and job.get("build_type") is None:
            raise ValueError(f"build job {job['key']} has no build_type")
        for machine in job["machines"] + job["dispatched_to"]:
            if machine not in doc["machines"]:
                raise ValueError(f"job {job['key']}: unknown machine {machine}")


def check_status(doc: dict) -> None:
    _require(doc, STATUS_FIELDS, "status")
    commits = len(doc["commits"])
    for key, entry in doc["jobs"].items():
        _require(entry, {"history": list}, key)
        if len(entry["history"]) != commits:
            raise ValueError(f"{key}: history has {len(entry['history'])} entries "
                             f"for {commits} commits")
        results = [result for result in entry["history"] if result]
        if entry.get("elsewhere"):
            results.append(entry["elsewhere"])
        for result in results:
            _require(result, RESULT_FIELDS, key)
