"""Job records from the GitHub Actions workflows."""

import itertools
import json
import re
from pathlib import Path

import yaml

from . import cmake, toolchain
from .hardware import Hardware
from .model import Job, apply_build, missing_versions

# entry workflows -> the pipelines their jobs run in. CI-Extra only runs on
# pull requests with the 1:ST:run-full-test or 1:ST:ready-to-merge label.
ENTRY_WORKFLOWS = {"ci.yml": ["develop", "pr-quick"], "ci-extra.yml": ["pr-full"]}
LOCAL_WORKFLOW = "./.github/workflows/"

_EXPRESSION = re.compile(r"\$\{\{\s*([^}]*?)\s*\}\}")
_FULL_SWITCH = re.compile(
    r"fromJSON\(\s*inputs\.full\s*&&\s*'([^']*)'\s*\|\|\s*'([^']*)'\s*\)")
_CMAKE = re.compile(r"\bcmake\b")
_TEST_COMMAND = re.compile(r"\bctest\b")


def evaluate(text: str, matrix: dict) -> str:
    """Replaces ${{ matrix.X }} and ${{ matrix.config.X }}; other expressions stay."""
    def value(match):
        path = match.group(1)
        if not path.startswith("matrix."):
            return match.group(0)
        node = matrix
        for part in path.split(".")[1:]:
            if not isinstance(node, dict) or part not in node:
                return match.group(0)
            node = node[part]
        return str(node)

    return _EXPRESSION.sub(value, text)


def matrix_combinations(matrix, full: bool | None) -> list[dict]:
    """The combinations of a strategy.matrix, including the
    fromJSON(inputs.full && '[...]' || '[...]') switch of windows-msvc.yml."""
    if not matrix:
        return [{}]
    axes = {}
    for key, values in matrix.items():
        if key in ("include", "exclude"):
            continue
        if isinstance(values, str):
            switch = _FULL_SWITCH.search(values)
            values = json.loads(switch.group(1) if full else switch.group(2)) if switch else [values]
        axes[key] = values
    keys = list(axes)
    return [dict(zip(keys, combination))
            for combination in itertools.product(*(axes[key] for key in keys))]


def runs_with(job: dict, full: bool | None) -> bool:
    condition = str(job.get("if", "")).replace(" ", "")
    if "!inputs.full" in condition:
        return not full
    if "inputs.full" in condition:
        return bool(full)
    return True


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _local_callee(job: dict) -> str | None:
    uses = job.get("uses")
    if isinstance(uses, str) and uses.startswith(LOCAL_WORKFLOW):
        return uses[len(LOCAL_WORKFLOW):]
    return None


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def extract(root: Path, hw: Hardware, env: dict) -> tuple[list[Job], list[str]]:
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return [], ["github: no .github/workflows directory"]
    docs = {path.name: _load(path) for path in sorted(workflows.glob("*.yml"))}
    called = {_local_callee(job) for doc in docs.values()
              for job in (doc.get("jobs") or {}).values()} - {None}
    jobs: dict[str, Job] = {}
    warnings: list[str] = []
    for entry, pipelines in ENTRY_WORKFLOWS.items():
        if entry not in docs:
            warnings.append(f"github: {entry} not found")
            continue
        for caller_id, caller in (docs[entry].get("jobs") or {}).items():
            callee = _local_callee(caller)
            if callee:
                full = (caller.get("with") or {}).get("full")
                targets = [(f"{caller_id} / ", job_id, job, full)
                           for job_id, job in (docs.get(callee, {}).get("jobs") or {}).items()]
            else:
                targets = [("", caller_id, caller, None)]
            for prefix, job_id, job, full in targets:
                if not runs_with(job, full):
                    continue
                for matrix in matrix_combinations((job.get("strategy") or {}).get("matrix"), full):
                    record = _build_job(prefix, job_id, job, matrix, hw, env, warnings)
                    existing = jobs.setdefault(record.key, record)
                    existing.pipelines += [p for p in pipelines if p not in existing.pipelines]
    for name, doc in docs.items():
        if name in ENTRY_WORKFLOWS or name in called:
            continue
        # e.g. mirror-major.yml, whose failure leaves every GitLab result empty
        pipelines = ["develop"] if _runs_on_push_to(doc, "develop") else ["other"]
        for check in _check_names(docs, doc):
            # several workflows can produce the same check run name (mirror-develop.yml
            # and mirror-major.yml both run "mirror / to_gitlab"); "other" only stays
            # when no workflow puts the check into a real pipeline
            job = jobs.setdefault(f"github:{check}", Job(key=f"github:{check}", ci="github",
                                                         name=check, kind="check", site="GitHub"))
            merged = job.pipelines + [p for p in pipelines if p not in job.pipelines]
            job.pipelines = [p for p in merged if p != "other"] or ["other"]
    return list(jobs.values()), list(dict.fromkeys(warnings))


def _build_job(prefix: str, job_id: str, job: dict, matrix: dict, hw: Hardware, env: dict,
               warnings: list[str]) -> Job:
    name = prefix + evaluate(str(job.get("name", job_id)), matrix)
    runs_on = evaluate(str(_first(job.get("runs-on"))), matrix)
    record = Job(key=f"github:{name}", ci="github", name=name, kind="build", site="GitHub")
    machine = hw.github_runners.get(runs_on)
    if machine:
        record.machines, record.dispatched_to = [machine], [machine]
    else:
        warnings.append(f"{record.key}: unknown runner {runs_on}")
    script = evaluate("\n".join(str(step.get("run", "")) for step in job.get("steps") or []),
                      matrix)
    if not _CMAKE.search(script):
        record.kind = "check"
        return record
    runner_env = env["github_runners"].get(runs_on, {})
    versions = toolchain.merge(env["jobs"].get(record.key, {}), runner_env,
                               toolchain.versions_from_tokens(name))
    apply_build(record, cmake.parse_flags(script), versions, next(iter(runner_env), None))
    record.compile_only = "only compile" in name or not _TEST_COMMAND.search(script)
    warnings.extend(missing_versions(record))
    return record


def _runs_on_push_to(doc: dict, branch: str) -> bool:
    # PyYAML reads the key `on` as the boolean True
    on = doc.get("on", doc.get(True))
    push = on.get("push") if isinstance(on, dict) else None
    return isinstance(push, dict) and branch in (push.get("branches") or [])


def _check_names(docs: dict, doc: dict) -> list[str]:
    """Check run names of a workflow that is not a build, e.g. mirror / to_gitlab."""
    names = []
    for job_id, job in (doc.get("jobs") or {}).items():
        callee = _local_callee(job)
        if callee:
            names += [f"{job_id} / {evaluate(str(called.get('name', called_id)), {})}"
                      for called_id, called in (docs.get(callee, {}).get("jobs") or {}).items()]
        else:
            names.append(evaluate(str(job.get("name", job_id)), {}))
    return names
