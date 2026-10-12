"""The record the extractor writes for each CI job."""

from dataclasses import asdict, dataclass, field

from . import cmake
from .toolchain import MPI_NAMES, compiler_name


@dataclass
class Job:
    key: str                       # "<ci>:<name>", unique across all CIs
    ci: str                        # gitlab, cscs or github
    name: str                      # job name in GitLab, check run name in GitHub
    kind: str                      # build, check, benchmark or status
    site: str | None = None
    pipelines: list[str] = field(default_factory=list)
    compiler: dict | None = None   # {"name": "gcc", "version": "12.4.0"}
    device: dict | None = None     # {"name": "cuda", "version": "12.0.1"}
    mpi: str | None = None         # MPI implementation, None without MPI
    omp: bool | None = None        # None: CMake detects it
    build_type: str | None = None
    linkage: str | None = None
    precision: dict | None = None
    fast_tests: bool | None = None
    nondefault_stream: bool | None = None
    machines: list[str] = field(default_factory=list)       # every machine it can run on
    dispatched_to: list[str] = field(default_factory=list)  # the ones it is sent to
    compile_only: bool = False
    disabled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def apply_build(job: Job, flags: dict[str, str], versions: dict[str, str],
                cxx: str | None) -> None:
    """Fills the build fields of job from its CMake flags and toolchain versions."""
    config = cmake.build_config(flags)
    job.build_type = config["build_type"]
    job.linkage = config["linkage"]
    job.omp = config["omp"]
    job.precision = config["precision"]
    job.fast_tests = config["fast_tests"]
    job.nondefault_stream = config["nondefault_stream"]
    compiler = compiler_name(cxx or flags.get("CMAKE_CXX_COMPILER")) or "gcc"
    job.compiler = {"name": compiler, "version": versions.get(compiler)}
    if config["device"]:
        job.device = {"name": config["device"], "version": versions.get(config["device"])}
    if config["mpi"]:
        job.mpi = next((name for name in MPI_NAMES if name in versions), "mpi")


def missing_versions(job: Job) -> list[str]:
    """Warnings for a compiler or device without a known version."""
    return [
        f"{job.key}: no version for {toolchain['name']}"
        for toolchain in (job.compiler, job.device)
        if toolchain and not toolchain.get("version")
    ]
