import pytest

from extract import gitlab
from tests import fake_ginkgo

DEFAULT = ["develop", "pr-quick", "pr-full"]


@pytest.fixture
def ginkgo(tmp_path):
    return fake_ginkgo.write(tmp_path / "ginkgo")


@pytest.fixture
def extracted(ginkgo, hw, env):
    jobs, warnings = gitlab.extract(ginkgo, ".gitlab-ci.yml", "gitlab", hw, env, DEFAULT)
    return {job.key: job for job in jobs}, warnings


def test_deep_merge():
    assert gitlab.deep_merge({"a": {"x": 1, "y": 2}, "b": [1]}, {"a": {"y": 3}, "b": [2]}) == {
        "a": {"x": 1, "y": 3},
        "b": [2],
    }


def test_load_merges_local_includes_and_ignores_remote_ones(ginkgo):
    doc = gitlab.load(ginkgo, ".gitlab-ci.yml")
    assert doc[".default_variables"]["variables"]["BUILD_TYPE"] == "Debug"
    assert "horeka/a100/cuda124/nompi/gcc/nondefault-stream/release/shared-reduced" in doc
    assert "include" not in doc
    assert "include" not in gitlab.load(ginkgo, ".gitlab/cscs.yml")


def test_resolve_applies_extends_in_order_with_own_keys_last(ginkgo):
    doc = gitlab.load(ginkgo, ".gitlab-ci.yml")
    merged, chain = gitlab.resolve(doc, "build/cuda120/openmpi/gcc/cuda/release/static")
    assert merged["variables"]["BUILD_TYPE"] == "Release"
    assert merged["variables"]["CXX_COMPILER"] == "g++"
    assert merged["tags"] == ["nvidia-gpus", "tum"]
    assert chain == [".build_and_test_template", ".default_variables",
                     ".full_test_condition", ".use_tum-nvidia"]


def test_resolve_rejects_extends_loops():
    with pytest.raises(ValueError, match="extends loop"):
        gitlab.resolve({"a": {"extends": ".b"}, ".b": {"extends": "a"}}, "a")


def test_tum_cuda_job(extracted):
    jobs, _ = extracted
    job = jobs["gitlab:build/cuda120/openmpi/gcc/cuda/release/static"]
    assert job.kind == "build"
    assert job.pipelines == ["develop", "pr-full"]
    assert job.machines == ["tum-l40s", "tum-rocinante-nvidia"]
    assert job.dispatched_to == ["tum-rocinante-nvidia"]
    assert job.site == "TUM"
    assert job.compiler == {"name": "gcc", "version": "12.4.0"}
    assert job.device == {"name": "cuda", "version": "12.0.1"}
    assert job.mpi == "openmpi"
    assert (job.build_type, job.linkage, job.omp) == ("release", "static", False)
    assert job.precision == {"mixed": True, "half": True, "bfloat16": True}
    assert job.compile_only is False


def test_compile_only_cpu_job_with_versions_from_the_image(extracted):
    jobs, _ = extracted
    job = jobs["gitlab:build/nocuda/openmpi/clang/omp/debug/shared"]
    assert job.pipelines == ["develop", "pr-quick"]
    assert job.compiler == {"name": "clang", "version": "8"}
    assert job.device is None
    assert job.mpi is None
    assert (job.build_type, job.omp, job.compile_only) == ("debug", True, True)
    assert job.dispatched_to == ["tum-cpu"]


def test_status_check_and_disabled_jobs(extracted):
    jobs, _ = extracted
    assert jobs["gitlab:sync"].kind == "status"
    assert jobs["gitlab:sync"].pipelines == ["develop"]
    assert jobs["gitlab:sync"].machines == ["status-runner"]
    assert jobs["gitlab:clang-tidy"].kind == "check"
    assert jobs["gitlab:clang-tidy"].build_type is None
    disabled = jobs["gitlab:build/dpcpp/gpu/release/shared"]
    assert disabled.disabled is True
    assert disabled.pipelines == []


def test_horeka_job_takes_flags_from_extra_cmake_flags(extracted):
    jobs, _ = extracted
    job = jobs["gitlab:horeka/a100/cuda124/nompi/gcc/nondefault-stream/release/shared-reduced"]
    assert job.kind == "build"
    assert job.pipelines == ["custom"]
    assert job.machines == ["horeka-a100"]
    assert job.site == "HoreKa"
    assert job.compiler == {"name": "gcc", "version": "13"}
    assert job.device == {"name": "cuda", "version": "12.4"}
    assert job.mpi is None
    assert job.omp is False
    assert job.nondefault_stream is True
    assert job.build_type == "release"
    assert job.compile_only is False


def test_warnings_for_name_mismatch_unknown_template_tags_and_version(extracted):
    _, warnings = extracted
    assert sorted(warnings) == sorted([
        "build/cuda124/mpich/gcc/cuda/release/shared: the name says cuda 12.4, "
        "the configuration has 12.6.3",
        "gitlab:broken: unknown template .use_missing-template",
        "gitlab:broken: no runner matches the tags ['no-such-tag']",
        "gitlab:broken: no version for gcc",
    ])


def test_cscs_job_uses_the_template_machine_and_the_uenv(ginkgo, hw, env):
    jobs, warnings = gitlab.extract(ginkgo, ".gitlab/cscs.yml", "cscs", hw, env, ["pr-cscs"])
    assert warnings == []
    assert [job.key for job in jobs] == ["cscs:daint/cuda129/cray-mpich/gcc/omp/release/static"]
    job = jobs[0]
    assert job.pipelines == ["pr-cscs"]
    assert job.machines == job.dispatched_to == ["cscs-gh200"]
    assert job.site == "CSCS"
    assert job.compiler == {"name": "gcc", "version": "14.2"}
    assert job.device == {"name": "cuda", "version": "12.9"}
    assert job.mpi == "cray-mpich"
    assert (job.linkage, job.omp, job.compile_only) == ("static", True, False)


BRANCH_RULES = """
.daint:
  extends: .baremetal-runner-daint-gh200
  stage: test
  rules:
    - if: $CI_COMMIT_REF_NAME != "develop"
  script:
    - uenv run ${UENV} -- bash ../.gitlab/run-ctest.sh

pull-requests:
  extends: .daint

develop-only:
  extends: .daint
  rules:
    - if: $CI_COMMIT_REF_NAME == "develop"

other-rules:
  extends: .daint
  rules:
    - if: $CI_COMMIT_REF_NAME == "develop"
      when: manual
"""


def test_rules_that_check_for_develop(tmp_path, hw, env):
    root = fake_ginkgo.write(tmp_path / "ginkgo", {".gitlab/cscs.yml": BRANCH_RULES})
    jobs, _ = gitlab.extract(root, ".gitlab/cscs.yml", "cscs", hw, env, ["pr-cscs"])
    assert {job.name: job.pipelines for job in jobs} == {
        "pull-requests": ["pr-cscs"], "develop-only": ["develop"], "other-rules": ["custom"]}
    assert gitlab.rules_pipelines([{"if": '$CI_COMMIT_REF_NAME != "develop"'}], DEFAULT) == [
        "pr-quick", "pr-full"]


RULES_ORDER = """
.deploy_condition:
  rules:
    - if: $RUN_CI_TAG
.disable_job_condition:
  rules:
    - when: never
.full_test_condition:
  rules:
    - if: $RUN_CI_TAG
.check:
  stage: test
  tags: [cpu, tum]
  script:
    - ctest -S cmake/CTestScript.cmake

threadsanitizer:
  extends: [.check, .deploy_condition, .disable_job_condition]

reenabled:
  extends: [.check, .disable_job_condition, .full_test_condition]
"""


def test_the_last_rules_template_in_extends_wins(tmp_path, hw, env):
    root = fake_ginkgo.write(tmp_path / "ginkgo", {".gitlab-ci.yml": RULES_ORDER})
    jobs, _ = gitlab.extract(root, ".gitlab-ci.yml", "gitlab", hw, env, DEFAULT)
    jobs = {job.name: job for job in jobs}
    assert (jobs["threadsanitizer"].pipelines, jobs["threadsanitizer"].disabled) == ([], True)
    assert (jobs["reenabled"].pipelines, jobs["reenabled"].disabled) == (["develop", "pr-full"], False)
