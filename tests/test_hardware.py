from pathlib import Path

import pytest

from extract import hardware, toolchain

ROOT = Path(__file__).resolve().parent.parent


def test_machines_for_tags_picks_the_runners_with_fewest_tags(hw):
    assert hw.machines_for_tags(["nvidia-gpus", "tum"]) == (
        ["tum-l40s", "tum-rocinante-nvidia"],
        ["tum-rocinante-nvidia"],
    )
    assert hw.machines_for_tags(["cpu", "tum"]) == (["tum-cpu"], ["tum-cpu"])


def test_machines_for_tags_without_tags_or_runner(hw):
    assert hw.machines_for_tags([]) == ([], [])
    assert hw.machines_for_tags(["amd-gpus"]) == ([], [])


def test_machine_of_runner_and_site(hw):
    assert hw.machine_of_runner("ginkgo-cluster-meta-runner-cpu") == "tum-cpu"
    assert hw.machine_of_runner("Dispatch jobs through firecrest") is None
    assert hw.machine_of_runner(None) is None
    assert hw.site_of(["tum-l40s"]) == "TUM"
    assert hw.site_of(["status-runner"]) is None
    assert hw.site_of([]) is None


def test_load_rejects_unknown_machines(tmp_path):
    path = tmp_path / "hardware.yml"
    path.write_text(
        "columns: [x86-64, compile-only]\n"
        "machines:\n  a: {column: x86-64}\n"
        "gitlab_runners:\n  r: {tags: [t], machine: b}\n"
    )
    with pytest.raises(ValueError, match="unknown machine b"):
        hardware.load(path)


def test_load_rejects_columns_missing_from_the_list(tmp_path):
    path = tmp_path / "hardware.yml"
    path.write_text("columns: [x86-64, compile-only]\nmachines:\n  a: {column: GPU}\n")
    with pytest.raises(ValueError, match="column GPU"):
        hardware.load(path)


def test_load_requires_the_compile_only_column(tmp_path):
    path = tmp_path / "hardware.yml"
    path.write_text("columns: [x86-64]\nmachines:\n  a: {column: x86-64}\n")
    with pytest.raises(ValueError, match="compile-only"):
        hardware.load(path)


def test_repository_data_files_are_valid():
    hw = hardware.load(ROOT / "hardware.yml")
    toolchain.load_environments(ROOT / "environments.yml")
    toolchain.load_supported(ROOT / "supported.yml")
    # the meta-runner's fewest-tags rule, with the real runner tags
    assert hw.machines_for_tags(["nvidia-gpus", "tum"])[1] == ["tum-rocinante-nvidia"]
    assert sorted(hw.machines_for_tags(["amd-gpus", "tum"])[1]) == ["tum-mi210", "tum-mi50"]
    assert hw.machines_for_tags(["intel-fp32-gpus", "tum"])[1] == ["tum-a770"]
