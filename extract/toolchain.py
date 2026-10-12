"""Toolchain versions from module lists, version codes in image and job
names, and the hand-kept environments.yml."""

import re
from pathlib import Path

import yaml

# names in modules, images and job names -> the names the dashboard uses
ALIASES = {
    "gcc": "gcc", "gnu": "gcc",
    "clang": "clang", "llvm": "clang",
    "cuda": "cuda", "rocm": "rocm", "nvhpc": "nvhpc",
    "oneapi": "oneapi", "icpx": "oneapi", "intel-oneapi-compilers": "oneapi",
    "cmake": "cmake",
    "openmpi": "openmpi", "mpich": "mpich", "mvapich": "mvapich", "mvapich2": "mvapich",
    "cray-mpich": "cray-mpich",
}
MPI_NAMES = ("openmpi", "mpich", "mvapich", "cray-mpich")

# cray-mpich and mvapich2 come before mpich, so that they match as a whole
_TOKEN = re.compile(
    r"(cray-mpich|openmpi|mvapich2?|mpich|cuda|rocm|nvhpc|icpx|oneapi|gnu|gcc|llvm|clang)"
    r"(?:-?(\d+(?:\.\d+)*))?"
)
ENVIRONMENT_SECTIONS = ("images", "github_runners", "jobs")


def versions_from_modules(modules: str | None) -> dict[str, str]:
    """'cmake/3.18.6 compiler/gnu/13 mpich' -> {'cmake': '3.18.6', 'gcc': '13', 'mpich': ''}"""
    versions = {}
    for item in (modules or "").split():
        parts = item.split("/")
        name, version = (parts[0], "") if len(parts) == 1 else (parts[-2], parts[-1])
        name = ALIASES.get(name)
        if name and name not in versions:
            versions[name] = version
    return versions


def _code_to_version(name: str, code: str) -> str:
    """Version codes in names: cuda114 -> 11.4, rocm644 -> 6.4.4,
    nvhpc233 -> 23.3, icpx202421 -> 2024.2.1, gnu9 -> 9."""
    if "." in code or len(code) < 2 or name in ("gcc", "clang"):
        return code
    if name in ("cuda", "nvhpc"):
        return f"{code[:2]}.{code[2:]}"
    if name == "rocm":
        return ".".join(code)
    if name == "oneapi" and len(code) > 4:
        return ".".join([code[:4], *code[4:]])
    return code


def versions_from_tokens(text: str | None) -> dict[str, str]:
    """Versions in image or job names, e.g. 'ginkgohub/cuda:114-openmpi-gnu10'.
    A toolchain without a version code is left out; MPI names are kept with ''."""
    versions = {}
    for raw_name, code in _TOKEN.findall((text or "").replace(":", "").lower()):
        name = ALIASES[raw_name]
        if name in versions:
            continue
        if code:
            versions[name] = _code_to_version(name, code)
        elif name in MPI_NAMES:
            versions[name] = ""
    return versions


def merge(*sources: dict | None) -> dict[str, str]:
    """Merges version dicts: an earlier source wins, and a version beats an empty one."""
    result: dict[str, str] = {}
    for source in sources:
        for name, version in (source or {}).items():
            if name not in result or (not result[name] and version):
                result[name] = str(version)
    return result


def compiler_name(cxx: str | None) -> str | None:
    """g++ -> gcc, clang++ -> clang, nvc++ -> nvhpc, icpx and dpcpp -> oneapi, cl -> msvc."""
    if not cxx:
        return None
    base = cxx.rsplit("/", 1)[-1].lower()
    for prefix, name in (("clang", "clang"), ("g++", "gcc"), ("gcc", "gcc"),
                         ("nvc++", "nvhpc"), ("icpx", "oneapi"), ("dpcpp", "oneapi"),
                         ("cl", "msvc")):
        if base.startswith(prefix):
            return name
    return base


def _same_version(short: str, full: str) -> bool:
    a, b = short.split("."), full.split(".")
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def name_mismatches(job_name: str, versions: dict[str, str]) -> list[str]:
    """Versions in the job name that its configuration contradicts,
    e.g. cuda124 in the name while the job loads CUDA 12.6.3."""
    problems = []
    for name, version in versions_from_tokens(job_name).items():
        actual = versions.get(name)
        if version and actual and not _same_version(version, actual):
            problems.append(
                f"{job_name}: the name says {name} {version}, the configuration has {actual}"
            )
    return problems


def load_environments(path) -> dict:
    """environments.yml; versions must be quoted, since YAML reads 13.10 as 13.1."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    result = {section: data.get(section) or {} for section in ENVIRONMENT_SECTIONS}
    for section, owners in result.items():
        for owner, versions in owners.items():
            for name, version in (versions or {}).items():
                if not isinstance(version, str):
                    raise ValueError(
                        f"{path}: {section}.{owner}.{name} must be a quoted string, "
                        f"not {version!r}"
                    )
    return result


def load_supported(path) -> dict[str, dict[str, str]]:
    """supported.yml: per toolchain a quoted min and an optional quoted max."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    for name, bounds in data.items():
        if not isinstance(bounds, dict) or "min" not in bounds:
            raise ValueError(f"{path}: {name} needs a min")
        for key, value in bounds.items():
            if key not in ("min", "max") or not isinstance(value, str):
                raise ValueError(f"{path}: {name}.{key} must be min or max with a quoted version")
    return data
