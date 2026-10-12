import pytest

from status.reasons import classify


@pytest.mark.parametrize(
    "status, failure_reason, log, expected",
    [
        ("success", None, None, None),
        ("running", None, None, None),
        ("canceled", None, None, "canceled"),
        ("failed", "stuck_or_timeout_failure", None, "stuck"),
        ("failed", "job_execution_timeout", None, "timeout"),
        ("failed", "runner_system_failure", "No space left on device", "runner"),
        ("failed", "script_failure",
         "The following tests FAILED:\n...\nld: final link failed: No space left on device", "disk"),
        ("failed", "script_failure",
         "slurmstepd: error: *** JOB 42 ON hkn0901 CANCELLED AT 2026-10-01 DUE TO TIME LIMIT ***",
         "slurm-timeout"),
        ("failed", "script_failure", "The following tests FAILED:\n  12 - foo (Failed)", "tests"),
        ("failed", "script_failure", "Errors while running CTest", "tests"),
        ("failed", "script_failure", "error: no member named x\nninja: build stopped: subcommand failed.", "build"),
        ("failed", "script_failure", "something else", "unknown"),
        ("failed", None, None, "unknown"),
    ],
)
def test_classify(status, failure_reason, log, expected):
    assert classify(status, failure_reason, log) == expected
