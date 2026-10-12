"""The CMake flags of a CI job and the Ginkgo build configuration they select."""

import re

# Ginkgo's defaults (CMakeLists.txt) for the options the dashboard shows.
# None means CMake detects it (GINKGO_HAS_OMP, GINKGO_HAS_MPI, GINKGO_HAS_CUDA, ...).
DEFAULTS = {
    "CMAKE_BUILD_TYPE": "Release",
    "BUILD_SHARED_LIBS": "ON",
    "GINKGO_BUILD_OMP": None,
    "GINKGO_BUILD_MPI": None,
    "GINKGO_BUILD_CUDA": None,
    "GINKGO_BUILD_HIP": None,
    "GINKGO_BUILD_SYCL": None,
    "GINKGO_MIXED_PRECISION": "OFF",
    "GINKGO_ENABLE_HALF": "ON",
    "GINKGO_ENABLE_BFLOAT16": "ON",
    "GINKGO_FAST_TESTS": "OFF",
    "GINKGO_TEST_NONDEFAULT_STREAM": "OFF",
}

# the device module each build flag enables, checked in this order
DEVICES = (
    ("GINKGO_BUILD_CUDA", "cuda"),
    ("GINKGO_BUILD_HIP", "rocm"),
    ("GINKGO_BUILD_SYCL", "oneapi"),
)

_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
_FLAG = re.compile(
    r"""-D([A-Za-z_][A-Za-z0-9_]*)(?::[A-Za-z]+)?=("[^"]*"|'[^']*'|[^\s"']*)"""
)


def expand(text: str, variables: dict[str, str], depth: int = 5) -> str:
    """Replaces $VAR and ${VAR} like the shell does, also inside the values
    of variables; unknown variables become empty."""
    for _ in range(depth):
        expanded = _VARIABLE.sub(
            lambda match: str(variables.get(match.group(1) or match.group(2), "")),
            text,
        )
        if expanded == text:
            break
        text = expanded
    return text


def parse_flags(text: str) -> dict[str, str]:
    """The -DNAME=VALUE definitions in text; a later one wins, as in CMake."""
    return {name: value.strip("\"'") for name, value in _FLAG.findall(text)}


def _value(flags: dict[str, str], name: str) -> str | None:
    value = flags.get(name)
    return DEFAULTS[name] if value in (None, "") else value


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().upper() in ("ON", "TRUE", "YES", "Y", "1")


def build_config(flags: dict[str, str]) -> dict:
    """The build configuration that flags select, with Ginkgo's defaults for the rest."""
    device = next(
        (name for flag, name in DEVICES if _bool(_value(flags, flag))), None
    )
    return {
        "build_type": _value(flags, "CMAKE_BUILD_TYPE").lower(),
        "linkage": "shared" if _bool(_value(flags, "BUILD_SHARED_LIBS")) else "static",
        "omp": _bool(_value(flags, "GINKGO_BUILD_OMP")),
        "mpi": _bool(_value(flags, "GINKGO_BUILD_MPI")),
        "device": device,
        "precision": {
            "mixed": _bool(_value(flags, "GINKGO_MIXED_PRECISION")),
            "half": _bool(_value(flags, "GINKGO_ENABLE_HALF")),
            "bfloat16": _bool(_value(flags, "GINKGO_ENABLE_BFLOAT16")),
        },
        "fast_tests": _bool(_value(flags, "GINKGO_FAST_TESTS")),
        "nondefault_stream": _bool(_value(flags, "GINKGO_TEST_NONDEFAULT_STREAM")),
    }
