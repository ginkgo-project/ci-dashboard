"""Puts the results of all CIs together into status.json."""

from datetime import datetime


def assemble(coverage: dict, commits: list[dict], histories: list[dict],
             elsewhere: list[dict], now: datetime) -> dict:
    """histories: key -> sha -> result, per CI; elsewhere: key -> result, per CI."""
    shas = [commit["sha"] for commit in commits]
    history: dict[str, dict[str, dict]] = {}
    for part in histories:
        for key, by_sha in part.items():
            history.setdefault(key, {}).update(by_sha)
    found_elsewhere: dict[str, dict] = {}
    for part in elsewhere:
        found_elsewhere.update(part)
    known = {job["key"] for job in coverage["jobs"]}
    jobs = {key: {"history": [history.get(key, {}).get(sha) for sha in shas],
                  "elsewhere": found_elsewhere.get(key)}
            for key in sorted(known)}
    # skipped results are left out: GitHub records a skipped check run for each
    # caller job whose condition is false, e.g. "arm" of CI-Extra on develop
    newest = shas[0] if shas else None
    unmatched = [{"key": key, "status": by_sha[newest]["status"], "url": by_sha[newest]["url"]}
                 for key, by_sha in sorted(history.items())
                 if key not in known and newest in by_sha
                 and by_sha[newest]["status"] != "skipped"]
    return {"generated_at": now.isoformat(timespec="seconds"), "commits": commits,
            "jobs": jobs, "unmatched": unmatched}
