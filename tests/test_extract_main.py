import datetime
import json

from extract.__main__ import build, main
from tests import fake_ginkgo

NOW = datetime.datetime(2026, 10, 12, 8, 0, tzinfo=datetime.timezone.utc)


def test_build_combines_all_cis(tmp_path, config_dir):
    ginkgo = fake_ginkgo.write(tmp_path / "ginkgo")
    doc = build(ginkgo, config_dir, NOW)
    assert doc["generated_at"] == "2026-10-12T08:00:00+00:00"
    assert doc["ginkgo_commit"] is None
    assert "compile-only" in doc["columns"]
    assert doc["machines"]["tum-l40s"]["column"] == "L40S"
    assert doc["supported"]["gcc"] == {"min": "9", "max": "16"}
    by_ci = {}
    for job in doc["jobs"]:
        by_ci[job["ci"]] = by_ci.get(job["ci"], 0) + 1
    assert by_ci == {"gitlab": 8, "cscs": 1, "github": 9}
    assert any("the name says cuda 12.4" in warning for warning in doc["warnings"])
    json.dumps(doc)


def test_main_writes_the_file(tmp_path, config_dir, capsys):
    ginkgo = fake_ginkgo.write(tmp_path / "ginkgo")
    output = tmp_path / "site" / "coverage.json"
    assert main([str(ginkgo), str(output), "--config-dir", str(config_dir)]) == 0
    assert len(json.loads(output.read_text())["jobs"]) == 18
    captured = capsys.readouterr()
    assert "18 jobs written" in captured.out
    assert "warning: gitlab:broken" in captured.err
