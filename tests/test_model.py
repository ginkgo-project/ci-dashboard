from extract.model import Job, apply_build, missing_versions


def make_job():
    return Job(key="gitlab:x", ci="gitlab", name="x", kind="build")


def test_apply_build_fills_the_configuration():
    job = make_job()
    apply_build(
        job,
        {"CMAKE_BUILD_TYPE": "Debug", "GINKGO_BUILD_CUDA": "ON", "GINKGO_BUILD_MPI": "ON",
         "BUILD_SHARED_LIBS": "OFF", "GINKGO_BUILD_OMP": "ON"},
        {"gcc": "12.4.0", "cuda": "12.0.1", "openmpi": "4.1.8"},
        "g++",
    )
    assert job.compiler == {"name": "gcc", "version": "12.4.0"}
    assert job.device == {"name": "cuda", "version": "12.0.1"}
    assert job.mpi == "openmpi"
    assert (job.build_type, job.linkage, job.omp) == ("debug", "static", True)
    assert job.precision == {"mixed": False, "half": True, "bfloat16": True}
    assert missing_versions(job) == []


def test_apply_build_without_mpi_implementation_or_compiler():
    job = make_job()
    apply_build(job, {"GINKGO_BUILD_MPI": "ON"}, {}, None)
    assert job.mpi == "mpi"
    assert job.compiler == {"name": "gcc", "version": None}
    assert job.device is None
    assert missing_versions(job) == ["gitlab:x: no version for gcc"]


def test_apply_build_reads_the_compiler_from_cmake_flags():
    job = make_job()
    apply_build(job, {"CMAKE_CXX_COMPILER": "/bin/g++", "GINKGO_BUILD_HIP": "ON"},
                {"gcc": "13.4", "rocm": "6.3.3"}, None)
    assert job.compiler == {"name": "gcc", "version": "13.4"}
    assert job.device == {"name": "rocm", "version": "6.3.3"}


def test_to_dict_is_plain_data():
    job = make_job()
    job.machines = ["tum-cpu"]
    data = job.to_dict()
    assert data["key"] == "gitlab:x"
    assert data["machines"] == ["tum-cpu"]
    assert data["compile_only"] is False
