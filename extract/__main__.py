"""python -m extract GINKGO_DIR OUTPUT: writes the coverage of Ginkgo's CI jobs."""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

from . import github, gitlab, hardware, schema, toolchain

GITLAB_ENTRY = ".gitlab-ci.yml"
CSCS_ENTRY = ".gitlab/cscs.yml"
GITLAB_PIPELINES = ["develop", "pr-quick", "pr-full"]
CSCS_PIPELINES = ["pr-cscs"]   # configured on the CSCS CI setup page: pull requests


def _commit(ginkgo: Path) -> str | None:
    result = subprocess.run(["git", "-C", str(ginkgo), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() or None if result.returncode == 0 else None


def build(ginkgo: Path, config_dir: Path, now: datetime.datetime) -> dict:
    hw = hardware.load(config_dir / "hardware.yml")
    env = toolchain.load_environments(config_dir / "environments.yml")
    supported = toolchain.load_supported(config_dir / "supported.yml")
    results = [gitlab.extract(ginkgo, GITLAB_ENTRY, "gitlab", hw, env, GITLAB_PIPELINES)]
    if (ginkgo / CSCS_ENTRY).exists():
        results.append(gitlab.extract(ginkgo, CSCS_ENTRY, "cscs", hw, env, CSCS_PIPELINES))
    results.append(github.extract(ginkgo, hw, env))
    doc = {
        "generated_at": now.isoformat(timespec="seconds"),
        "ginkgo_commit": _commit(ginkgo),
        "warnings": [warning for _, warnings in results for warning in warnings],
        "machines": hw.machines,
        "columns": hw.columns,
        "supported": supported,
        "jobs": [job.to_dict() for jobs, _ in results for job in jobs],
    }
    schema.check_coverage(doc)
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m extract",
                                     description="Writes the coverage of Ginkgo's CI jobs as JSON.")
    parser.add_argument("ginkgo", type=Path, help="Ginkgo source directory")
    parser.add_argument("output", type=Path, help="coverage.json to write")
    parser.add_argument("--config-dir", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="directory with hardware.yml, environments.yml and supported.yml")
    args = parser.parse_args(argv)
    doc = build(args.ginkgo, args.config_dir, datetime.datetime.now(datetime.timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=1) + "\n")
    for warning in doc["warnings"]:
        print("warning:", warning, file=sys.stderr)
    print(f"{len(doc['jobs'])} jobs written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
