"""Shared fixtures: a small hardware.yml, environments.yml and supported.yml."""

import pytest
import yaml

from extract import hardware, toolchain

TEST_HARDWARE = """
columns: [x86-64, arm64, windows-x86-64, rocinante NVIDIA, L40S, A100, GH200, compile-only]
machines:
  tum-cpu: {site: TUM, node: develop partition, vendor: cpu, arch: x86-64, column: x86-64}
  tum-l40s: {site: TUM, node: gpu-nvidia, gpu: NVIDIA L40S 48GB, vendor: nvidia, arch: sm_89, column: L40S}
  tum-rocinante-nvidia: {site: TUM, node: rocinante, gpu: NVIDIA A100 or A2, vendor: nvidia, column: rocinante NVIDIA}
  status-runner: {vendor: cpu, arch: x86-64, column: x86-64}
  horeka-a100: {site: HoreKa, gpu: NVIDIA A100 40GB, vendor: nvidia, arch: sm_80, column: A100}
  cscs-gh200: {site: CSCS, node: Daint, gpu: NVIDIA GH200, vendor: nvidia, arch: sm_90, column: GH200}
  github-x86-64: {site: GitHub, node: ubuntu-24.04, vendor: cpu, arch: x86-64, column: x86-64}
  github-arm64: {site: GitHub, node: ubuntu-24.04-arm, vendor: cpu, arch: arm64, column: arm64}
  github-windows: {site: GitHub, node: windows, vendor: cpu, arch: x86-64, column: windows-x86-64}
gitlab_runners:
  ginkgo-cluster-meta-runner-cpu: {tags: [tum, cpu], machine: tum-cpu}
  ginkgo-cluster-meta-runner-nvidia_l40s: {tags: [nvidia-gpus, nvidia-gpus-l40s, tum], machine: tum-l40s}
  ginkgo-cluster-meta-runner-nvidia_rocinante: {tags: [nvidia-gpus, tum], machine: tum-rocinante-nvidia}
  Running small status jobs: {tags: [status-jobs], machine: status-runner}
  Runner for horeka-ci-controller: {tags: [horeka], machine: horeka-a100}
gitlab_templates:
  .baremetal-runner-daint-gh200: cscs-gh200
github_runners:
  ubuntu-24.04: github-x86-64
  ubuntu-latest: github-x86-64
  ubuntu-24.04-arm: github-arm64
  windows-latest: github-windows
  windows-2022: github-windows
"""

TEST_ENVIRONMENTS = {
    "images": {
        "rocky_tum": {"gcc": "11.5"},
        "prgenv-gnu/25.11:v1": {"cuda": "12.9", "gcc": "14.2", "cray-mpich": "8.1.32"},
    },
    "github_runners": {
        "ubuntu-24.04": {"gcc": "13.3"},
        "ubuntu-24.04-arm": {"gcc": "13.3"},
        "windows-latest": {"msvc": "19.51"},
        "windows-2022": {"msvc": "19.44"},
    },
    "jobs": {},
}

TEST_SUPPORTED = {"gcc": {"min": "9", "max": "16"}, "cuda": {"min": "11.0", "max": "13.3"}}


@pytest.fixture
def config_dir(tmp_path):
    directory = tmp_path / "config"
    directory.mkdir()
    (directory / "hardware.yml").write_text(TEST_HARDWARE)
    (directory / "environments.yml").write_text(yaml.safe_dump(TEST_ENVIRONMENTS))
    (directory / "supported.yml").write_text(yaml.safe_dump(TEST_SUPPORTED))
    return directory


@pytest.fixture
def hw(config_dir):
    return hardware.load(config_dir / "hardware.yml")


@pytest.fixture
def env(config_dir):
    return toolchain.load_environments(config_dir / "environments.yml")
