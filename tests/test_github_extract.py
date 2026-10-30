import pytest

from extract import github
from tests import fake_ginkgo


@pytest.fixture
def extracted(tmp_path, hw, env):
    root = fake_ginkgo.write(tmp_path / "ginkgo")
    jobs, warnings = github.extract(root, hw, env)
    return {job.key: job for job in jobs}, warnings


def test_evaluate_replaces_matrix_values_and_keeps_other_expressions():
    matrix = {"config": {"name": "a/b"}, "os": "windows-latest"}
    assert github.evaluate("x ${{ matrix.config.name }} ${{matrix.os}} ${{ inputs.full }}",
                           matrix) == "x a/b windows-latest ${{ inputs.full }}"
    assert github.evaluate("${{ matrix.config.missing }}", matrix) == "${{ matrix.config.missing }}"


def test_matrix_combinations():
    assert github.matrix_combinations(None, None) == [{}]
    assert github.matrix_combinations({"config": [{"a": 1}, {"a": 2}]}, None) == [
        {"config": {"a": 1}}, {"config": {"a": 2}}]
    switch = "${{ fromJSON(inputs.full && '[\"w-2022\", \"w-latest\"]' || '[\"w-latest\"]') }}"
    assert github.matrix_combinations({"os": switch}, True) == [{"os": "w-2022"}, {"os": "w-latest"}]
    assert github.matrix_combinations({"os": switch}, False) == [{"os": "w-latest"}]


def test_jobs_and_their_pipelines(extracted):
    jobs, warnings = extracted
    assert warnings == []
    assert {key: job.pipelines for key, job in jobs.items()} == {
        "github:arm / arm/omp/release/shared-16bit": ["develop", "pr-quick"],
        "github:windows-msvc / msvc/windows-latest": ["develop", "pr-quick", "pr-full"],
        "github:linux-gcc-cuda / gcc/cuda-13.3/release/shared (only compile)": ["develop", "pr-quick"],
        "github:clang-tidy / clang-tidy on changed lines": ["pr-quick"],
        "github:coverage / coverage of the reference, OpenMP and MPI code": ["develop", "pr-full"],
        "github:arm / arm/omp/release/static": ["pr-full"],
        "github:windows-msvc / msvc/windows-2022": ["pr-full"],
        "github:mirror / to_gitlab": ["develop"],
        "github:check-format": ["other"],
    }


def test_a_job_only_ci_extra_calls_stays_on_develop_if_it_also_runs_on_pushes(tmp_path, hw, env):
    coverage = """  coverage:
    if: >-
      github.event_name != 'pull_request' || (
      !contains(github.event.pull_request.labels.*.name, '1:ST:SKIP_ALL_CI') && (
      (github.event.action != 'labeled' && contains(github.event.pull_request.labels.*.name, '1:ST:run-full-test'))
      || github.event.label.name == '1:ST:run-full-test'))
    uses: ./.github/workflows/coverage.yml
"""
    root = fake_ginkgo.write(tmp_path / "ginkgo", {
        **fake_ginkgo.FILES,
        ".github/workflows/ci.yml": fake_ginkgo.CI.split("  coverage:")[0],
        ".github/workflows/ci-extra.yml": fake_ginkgo.CI_EXTRA.split("  coverage:")[0] + coverage,
    })
    jobs, warnings = github.extract(root, hw, env)
    assert warnings == []
    job = next(job for job in jobs if job.key == "github:coverage / coverage of the reference, OpenMP and MPI code")
    assert job.pipelines == ["develop", "pr-full"]


def test_arm_build(extracted):
    jobs, _ = extracted
    job = jobs["github:arm / arm/omp/release/shared-16bit"]
    assert job.kind == "build"
    assert job.site == "GitHub"
    assert job.machines == job.dispatched_to == ["github-arm64"]
    assert job.compiler == {"name": "gcc", "version": "13.3"}
    assert job.precision == {"mixed": True, "half": True, "bfloat16": True}
    assert (job.build_type, job.linkage, job.omp, job.compile_only) == ("release", "shared", None, False)
    assert jobs["github:arm / arm/omp/release/static"].linkage == "static"


def test_windows_runner_from_the_matrix(extracted):
    jobs, _ = extracted
    assert jobs["github:windows-msvc / msvc/windows-latest"].compiler == {"name": "msvc", "version": "19.51"}
    job = jobs["github:windows-msvc / msvc/windows-2022"]
    assert job.compiler == {"name": "msvc", "version": "19.44"}
    assert job.precision["half"] is False
    assert job.machines == ["github-windows"]


def test_compile_only_cuda_job(extracted):
    jobs, _ = extracted
    job = jobs["github:linux-gcc-cuda / gcc/cuda-13.3/release/shared (only compile)"]
    assert job.compile_only is True
    assert job.device == {"name": "cuda", "version": "13.3"}
    assert job.compiler == {"name": "gcc", "version": "13.3"}
    assert job.omp is True


def test_other_workflows_become_checks(extracted):
    jobs, _ = extracted
    assert jobs["github:mirror / to_gitlab"].kind == "check"
    assert jobs["github:check-format"].kind == "check"
    assert jobs["github:check-format"].machines == []


def test_a_job_that_only_configures_is_a_check(extracted):
    jobs, _ = extracted
    job = jobs["github:clang-tidy / clang-tidy on changed lines"]
    assert job.kind == "check"
    assert job.machines == ["github-x86-64"]


def test_build_commands():
    builds = ["make -j4", "ninja install", "cmake --build . -j4", 'bash -c "cmake .. && make"']
    others = ["apt-get install -y build-essential cmake ninja-build", "cmake .. -G Ninja",
              "cmake --version", "git diff | clang-tidy-diff-18.py -p1"]
    assert all(github._BUILD_COMMAND.search(line) for line in builds)
    assert not any(github._BUILD_COMMAND.search(line) for line in others)


def test_unknown_runner_gives_a_warning(tmp_path, hw, env):
    files = dict(fake_ginkgo.FILES)
    files[".github/workflows/linux-gcc-cuda.yml"] = fake_ginkgo.LINUX_CUDA.replace(
        "[ubuntu-24.04]", "[self-hosted-gpu]")
    root = fake_ginkgo.write(tmp_path / "ginkgo", files)
    _, warnings = github.extract(root, hw, env)
    assert warnings == [
        "github:linux-gcc-cuda / gcc/cuda-13.3/release/shared (only compile): "
        "unknown runner self-hosted-gpu",
        "github:linux-gcc-cuda / gcc/cuda-13.3/release/shared (only compile): "
        "no version for gcc",
    ]
