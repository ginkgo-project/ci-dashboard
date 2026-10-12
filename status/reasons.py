"""Why a job failed: from GitLab's failure_reason, then from the end of its log."""

import re

# failure_reason values that already say what happened
RECORD_REASONS = {
    "stuck_or_timeout_failure": "stuck",
    "job_execution_timeout": "timeout",
    "runner_system_failure": "runner",
    "runner_unsupported": "runner",
    "scheduler_failure": "runner",
    "api_failure": "runner",
    "data_integrity_failure": "runner",
}

# checked in order: a full disk often also makes tests fail, so it comes first
LOG_REASONS = [
    ("disk", re.compile(r"No space left on device")),
    ("slurm-timeout", re.compile(r"CANCELLED .* DUE TO TIME LIMIT")),
    ("tests", re.compile(r"The following tests FAILED|Errors while running CTest")),
    ("build", re.compile(r"ninja: build stopped|make(\[\d+\])?: \*\*\*")),
]


def classify(status: str, failure_reason: str | None, log: str | None) -> str | None:
    """A short reason for a failed or canceled job; None if it didn't fail."""
    if status == "canceled":
        return "canceled"
    if status != "failed":
        return None
    if failure_reason in RECORD_REASONS:
        return RECORD_REASONS[failure_reason]
    for reason, pattern in LOG_REASONS:
        if log and pattern.search(log):
            return reason
    return "unknown"
