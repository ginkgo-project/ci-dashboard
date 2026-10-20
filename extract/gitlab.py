"""Flat job records from a GitLab CI configuration: includes, extends and
variables resolved the way GitLab does it, limited to what Ginkgo uses."""

import copy
import re
from pathlib import Path

import yaml

from . import cmake, toolchain
from .hardware import Hardware
from .model import Job, apply_build, missing_versions

# top-level keys that are not jobs
KEYWORDS = {"stages", "include", "variables", "default", "workflow", "image",
            "services", "before_script", "after_script", "cache"}

# rules templates of .gitlab/rules.yml -> the pipelines a job runs in
RULES_TEMPLATES = {
    ".quick_test_condition": ["develop", "pr-quick"],
    ".full_test_condition": ["develop", "pr-full"],
    ".full_test_short_lived_condition": ["pr-full"],
    ".deploy_condition": ["develop"],
    ".develop_condition": ["develop"],
    ".pr_condition": ["pr-quick", "pr-full"],
    ".pr_trigger_condition": ["pr-quick"],
    ".disable_job_condition": [],
}

STATUS_STAGES = {"init-status", "sync", "trigger_pipeline", "on-failure", "finalize-status"}
CHECK_STAGES = {"code_quality", "QoS_tools", "deploy"}
TEST_COMMAND = re.compile(r"\bctest\b|run-ctest\.sh|build-and-test\.sh")


def deep_merge(base: dict, override: dict) -> dict:
    """GitLab's merge for extends and includes: hashes merge recursively,
    everything else is replaced."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _local_includes(value) -> list[str]:
    items = value if isinstance(value, list) else [] if value is None else [value]
    paths = []
    for item in items:
        if isinstance(item, str) and not item.startswith(("http://", "https://")):
            paths.append(item)
        elif isinstance(item, dict) and "local" in item:
            paths.append(item["local"])
    return paths


def load(root: Path, entry: str) -> dict:
    """root/entry with its local includes merged in; the including file wins.
    Remote includes are not fetched."""
    doc = yaml.safe_load((root / entry).read_text()) or {}
    merged: dict = {}
    for path in _local_includes(doc.get("include")):
        merged = deep_merge(merged, load(root, path.lstrip("/")))
    return deep_merge(merged, {key: value for key, value in doc.items() if key != "include"})


def resolve(doc: dict, name: str) -> tuple[dict, list[str]]:
    """The job with its extends applied, and every template it uses. A
    template that is not in doc (e.g. from a remote include) adds nothing."""
    chain: list[str] = []

    def walk(key: str, seen: tuple[str, ...]) -> dict:
        if key in seen:
            raise ValueError(f"extends loop: {' -> '.join(seen + (key,))}")
        node = doc.get(key)
        if not isinstance(node, dict):
            return {}
        parents = node.get("extends", [])
        merged: dict = {}
        for parent in [parents] if isinstance(parents, str) else parents:
            chain.append(parent)
            merged = deep_merge(merged, walk(parent, seen + (key,)))
        return deep_merge(merged, {k: v for k, v in node.items() if k != "extends"})

    return walk(name, ()), chain


def rules_template(chain: list[str]) -> str | None:
    """The rules template whose rules the job ends up with: the last one in
    merge order, since a later template's rules replace an earlier one's."""
    return next((t for t in reversed(chain) if t in RULES_TEMPLATES), None)


def rules_pipelines(rules, default: list[str]) -> list[str]:
    """The pipelines of rules that only check whether the ref is develop, as in
    .gitlab/cscs.yml; any other rules are "custom"."""
    if (isinstance(rules, list) and len(rules) == 1 and isinstance(rules[0], dict)
            and set(rules[0]) == {"if"}):
        condition = " ".join(str(rules[0]["if"]).split())
        if condition == '$CI_COMMIT_REF_NAME == "develop"':
            return ["develop"]
        if condition == '$CI_COMMIT_REF_NAME != "develop"':
            return [pipeline for pipeline in default if pipeline != "develop"]
    return ["custom"]


def pipelines_of(own: dict, merged: dict, chain: list[str], default: list[str]) -> list[str]:
    if "rules" in own:
        return rules_pipelines(own["rules"], default)
    template = rules_template(chain)
    if template:
        return list(RULES_TEMPLATES[template])
    if "rules" in merged:
        return rules_pipelines(merged["rules"], default)
    only = merged.get("only")
    if only is not None:
        refs = only if isinstance(only, list) else only.get("refs", [])
        return ["develop"] if "develop" in refs else ["custom"]
    return list(default)


def kind_of(merged: dict, script: str) -> str:
    stage = str(merged.get("stage", "test"))
    if stage in STATUS_STAGES:
        return "status"
    if stage.startswith("benchmark"):
        return "benchmark"
    if stage in CHECK_STAGES:
        return "check"
    if "-DGINKGO_" in script or "build-and-test.sh" in script:
        return "build"
    return "check"


def script_text(merged: dict) -> str:
    lines: list[str] = []

    def flatten(item):
        if isinstance(item, list):
            for entry in item:
                flatten(entry)
        elif item is not None:
            lines.append(str(item))

    flatten(merged.get("script"))
    return "\n".join(lines)


def variables_of(doc: dict, merged: dict) -> dict[str, str]:
    """Global variables, then the job's; {value: ...} entries give their value."""
    result = {}
    for source in (doc.get("variables") or {}, merged.get("variables") or {}):
        for key, value in source.items():
            if isinstance(value, dict):
                value = value.get("value", "")
            result[key] = "" if value is None else str(value)
    return result


def _image_name(image) -> str | None:
    return image.get("name") if isinstance(image, dict) else image


def extract(root: Path, entry: str, ci: str, hw: Hardware, env: dict,
            default_pipelines: list[str]) -> tuple[list[Job], list[str]]:
    doc = load(root, entry)
    jobs: list[Job] = []
    warnings: list[str] = []
    for name, own in doc.items():
        if name.startswith(".") or name in KEYWORDS or not isinstance(own, dict):
            continue
        merged, chain = resolve(doc, name)
        variables = variables_of(doc, merged)
        raw_script = script_text(merged)
        script = cmake.expand(raw_script, variables)
        job = Job(key=f"{ci}:{name}", ci=ci, name=name, kind=kind_of(merged, script))
        job.disabled = "rules" not in own and rules_template(chain) == ".disable_job_condition"
        job.pipelines = pipelines_of(own, merged, chain, default_pipelines)
        _place(job, merged, chain, doc, hw, warnings)
        if job.kind == "build":
            _configure(job, merged, variables, raw_script, script, env, warnings)
        jobs.append(job)
    return jobs, warnings


def _place(job: Job, merged: dict, chain: list[str], doc: dict, hw: Hardware,
           warnings: list[str]) -> None:
    """The machines the job can run on and the ones it is sent to."""
    for template in chain:
        if template not in doc and template not in hw.gitlab_templates:
            warnings.append(f"{job.key}: unknown template {template}")
    from_templates = [hw.gitlab_templates[t] for t in chain if t in hw.gitlab_templates]
    if from_templates:
        job.machines, job.dispatched_to = list(from_templates), list(from_templates)
    else:
        tags = merged.get("tags") or []
        job.machines, job.dispatched_to = hw.machines_for_tags(tags)
        if not job.machines and not job.disabled:
            warnings.append(f"{job.key}: no runner matches the tags {tags}")
    job.site = hw.site_of(job.dispatched_to or job.machines)


def _configure(job: Job, merged: dict, variables: dict[str, str], raw_script: str,
               script: str, env: dict, warnings: list[str]) -> None:
    """The build configuration and toolchain versions of a build job."""
    flags = cmake.parse_flags(script)
    if "EXTRA_CMAKE_FLAGS" not in raw_script:
        # e.g. HoreKa, where .gitlab/build-and-test.sh passes them to CMake
        extra = cmake.expand(variables.get("EXTRA_CMAKE_FLAGS", ""), variables)
        flags.update(cmake.parse_flags(extra))
    if "CMAKE_BUILD_TYPE" not in flags and variables.get("BUILD_TYPE"):
        flags["CMAKE_BUILD_TYPE"] = variables["BUILD_TYPE"]
    image = _image_name(merged.get("image"))
    configured = toolchain.merge(
        toolchain.versions_from_modules(variables.get("MODULE_LOAD") or variables.get("MODULES")),
        env["images"].get(variables.get("UENV") or image or "", {}),
        toolchain.versions_from_tokens(image),
    )
    if not job.disabled:
        warnings.extend(toolchain.name_mismatches(job.name, configured))
    versions = toolchain.merge(env["jobs"].get(job.key, {}), configured,
                               toolchain.versions_from_tokens(job.name))
    apply_build(job, flags, versions, variables.get("CXX_COMPILER") or variables.get("CXX"))
    job.compile_only = not TEST_COMMAND.search(script)
    if not job.disabled:
        warnings.extend(missing_versions(job))
