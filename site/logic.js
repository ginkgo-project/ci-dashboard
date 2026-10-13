// Pure functions behind the dashboard page; tested with `node --test tests/js/*.test.js`.

export const STATUS_ORDER = ["failed", "canceled", "notrun", "pending", "running", "success"];
export const SETTINGS = ["CI", "site", "machine", "kind", "pipeline", "build type", "linkage", "MPI", "OpenMP", "precision", "toolchain"];

const NAME_ORDER = ["cuda", "rocm", "oneapi", "gcc", "clang", "nvhpc", "appleclang", "msvc"];
const MAJOR_ONLY = ["gcc", "clang", "appleclang"];
const NOT_RUN = ["skipped", "manual", "created", "scheduled"];
const PENDING = ["pending", "waiting_for_resource", "preparing"];

const finishedAt = (result) => Date.parse(result.finished_at ?? "") || 0;

// The newest result that actually ran: the newest one on develop or the one
// from another branch, whichever finished later; otherwise whatever develop
// has (e.g. skipped).
export function latestResult(entry) {
  if (!entry) return null;
  const ran = entry.history.find((result) => result && !NOT_RUN.includes(result.status)) ?? null;
  const other = entry.elsewhere ?? null;
  if (ran && other) return finishedAt(other) > finishedAt(ran) ? other : ran;
  return ran ?? other ?? entry.history.find((result) => result) ?? null;
}

export function effectiveStatus(result) {
  if (!result || NOT_RUN.includes(result.status)) return "notrun";
  if (PENDING.includes(result.status)) return "pending";
  return STATUS_ORDER.includes(result.status) ? result.status : "notrun";
}

export function shortVersion(name, version) {
  if (!version) return "?";
  const parts = String(version).split(".");
  return parts.slice(0, MAJOR_ONLY.includes(name) ? 1 : 2).join(".");
}

export function toolchainLabel(job) {
  const toolchain = job.device ?? job.compiler;
  return toolchain ? `${toolchain.name} ${shortVersion(toolchain.name, toolchain.version)}` : "n/a";
}

export function columnOf(job, machines) {
  if (job.compile_only) return "compile-only";
  const id = job.dispatched_to[0] ?? job.machines[0];
  return machines[id]?.column ?? "unknown";
}

export function machineLabel(machines, id) {
  if (!id) return "?";
  const machine = machines[id];
  if (!machine) return id;
  const what = machine.gpu ?? machine.arch ?? id;
  return machine.node ? `${what} (${machine.node})` : what;
}

export function precisionLabel(precision) {
  const parts = ["mixed", "half", "bfloat16"].filter((part) => precision[part]);
  return parts.length ? parts.join("+") : "none";
}

export function chipLabel(job) {
  let label = job.build_type === "debug" ? "D" : "R";
  if (job.linkage === "static") label += "S";
  if (job.mpi) label += "M";
  if (job.precision?.half || job.precision?.bfloat16) label += "P";
  return label;
}

export function settingValues(job) {
  const build = job.kind === "build";
  return {
    CI: [job.ci],
    site: [job.site ?? "unknown"],
    // where the job is sent; machine ids, shown with machineLabel on the page
    machine: job.dispatched_to.length ? job.dispatched_to : job.machines.length ? job.machines : ["none"],
    kind: [job.kind],
    pipeline: job.pipelines.length ? job.pipelines : ["none"],
    "build type": [build ? job.build_type : "n/a"],
    linkage: [build ? job.linkage : "n/a"],
    MPI: [build ? job.mpi ?? "no MPI" : "n/a"],
    OpenMP: [!build ? "n/a" : job.omp === null ? "detected" : job.omp ? "OpenMP" : "no OpenMP"],
    precision: [build && job.precision ? precisionLabel(job.precision) : "n/a"],
    toolchain: [build ? toolchainLabel(job) : "n/a"],
  };
}

export function countSettings(jobs) {
  const counts = Object.fromEntries(SETTINGS.map((setting) => [setting, {}]));
  for (const job of jobs) {
    const values = settingValues(job);
    for (const setting of SETTINGS) {
      for (const value of values[setting]) counts[setting][value] = (counts[setting][value] ?? 0) + 1;
    }
  }
  for (const setting of SETTINGS) {
    counts[setting] = Object.fromEntries(
      Object.entries(counts[setting]).sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true })),
    );
  }
  return counts;
}

export function matchesFilters(job, status, filters) {
  const values = settingValues(job);
  return Object.entries(filters).every(([setting, wanted]) => {
    if (setting === "status") return effectiveStatus(latestResult(status?.jobs?.[job.key])) === wanted;
    return (values[setting] ?? []).includes(wanted);
  });
}

// Workflows outside the CI (formatting, bots, mirroring) only run on pull
// requests and their results are not fetched, so they are listed only when
// their pipeline, "other", is picked in the filters.
const onlyOther = (job) => job.pipelines.length > 0 && job.pipelines.every((p) => p === "other");

export function statusRows(coverage, status, filters = {}) {
  return coverage.jobs
    .filter((job) => job.kind !== "status" && !job.disabled && matchesFilters(job, status, filters))
    .filter((job) => !onlyOther(job) || filters.pipeline === "other")
    .map((job) => {
      const entry = status?.jobs?.[job.key] ?? null;
      const latest = latestResult(entry);
      return { job, entry, latest, status: effectiveStatus(latest), onDevelop: job.pipelines.includes("develop") };
    })
    .sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || a.job.name.localeCompare(b.job.name));
}

export function summary(coverage, status) {
  if (!status || !status.commits.length) return null;
  const jobs = coverage.jobs.filter((job) => job.pipelines.includes("develop") && !job.disabled && job.kind !== "status");
  const newest = (job) => status.jobs[job.key]?.history[0] ?? null;
  return {
    green: jobs.filter((job) => newest(job)?.status === "success").length,
    total: jobs.length,
    ran: jobs.filter((job) => newest(job)).length,
    sha: status.commits[0].sha,
  };
}

export function compareVersions(a, b) {
  const pa = String(a).split(".");
  const pb = String(b).split(".");
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] ?? "0";
    const y = pb[i] ?? "0";
    const nx = Number(x);
    const ny = Number(y);
    const diff = Number.isNaN(nx) || Number.isNaN(ny) ? x.localeCompare(y) : nx - ny;
    if (diff) return Math.sign(diff);
  }
  return 0;
}

function splitLabel(label) {
  const space = label.lastIndexOf(" ");
  return space < 0 ? [label, ""] : [label.slice(0, space), label.slice(space + 1)];
}

// the toolchain of a grid row, e.g. "cuda" for "cuda 12.0"
export const toolchainName = (label) => splitLabel(label)[0];

export function compareToolchainLabels(a, b) {
  const [nameA, versionA] = splitLabel(a);
  const [nameB, versionB] = splitLabel(b);
  const rank = (name) => (NAME_ORDER.includes(name) ? NAME_ORDER.indexOf(name) : NAME_ORDER.length);
  const byName = rank(nameA) - rank(nameB) || nameA.localeCompare(nameB);
  if (byName) return byName;
  if (versionA === "?" || versionB === "?") return (versionA === "?") - (versionB === "?");
  return compareVersions(versionA, versionB);
}

export function gridModel(coverage, status, filters = {}) {
  const jobs = coverage.jobs.filter((job) => job.kind === "build" && !job.disabled && matchesFilters(job, status, filters));
  const rows = [...new Set(jobs.map(toolchainLabel))].sort(compareToolchainLabels);
  const columns = [...coverage.columns];
  const cells = {};
  for (const job of jobs) {
    const column = columnOf(job, coverage.machines);
    if (!columns.includes(column)) columns.push(column);
    const entry = status?.jobs?.[job.key] ?? null;
    const latest = latestResult(entry);
    (cells[`${toolchainLabel(job)}\t${column}`] ??= []).push({
      job,
      latest,
      status: effectiveStatus(latest),
      elsewhere: latest !== null && latest === entry?.elsewhere,
      moved: Boolean(latest?.machine && job.dispatched_to.length && !job.dispatched_to.includes(latest.machine)),
    });
  }
  return { rows, columns, cells, groups: columnGroups(columns, coverage.machines) };
}

const VENDOR_NAMES = { cpu: "CPU", nvidia: "NVIDIA", amd: "AMD", intel: "Intel" };

// The headings over the grid columns: runs of neighbouring columns whose
// machines have the same vendor. Columns without one (compile-only, unknown)
// each get a group without a name.
function columnGroups(columns, machines) {
  const vendorOf = {};
  for (const machine of Object.values(machines)) {
    if (machine.vendor) vendorOf[machine.column] ??= machine.vendor;
  }
  const groups = [];
  for (const column of columns) {
    const vendor = vendorOf[column];
    const name = vendor ? VENDOR_NAMES[vendor] ?? vendor : null;
    const last = groups.at(-1);
    if (name && last?.name === name) last.columns.push(column);
    else groups.push({ name, columns: [column] });
  }
  return groups;
}

export function supportedLines(coverage, status, filters = {}) {
  return Object.entries(coverage.supported).map(([name, range]) => {
    const tested = new Map();
    for (const job of coverage.jobs) {
      if (job.kind !== "build" || job.disabled || !matchesFilters(job, status, filters)) continue;
      for (const toolchain of [job.compiler, job.device]) {
        if (!toolchain || toolchain.name !== name || !toolchain.version) continue;
        const version = shortVersion(name, toolchain.version);
        const mark = tested.get(version) ?? { version, hardware: false, failed: false };
        mark.hardware ||= !job.compile_only;
        mark.failed ||= effectiveStatus(latestResult(status?.jobs?.[job.key])) === "failed";
        tested.set(version, mark);
      }
    }
    const marks = [...tested.values()].sort((a, b) => compareVersions(a.version, b.version));
    return {
      name,
      min: range.min,
      max: range.max ?? null,
      tested: marks.map((mark) => ({
        ...mark,
        below: compareVersions(mark.version, range.min) < 0,
        above: range.max ? compareVersions(mark.version, range.max) > 0 : false,
      })),
    };
  });
}

export function ageLevel(generatedAt, now = new Date()) {
  const hours = (now - new Date(generatedAt)) / 3_600_000;
  if (!(hours <= 24)) return "old";
  return hours > 2 ? "stale" : "fresh";
}

export function shortSha(sha) {
  return sha ? sha.slice(0, 10) : "";
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}
