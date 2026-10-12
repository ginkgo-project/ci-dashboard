import pytest

from extract import toolchain


def test_versions_from_modules():
    assert toolchain.versions_from_modules(
        "cmake/3.18.6 cuda/12.0.1 gcc/12.4.0 openmpi/4.1.8 intel-oneapi-dpl/2022.6.1"
    ) == {"cmake": "3.18.6", "cuda": "12.0.1", "gcc": "12.4.0", "openmpi": "4.1.8"}
    assert toolchain.versions_from_modules(
        "compiler/gnu/13 devel/cuda/12.4 intel-oneapi-compilers/2025.2.1 mpich"
    ) == {"gcc": "13", "cuda": "12.4", "oneapi": "2025.2.1", "mpich": ""}
    assert toolchain.versions_from_modules(None) == {}


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "ginkgohub/cuda:110-mvapich2-gnu9-llvm9-intel2020",
            {"cuda": "11.0", "mvapich": "", "gcc": "9", "clang": "9"},
        ),
        (
            "ginkgohub/nvhpc:233-cuda120-openmpi-gnu12-llvm16",
            {"nvhpc": "23.3", "cuda": "12.0", "openmpi": "", "gcc": "12", "clang": "16"},
        ),
        (
            "ginkgohub/rocm:514-openmpi-gnu11-llvm11",
            {"rocm": "5.1.4", "openmpi": "", "gcc": "11", "clang": "11"},
        ),
        ("ginkgohub/spack-oneapi:20231-openmpi", {"oneapi": "2023.1", "openmpi": ""}),
        ("build/icpx202421/gpu-fp32/release/shared", {"oneapi": "2024.2.1"}),
        (
            "build/amd/openmpi/gcc/rocm634_wo_omp/release/shared",
            {"openmpi": "", "rocm": "6.3.4"},
        ),
        ("daint/cuda131/cray-mpich/gcc/omp/debug/shared", {"cuda": "13.1", "cray-mpich": ""}),
        ("linux-gcc-cuda / gcc/cuda-13.3/release/shared (only compile)", {"cuda": "13.3"}),
        ("build/nocuda/nompi/gcc/omp/release/shared", {}),
        (None, {}),
    ],
)
def test_versions_from_tokens(text, expected):
    assert toolchain.versions_from_tokens(text) == expected


def test_merge_prefers_earlier_sources_and_versions_over_empty_ones():
    assert toolchain.merge(
        {"gcc": "12.4.0", "mpich": ""},
        None,
        {"gcc": "11.5", "mpich": "4.1", "cuda": "12.0"},
    ) == {"gcc": "12.4.0", "mpich": "4.1", "cuda": "12.0"}


def test_compiler_name():
    names = ["g++", "/usr/bin/g++-13", "clang++", "nvc++", "icpx", "dpcpp", "cl.exe",
             "msvc", "appleclang", None]
    assert [toolchain.compiler_name(name) for name in names] == [
        "gcc", "gcc", "clang", "nvhpc", "oneapi", "oneapi", "msvc", "msvc", "appleclang", None
    ]


def test_name_mismatches():
    assert toolchain.name_mismatches(
        "build/cuda124/mpich/gcc/cuda/release/shared", {"cuda": "12.6.3", "gcc": "13.3.0"}
    ) == [
        "build/cuda124/mpich/gcc/cuda/release/shared: the name says cuda 12.4, "
        "the configuration has 12.6.3"
    ]
    assert toolchain.name_mismatches("build/cuda120/openmpi", {"cuda": "12.0.1"}) == []
    assert toolchain.name_mismatches("build/cuda120", {}) == []


def test_load_environments_fills_missing_sections(tmp_path):
    path = tmp_path / "environments.yml"
    path.write_text('images:\n  rocky_tum: {gcc: "11.5"}\n')
    assert toolchain.load_environments(path) == {
        "images": {"rocky_tum": {"gcc": "11.5"}},
        "github_runners": {},
        "jobs": {},
    }


def test_load_environments_rejects_unquoted_versions(tmp_path):
    path = tmp_path / "environments.yml"
    path.write_text("images:\n  rocky_tum: {gcc: 13.10}\n")
    with pytest.raises(ValueError, match="images.rocky_tum.gcc"):
        toolchain.load_environments(path)


def test_load_supported(tmp_path):
    path = tmp_path / "supported.yml"
    path.write_text('gcc: {min: "9", max: "16"}\ncuda: {min: "11.0"}\n')
    assert toolchain.load_supported(path) == {
        "gcc": {"min": "9", "max": "16"},
        "cuda": {"min": "11.0"},
    }
    path.write_text("gcc: {max: \"16\"}\n")
    with pytest.raises(ValueError, match="gcc"):
        toolchain.load_supported(path)
