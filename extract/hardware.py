"""The hardware behind the CI runners, from hardware.yml."""

from dataclasses import dataclass
from pathlib import Path

import yaml


def _unique(items) -> list:
    return list(dict.fromkeys(items))


@dataclass
class Hardware:
    machines: dict[str, dict]         # id -> {site, node, gpu, vendor, arch, column}
    gitlab_runners: dict[str, dict]   # runner description -> {tags, machine}
    gitlab_templates: dict[str, str]  # job template, e.g. a CSCS runner -> machine id
    github_runners: dict[str, str]    # runs-on label -> machine id
    columns: list[str]                # coverage grid columns, in order

    def machines_for_tags(self, tags: list[str]) -> tuple[list[str], list[str]]:
        """The machines of all runners whose tags include tags, and of the runners
        gitlab-meta-runner picks: those with the fewest tags (find_match in src/run.rs)."""
        wanted = set(tags)
        if not wanted:
            return [], []
        matching = [name for name, runner in self.gitlab_runners.items()
                    if wanted <= set(runner["tags"])]
        if not matching:
            return [], []
        fewest = min(len(self.gitlab_runners[name]["tags"]) for name in matching)
        picked = [name for name in matching
                  if len(self.gitlab_runners[name]["tags"]) == fewest]
        machine = lambda name: self.gitlab_runners[name]["machine"]
        return _unique(map(machine, matching)), _unique(map(machine, picked))

    def machine_of_runner(self, description: str | None) -> str | None:
        runner = self.gitlab_runners.get(description or "")
        return runner["machine"] if runner else None

    def site_of(self, machine_ids: list[str]) -> str | None:
        for machine_id in machine_ids:
            if machine_id in self.machines:
                return self.machines[machine_id].get("site")
        return None


def load(path) -> Hardware:
    data = yaml.safe_load(Path(path).read_text()) or {}
    machines = data.get("machines") or {}
    for machine_id, machine in machines.items():
        machine.setdefault("column", machine_id)
    hw = Hardware(
        machines=machines,
        gitlab_runners=data.get("gitlab_runners") or {},
        gitlab_templates=data.get("gitlab_templates") or {},
        github_runners=data.get("github_runners") or {},
        columns=data.get("columns") or [],
    )
    _validate(hw, path)
    return hw


def _validate(hw: Hardware, path) -> None:
    if "compile-only" not in hw.columns:
        raise ValueError(f"{path}: columns must include compile-only")
    for machine_id, machine in hw.machines.items():
        if machine["column"] not in hw.columns:
            raise ValueError(f"{path}: machine {machine_id} has column {machine['column']}, "
                             "which is not in columns")
    used = [runner["machine"] for runner in hw.gitlab_runners.values()]
    used += list(hw.gitlab_templates.values()) + list(hw.github_runners.values())
    for machine_id in used:
        if machine_id not in hw.machines:
            raise ValueError(f"{path}: unknown machine {machine_id}")
