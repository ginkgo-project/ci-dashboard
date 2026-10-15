"""python -m status COVERAGE OUTPUT: writes the latest results of Ginkgo's CI jobs
and the clang-tidy findings of its open pull requests."""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from extract import hardware, schema

from . import github, gitlab, merge, tidy
from .fetch import FetchError, Fetcher

# ginkgo-public-ci, and the public gitlab.com project CSCS mirrors its pipelines to
PROJECTS = {"gitlab": 6431537, "cscs": 86842909}
REPO = "ginkgo-project/ginkgo"
COMMITS = 10
DEVELOP_PIPELINES = 20
ELSEWHERE_PIPELINES = 50


def collect(coverage: dict, fetcher, hw, now: datetime.datetime) -> dict:
    def wanted(ci: str) -> set[str]:
        """Jobs that never run on develop, so they need a result from elsewhere."""
        return {job["key"] for job in coverage["jobs"]
                if job["ci"] == ci and "develop" not in job["pipelines"] and not job["disabled"]}

    repo = github.Repo(fetcher, REPO)
    commits = repo.pushed_commits("develop", COMMITS)
    shas = [commit["sha"] for commit in commits]
    public_ci = gitlab.Project(fetcher, PROJECTS["gitlab"], "gitlab", hw)
    cscs = gitlab.Project(fetcher, PROJECTS["cscs"], "cscs", hw)
    histories = [public_ci.develop_history(shas, DEVELOP_PIPELINES), repo.develop_history(shas)]
    pulls = tidy.Pulls(fetcher, REPO).collect(now)
    elsewhere = [
        public_ci.latest_elsewhere(wanted("gitlab"), ELSEWHERE_PIPELINES),
        cscs.latest_elsewhere(wanted("cscs"), ELSEWHERE_PIPELINES),
        # the clang-tidy job runs in CI, not CI-Extra; its result comes from the pull requests
        repo.latest_elsewhere(wanted("github") - {tidy.KEY}),
        tidy.newest_result(pulls),
    ]
    doc = merge.assemble(coverage, commits, histories, elsewhere, now)
    doc["clang_tidy"] = {"check": tidy.CHECK, "max_age_days": tidy.MAX_AGE.days, "pulls": pulls}
    schema.check_status(doc)
    return doc


def main(argv: list[str] | None = None, fetcher=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m status",
                                     description="Writes the latest results of Ginkgo's CI jobs as JSON.")
    parser.add_argument("coverage", type=Path, help="coverage.json written by python -m extract")
    parser.add_argument("output", type=Path, help="status.json to write")
    parser.add_argument("--config-dir", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="directory with hardware.yml")
    args = parser.parse_args(argv)
    coverage = json.loads(args.coverage.read_text())
    hw = hardware.load(args.config_dir / "hardware.yml")
    fetcher = fetcher or Fetcher(github_token=os.environ.get("GITHUB_TOKEN"))
    try:
        doc = collect(coverage, fetcher, hw, datetime.datetime.now(datetime.timezone.utc))
    except FetchError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"results of {len(doc['jobs'])} jobs over {len(doc['commits'])} commits "
          f"written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
