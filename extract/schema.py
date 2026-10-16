"""Shape checks for coverage.json and status.json, so that a broken file
fails the update instead of reaching the page."""

COVERAGE_FIELDS = {"generated_at": str, "warnings": list, "machines": dict, "columns": list,
                   "supported": dict, "jobs": list}
JOB_FIELDS = {"key": str, "ci": str, "name": str, "kind": str, "pipelines": list,
              "machines": list, "dispatched_to": list, "compile_only": bool, "disabled": bool}
STATUS_FIELDS = {"generated_at": str, "commits": list, "jobs": dict, "unmatched": list,
                 "clang_tidy": dict, "code_coverage": dict}
RESULT_FIELDS = {"status": str, "url": str}
PULL_FIELDS = {"number": int, "title": str, "url": str, "sha": str, "updated_at": str}
FINDING_FIELDS = {"path": str, "line": int, "check": str, "message": str}
REPORT_FIELDS = {"sha": str, "date": str, "coverage": (int, float), "lines": int, "hits": int,
                 "url": str}
CODECOV_FIELDS = {"coverage": (int, float), "base_has_report": bool, "url": str}
CHANGED_FIELDS = {"lines": int, "hits": int, "partials": int, "misses": int}


def _require(obj, fields: dict, where: str) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f"{where}: not an object")
    for name, kind in fields.items():
        if name not in obj:
            raise ValueError(f"{where}: missing {name}")
        if not isinstance(obj[name], kind):
            names = " or ".join(k.__name__ for k in kind) if isinstance(kind, tuple) else kind.__name__
            raise ValueError(f"{where}: {name} should be a {names}")


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


def _check_pull(pull: dict) -> str:
    where = f"pull request {pull.get('number')}"
    _require(pull, PULL_FIELDS, where)
    if pull.get("result"):
        _require(pull["result"], RESULT_FIELDS, where)
    return where


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
    _require(doc["clang_tidy"], {"check": str, "pulls": list}, "clang_tidy")
    for pull in doc["clang_tidy"]["pulls"]:
        where = _check_pull(pull)
        for finding in pull.get("findings") or []:
            _require(finding, FINDING_FIELDS, where)
    _require(doc["code_coverage"], {"check": str, "develop": list, "pulls": list}, "code_coverage")
    for report in doc["code_coverage"]["develop"]:
        _require(report, REPORT_FIELDS, f"report of {report.get('sha')}")
    for pull in doc["code_coverage"]["pulls"]:
        where = _check_pull(pull)
        if pull.get("codecov"):
            _require(pull["codecov"], CODECOV_FIELDS, where)
            if pull["codecov"].get("changed"):
                _require(pull["codecov"]["changed"], CHANGED_FIELDS, where)
