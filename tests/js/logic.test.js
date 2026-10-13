import { test } from "node:test";
import assert from "node:assert/strict";
import * as logic from "../../site/logic.js";

const machines = {
  "tum-l40s": { site: "TUM", node: "gpu-nvidia", gpu: "NVIDIA L40S", vendor: "nvidia", column: "L40S" },
  "tum-rocinante-nvidia": { site: "TUM", node: "rocinante", gpu: "NVIDIA A100 or A2", vendor: "nvidia", column: "rocinante NVIDIA" },
  "github-x86-64": { site: "GitHub", node: "ubuntu-24.04", gpu: null, vendor: "cpu", arch: "x86-64", column: "x86-64" },
};

function job(key, extra = {}) {
  const [ci, name] = key.split(":");
  return {
    key, ci, name, kind: "build", site: "TUM", pipelines: ["develop", "pr-full"],
    compiler: { name: "gcc", version: "12.4.0" }, device: null, mpi: null, omp: true,
    build_type: "release", linkage: "shared", precision: { mixed: true, half: true, bfloat16: false },
    fast_tests: false, nondefault_stream: false,
    machines: ["tum-l40s", "tum-rocinante-nvidia"], dispatched_to: ["tum-rocinante-nvidia"],
    compile_only: false, disabled: false, ...extra,
  };
}

const result = (status, extra = {}) => ({
  sha: "aaa", ref: "develop", status, reason: null, machine: "tum-rocinante-nvidia",
  duration_s: 600, tests: null, url: "https://gitlab.com/j/1", ...extra,
});

const coverage = {
  machines,
  columns: ["x86-64", "rocinante NVIDIA", "L40S", "compile-only"],
  supported: { gcc: { min: "9", max: "16" }, cuda: { min: "11.0" } },
  jobs: [
    job("gitlab:build/cuda120", { device: { name: "cuda", version: "12.0.1" }, linkage: "static", mpi: "openmpi" }),
    job("gitlab:build/cuda118", { device: { name: "cuda", version: "11.8.0" }, compiler: { name: "gcc", version: "9.5.0" }, build_type: "debug" }),
    job("gitlab:build/gcc9", { compiler: { name: "gcc", version: "9" }, machines: ["github-x86-64"], dispatched_to: ["github-x86-64"] }),
    job("github:cuda-compile", { device: { name: "cuda", version: "13.3" }, compiler: { name: "gcc", version: "13.3" }, compile_only: true, pipelines: ["develop", "pr-quick"], machines: ["github-x86-64"], dispatched_to: ["github-x86-64"], site: "GitHub" }),
    job("cscs:daint/gh200", { device: { name: "cuda", version: null }, pipelines: ["pr-cscs"], machines: ["cscs-gh200"], dispatched_to: ["cscs-gh200"], site: "CSCS" }),
    job("gitlab:sync", { kind: "status", compiler: null, precision: null, build_type: null, linkage: null, omp: null }),
    job("gitlab:disabled", { disabled: true, pipelines: [] }),
    job("github:check-format", { kind: "check", pipelines: ["other"], compiler: null, precision: null, build_type: null, linkage: null, omp: null, machines: [], dispatched_to: [], site: "GitHub" }),
  ],
};

const status = {
  generated_at: "2026-10-12T08:00:00+00:00",
  commits: [{ sha: "aaa", title: "newest" }, { sha: "bbb", title: "older" }],
  jobs: {
    "gitlab:build/cuda120": { history: [result("failed", { reason: "disk" }), result("success", { sha: "bbb" })], elsewhere: null },
    "gitlab:build/cuda118": { history: [null, result("success", { sha: "bbb", machine: "tum-l40s" })], elsewhere: null },
    "gitlab:build/gcc9": { history: [result("success"), null], elsewhere: null },
    "github:cuda-compile": { history: [result("skipped"), null], elsewhere: null },
    "cscs:daint/gh200": { history: [null, null], elsewhere: result("success", { ref: "PR #2114", machine: null }) },
  },
  unmatched: [],
};

const byKey = Object.fromEntries(coverage.jobs.map((j) => [j.key, j]));

test("latestResult prefers develop, then elsewhere", () => {
  assert.equal(logic.latestResult(status.jobs["gitlab:build/cuda120"]).status, "failed");
  assert.equal(logic.latestResult(status.jobs["gitlab:build/cuda118"]).sha, "bbb");
  assert.equal(logic.latestResult(status.jobs["cscs:daint/gh200"]).ref, "PR #2114");
  assert.equal(logic.latestResult(undefined), null);
});

test("latestResult prefers a real result elsewhere over a skipped or manual one on develop", () => {
  const manualOnDevelop = { history: [result("manual"), null], elsewhere: result("failed", { ref: "rebased/pr-2099" }) };
  assert.equal(logic.latestResult(manualOnDevelop).ref, "rebased/pr-2099");
  const onlySkipped = { history: [result("skipped"), null], elsewhere: null };
  assert.equal(logic.latestResult(onlySkipped).status, "skipped");
});

test("effectiveStatus folds not-run states", () => {
  assert.equal(logic.effectiveStatus(null), "notrun");
  assert.equal(logic.effectiveStatus(result("skipped")), "notrun");
  assert.equal(logic.effectiveStatus(result("manual")), "notrun");
  assert.equal(logic.effectiveStatus(result("waiting_for_resource")), "pending");
  assert.equal(logic.effectiveStatus(result("failed")), "failed");
});

test("labels survive missing data", () => {
  assert.equal(logic.shortVersion("gcc", "12.4.0"), "12");
  assert.equal(logic.shortVersion("cuda", "12.0.1"), "12.0");
  assert.equal(logic.shortVersion("oneapi", "2024.2.1"), "2024.2");
  assert.equal(logic.shortVersion("rocm", null), "?");
  assert.equal(logic.toolchainLabel(byKey["gitlab:build/cuda120"]), "cuda 12.0");
  assert.equal(logic.toolchainLabel(byKey["gitlab:build/gcc9"]), "gcc 9");
  assert.equal(logic.toolchainLabel(byKey["cscs:daint/gh200"]), "cuda ?");
  assert.equal(logic.toolchainLabel(byKey["gitlab:sync"]), "n/a");
  assert.equal(logic.columnOf(byKey["gitlab:build/cuda120"], machines), "rocinante NVIDIA");
  assert.equal(logic.columnOf(byKey["github:cuda-compile"], machines), "compile-only");
  assert.equal(logic.columnOf(byKey["cscs:daint/gh200"], machines), "unknown");
  assert.equal(logic.machineLabel(machines, "tum-l40s"), "NVIDIA L40S (gpu-nvidia)");
  assert.equal(logic.machineLabel(machines, "github-x86-64"), "x86-64 (ubuntu-24.04)");
  assert.equal(logic.machineLabel(machines, "cscs-gh200"), "cscs-gh200");
  assert.equal(logic.machineLabel(machines, null), "?");
  assert.equal(logic.chipLabel(byKey["gitlab:build/cuda120"]), "RSMP");
  assert.equal(logic.chipLabel(byKey["gitlab:build/cuda118"]), "DP");
});

test("statusRows sorts failures first and applies filters", () => {
  const keys = logic.statusRows(coverage, status, {}).map((row) => row.job.key);
  assert.deepEqual(keys, ["gitlab:build/cuda120", "github:cuda-compile", "gitlab:build/cuda118", "gitlab:build/gcc9", "cscs:daint/gh200"]);
  assert.equal(logic.statusRows(coverage, status, { status: "success" }).length, 3);
  assert.deepEqual(logic.statusRows(coverage, status, { pipeline: "pr-cscs" }).map((r) => r.job.key), ["cscs:daint/gh200"]);
  assert.equal(logic.statusRows(coverage, status, { pipeline: "pr-cscs" })[0].onDevelop, false);
  assert.deepEqual(logic.statusRows(coverage, null, {}).map((r) => r.status), ["notrun", "notrun", "notrun", "notrun", "notrun"]);
});

test("statusRows leaves out checks without results unless their pipeline is picked", () => {
  assert.ok(!logic.statusRows(coverage, status, {}).some((row) => row.job.key === "github:check-format"));
  assert.deepEqual(logic.statusRows(coverage, status, { pipeline: "other" }).map((row) => row.job.key), ["github:check-format"]);
});

test("summary counts the newest commit only", () => {
  assert.deepEqual(logic.summary(coverage, status), { green: 1, total: 4, ran: 3, sha: "aaa" });
  assert.equal(logic.summary(coverage, null), null);
});

test("gridModel places jobs and flags results from elsewhere and moved jobs", () => {
  const model = logic.gridModel(coverage, status, {});
  assert.deepEqual(model.rows, ["cuda 11.8", "cuda 12.0", "cuda 13.3", "cuda ?", "gcc 9"]);
  assert.deepEqual(model.columns, ["x86-64", "rocinante NVIDIA", "L40S", "compile-only", "unknown"]);
  const failed = model.cells["cuda 12.0\trocinante NVIDIA"][0];
  assert.equal(failed.status, "failed");
  assert.equal(failed.moved, false);
  assert.equal(model.cells["cuda 11.8\trocinante NVIDIA"][0].moved, true);
  assert.equal(model.cells["cuda ?\tunknown"][0].elsewhere, true);
  assert.equal(model.cells["cuda 13.3\tcompile-only"][0].status, "notrun");
  assert.deepEqual(logic.gridModel(coverage, status, { linkage: "static" }).rows, ["cuda 12.0"]);
});

test("gridModel groups neighbouring columns by the vendor of their machines", () => {
  const groups = logic.gridModel(coverage, status, {}).groups.map((g) => [g.name, g.columns]);
  assert.deepEqual(groups, [
    ["CPU", ["x86-64"]],
    ["NVIDIA", ["rocinante NVIDIA", "L40S"]],
    [null, ["compile-only"]],
    [null, ["unknown"]],
  ]);
  // a vendor whose columns are not next to each other gets two groups
  const split = logic.gridModel({ ...coverage, columns: ["L40S", "x86-64", "rocinante NVIDIA", "compile-only"] }, status, {});
  assert.deepEqual(split.groups.map((g) => g.name), ["NVIDIA", "CPU", "NVIDIA", null, null]);
});

test("toolchainName drops the version from a grid row", () => {
  assert.deepEqual(logic.gridModel(coverage, status, {}).rows.map(logic.toolchainName), ["cuda", "cuda", "cuda", "cuda", "gcc"]);
  assert.equal(logic.toolchainName("oneapi 2024.2"), "oneapi");
  assert.equal(logic.toolchainName("n/a"), "n/a");
});

test("countSettings counts every value", () => {
  const builds = coverage.jobs.filter((j) => j.kind === "build" && !j.disabled);
  const counts = logic.countSettings(builds);
  assert.deepEqual(counts.linkage, { shared: 4, static: 1 });
  assert.deepEqual(counts.MPI, { "no MPI": 4, openmpi: 1 });
  assert.deepEqual(counts.pipeline, { develop: 4, "pr-cscs": 1, "pr-full": 3, "pr-quick": 1 });
});

test("supportedLines marks tested versions", () => {
  const [gcc, cuda] = logic.supportedLines(coverage, status);
  assert.equal(gcc.name, "gcc");
  // gcc 12 is not red: cuda120 failed because the disk was full
  assert.deepEqual(gcc.tested.map((t) => [t.version, t.hardware, t.failed]), [["9", true, false], ["12", true, false], ["13", false, false]]);
  assert.deepEqual(cuda.tested.map((t) => t.version), ["11.8", "12.0", "13.3"]);
  assert.equal(cuda.max, null);
  const [low] = logic.supportedLines({ ...coverage, supported: { gcc: { min: "10", max: "12" } } }, status);
  assert.deepEqual(low.tested.map((t) => [t.version, t.below, t.above]), [["9", true, false], ["12", false, false], ["13", false, true]]);
});

test("supportedLines marks failures red unless the machine caused them, and names the failing jobs and their logs", () => {
  const failing = { ...status, jobs: { ...status.jobs,
    "gitlab:build/gcc9": { history: [result("failed", { reason: "tests", url: "https://gitlab.com/j/9" }), null], elsewhere: null },
    // GitHub failures have no reason
    "github:cuda-compile": { history: [result("failed", { reason: null, url: "https://github.com/j/13" }), null], elsewhere: null },
  } };
  const [gcc, cuda] = logic.supportedLines(coverage, failing);
  const mark = (line, version) => line.tested.find((t) => t.version === version);
  assert.deepEqual([mark(gcc, "9").failed, mark(gcc, "9").failedJobs], [true, [{ name: "build/gcc9", url: "https://gitlab.com/j/9" }]]);
  assert.deepEqual([mark(cuda, "13.3").failed, mark(cuda, "13.3").failedJobs], [true, [{ name: "cuda-compile", url: "https://github.com/j/13" }]]);
  // full disk
  assert.deepEqual([mark(cuda, "12.0").failed, mark(cuda, "12.0").failedJobs], [false, []]);
});

test("supportedLines places the marks by version number", () => {
  const places = (line) => line.tested.map((t) => [t.version, t.position === null ? null : Number(t.position.toFixed(3))]);
  const [gcc, cuda] = logic.supportedLines(coverage, status);
  assert.deepEqual(places(gcc), [["9", 0], ["12", 0.429], ["13", 0.571]]);
  // without a max, the line ends at the newest tested version
  assert.deepEqual(places(cuda), [["11.8", 0.348], ["12.0", 0.435], ["13.3", 1]]);
  // versions outside the range are not on the line
  const [low] = logic.supportedLines({ ...coverage, supported: { gcc: { min: "10", max: "12" } } }, status);
  assert.deepEqual(places(low), [["9", null], ["12", 1], ["13", null]]);
  // two-digit minors stay below the next major: 19.44 between 19.20 and 19.51
  const msvc = { ...coverage, supported: { msvc: { min: "19.20" } }, jobs: [
    job("github:old", { compiler: { name: "msvc", version: "19.44" } }),
    job("github:new", { compiler: { name: "msvc", version: "19.51" } }),
  ] };
  assert.deepEqual(places(logic.supportedLines(msvc, null)[0]), [["19.44", 0.774], ["19.51", 1]]);
});

test("supportedLines puts the label of a mark close to the previous one below the line", () => {
  const [cuda] = logic.supportedLines({ ...coverage, supported: { cuda: { min: "11.0", max: "30.0" } } }, status);
  // 11.8 and 12.0 are close on a line up to 30.0; 13.3 is far enough from 11.8
  assert.deepEqual(cuda.tested.map((t) => [t.version, t.labelBelow]), [["11.8", false], ["12.0", true], ["13.3", false]]);
});

test("supportedLines only counts the jobs that match the filters", () => {
  const versions = (filters) => logic.supportedLines(coverage, status, filters).map((line) => line.tested.map((t) => t.version));
  assert.deepEqual(versions({ site: "GitHub" }), [["13"], ["13.3"]]);
  assert.deepEqual(versions({ status: "failed" }), [["12"], ["12.0"]]);
  // a toolchain without matching jobs keeps its line, with nothing tested
  assert.deepEqual(versions({ site: "CSCS" }), [["12"], []]);
});

test("small helpers", () => {
  const now = new Date("2026-10-12T09:00:00Z");
  assert.equal(logic.ageLevel("2026-10-12T08:00:00Z", now), "fresh");
  assert.equal(logic.ageLevel("2026-10-12T06:00:00Z", now), "stale");
  assert.equal(logic.ageLevel("2026-10-11T08:00:00Z", now), "old");
  assert.equal(logic.ageLevel("not a date", now), "old");
  assert.equal(logic.compareVersions("12.10", "12.9"), 1);
  assert.equal(logic.compareVersions("9", "9.0"), 0);
  assert.equal(logic.formatDuration(null), "");
  assert.equal(logic.formatDuration(600), "10 min");
  assert.equal(logic.formatDuration(5400), "1 h 30 min");
  assert.equal(logic.shortSha("0123456789abcdef"), "0123456789");
  assert.equal(logic.shortSha(null), "");
});

test("latestResult takes the newer of a develop result and a result elsewhere", () => {
  const horeka = {
    history: [result("manual"), result("success", { finished_at: "2026-10-04T10:00:00Z" })],
    elsewhere: result("failed", { ref: "rebased/pr-2099", finished_at: "2026-10-08T10:00:00Z" }),
  };
  assert.equal(logic.latestResult(horeka).ref, "rebased/pr-2099");
  const developNewer = { ...horeka, elsewhere: { ...horeka.elsewhere, finished_at: "2026-10-01T10:00:00Z" } };
  assert.equal(logic.latestResult(developNewer).status, "success");
});

test("the machine filter matches the machines a job is sent to", () => {
  assert.deepEqual(logic.settingValues(byKey["gitlab:build/cuda120"]).machine, ["tum-rocinante-nvidia"]);
  assert.deepEqual(logic.settingValues(byKey["github:check-format"]).machine, ["none"]);
  assert.deepEqual(logic.statusRows(coverage, status, { machine: "github-x86-64" }).map((r) => r.job.key),
    ["github:cuda-compile", "gitlab:build/gcc9"]);
  const builds = coverage.jobs.filter((j) => j.kind === "build" && !j.disabled);
  assert.deepEqual(logic.countSettings(builds).machine, { "cscs-gh200": 1, "github-x86-64": 2, "tum-rocinante-nvidia": 2 });
});
