"""Runs the extractor on a real Ginkgo checkout: GINKGO_DIR=/path/to/ginkgo pytest -s"""

import datetime
import os
from pathlib import Path

import pytest

from extract.__main__ import build

GINKGO = os.environ.get("GINKGO_DIR")
ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not GINKGO, reason="set GINKGO_DIR to a Ginkgo checkout")
def test_real_ginkgo():
    doc = build(Path(GINKGO), ROOT, datetime.datetime.now(datetime.timezone.utc))
    jobs = {job["key"]: job for job in doc["jobs"]}
    builds = [job for job in doc["jobs"] if job["kind"] == "build" and not job["disabled"]]
    print(f"\n{len(doc['jobs'])} jobs, {len(builds)} enabled builds")
    for warning in doc["warnings"]:
        print("warning:", warning)
    assert len([job for job in builds if job["ci"] == "gitlab"]) >= 15
    assert any(job["ci"] == "cscs" for job in builds)
    assert len([job for job in builds if job["ci"] == "github"]) >= 6
    cpu = jobs["gitlab:build/nocuda/nompi/gcc/omp/release/shared"]
    assert cpu["compiler"] == {"name": "gcc", "version": "9"}
    assert cpu["omp"] is True
    assert cpu["dispatched_to"] == ["tum-cpu"]
    nvidia = jobs["gitlab:build/cuda126/nompi/gcc/cuda/release/shared"]
    assert nvidia["dispatched_to"] == ["tum-rocinante-nvidia"]
    assert set(nvidia["machines"]) == {"tum-l40s", "tum-rocinante-nvidia"}
