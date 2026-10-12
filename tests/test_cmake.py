from extract import cmake


def test_expand_replaces_both_forms_recursively_and_unknown_by_empty():
    variables = {"A": "1", "B": "$A-2", "C": "${B}/x"}
    assert cmake.expand("${A} $B ${C} ${MISSING}|", variables) == "1 1-2 1-2/x |"


def test_expand_leaves_command_substitution_alone():
    assert cmake.expand("x=$(command -v srun)", {}) == "x=$(command -v srun)"


def test_expand_converts_values_to_strings():
    assert cmake.expand("-n $N", {"N": 8}) == "-n 8"


def test_parse_flags_last_definition_wins_and_quotes_are_removed():
    text = (
        '-DBUILD_SHARED_LIBS=ON -DCMAKE_CXX_FLAGS="-Wpedantic -D_GLIBCXX_DEBUG=1" '
        "-DBUILD_SHARED_LIBS:BOOL=OFF -DCMAKE_CXX_FLAGS2=-ffp-contract=off"
    )
    assert cmake.parse_flags(text) == {
        "BUILD_SHARED_LIBS": "OFF",
        "CMAKE_CXX_FLAGS": "-Wpedantic -D_GLIBCXX_DEBUG=1",
        "CMAKE_CXX_FLAGS2": "-ffp-contract=off",
    }


def test_build_config_defaults_follow_ginkgo():
    assert cmake.build_config({}) == {
        "build_type": "release",
        "linkage": "shared",
        "omp": None,
        "mpi": None,
        "device": None,
        "precision": {"mixed": False, "half": True, "bfloat16": True},
        "fast_tests": False,
        "nondefault_stream": False,
    }


def test_build_config_reads_flags():
    config = cmake.build_config(
        {
            "CMAKE_BUILD_TYPE": "Debug",
            "BUILD_SHARED_LIBS": "OFF",
            "GINKGO_BUILD_OMP": "ON",
            "GINKGO_BUILD_MPI": "off",
            "GINKGO_BUILD_CUDA": "OFF",
            "GINKGO_BUILD_HIP": "ON",
            "GINKGO_MIXED_PRECISION": "ON",
            "GINKGO_ENABLE_HALF": "OFF",
            "GINKGO_TEST_NONDEFAULT_STREAM": "TRUE",
        }
    )
    assert config["build_type"] == "debug"
    assert config["linkage"] == "static"
    assert config["omp"] is True
    assert config["mpi"] is False
    assert config["device"] == "rocm"
    assert config["precision"] == {"mixed": True, "half": False, "bfloat16": True}
    assert config["nondefault_stream"] is True


def test_build_config_treats_empty_values_as_unset():
    config = cmake.build_config({"CMAKE_BUILD_TYPE": "", "GINKGO_BUILD_OMP": ""})
    assert config["build_type"] == "release"
    assert config["omp"] is None
