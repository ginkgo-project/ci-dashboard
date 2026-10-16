// Pure functions behind the dashboard page; tested with `node --test tests/js/*.test.js`.

export const STATUS_ORDER = ["failed", "canceled", "notrun", "pending", "running", "success"];
export const SETTINGS = ["CI", "site", "machine", "kind", "pipeline", "build type", "linkage", "MPI", "OpenMP", "precision", "toolchain"];

const NAME_ORDER = ["cuda", "rocm", "oneapi", "gcc", "clang", "nvhpc", "appleclang", "msvc"];
const MAJOR_ONLY = ["gcc", "clang", "appleclang"];
const NOT_RUN = ["skipped", "manual", "created", "scheduled"];
const PENDING = ["pending", "waiting_for_resource", "preparing"];
// failure reasons that come from the machine, not from the toolchain
const INFRASTRUCTURE = ["disk", "runner", "stuck", "timeout", "slurm-timeout"];

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
        const mark = tested.get(version) ?? { version, hardware: false, failedJobs: [] };
        mark.hardware ||= !job.compile_only;
        const latest = latestResult(status?.jobs?.[job.key]);
        if (effectiveStatus(latest) === "failed" && !INFRASTRUCTURE.includes(latest.reason)
            && !mark.failedJobs.some((failed) => failed.name === job.name)) {
          mark.failedJobs.push({ name: job.name, url: latest.url });
        }
        tested.set(version, mark);
      }
    }
    const marks = [...tested.values()]
      .sort((a, b) => compareVersions(a.version, b.version))
      .map((mark) => ({
        ...mark,
        failed: mark.failedJobs.length > 0,
        below: compareVersions(mark.version, range.min) < 0,
        above: range.max ? compareVersions(mark.version, range.max) > 0 : false,
      }));
    placeMarks(marks, range);
    return { name, min: range.min, max: range.max ?? null, tested: marks };
  });
}

// marks closer than this (as a fraction of the line) put their labels on
// alternate sides of the line
const LABEL_GAP = 0.06;

// Sets each mark's position on its line, from 0 at min to 1 at max (or at the
// newest tested version without a max), and null outside the range; and
// whether its label goes below the line, to keep it clear of its neighbours.
function placeMarks(marks, range) {
  const inside = marks.filter((mark) => !mark.below && !mark.above);
  const versions = [range.min, range.max, ...inside.map((mark) => mark.version)].filter(Boolean);
  // the minor version as a fraction of a major one, scaled so the largest
  // minor on the line (e.g. 51 in msvc 19.51) still stays below the next major
  const minor = (version) => Number(String(version).split(".")[1] ?? 0) || 0;
  const scale = 10 ** String(Math.max(...versions.map(minor))).length;
  const value = (version) => Number(String(version).split(".")[0]) + minor(version) / scale;
  const low = value(range.min);
  const high = value(range.max ?? inside.at(-1)?.version ?? range.min);
  let lastAbove = -Infinity;
  let lastBelow = -Infinity;
  for (const mark of marks) {
    mark.position = inside.includes(mark) ? (high > low ? (value(mark.version) - low) / (high - low) : 0) : null;
    mark.labelBelow = false;
    if (mark.position === null) continue;
    mark.labelBelow = mark.position - lastAbove < LABEL_GAP && mark.position - lastBelow >= LABEL_GAP;
    if (mark.labelBelow) lastBelow = mark.position;
    else lastAbove = mark.position;
  }
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

// pull requests without a clang-tidy run, e.g. not pushed to since the job
// was added, go last
const TIDY_ORDER = ["failed", "canceled", "pending", "running", "success", "notrun"];

// The open pull requests with the status of their clang-tidy run: failing ones
// first, then the most recently updated.
export function tidyPulls(status) {
  return (status?.clang_tidy?.pulls ?? [])
    .map((pull) => ({ ...pull, status: effectiveStatus(pull.result) }))
    .sort((a, b) => TIDY_ORDER.indexOf(a.status) - TIDY_ORDER.indexOf(b.status)
      || Date.parse(b.updated_at) - Date.parse(a.updated_at));
}

// findings grouped by check, the check with the most findings first
export function groupFindings(findings) {
  const groups = new Map();
  for (const finding of findings ?? []) {
    if (!groups.has(finding.check)) groups.set(finding.check, []);
    groups.get(finding.check).push(finding);
  }
  return [...groups].map(([check, items]) => ({ check, findings: items }))
    .sort((a, b) => b.findings.length - a.findings.length || a.check.localeCompare(b.check));
}

// for each check, its findings and the pull requests they are in
export function checkTotals(pulls) {
  const totals = new Map();
  for (const pull of pulls) {
    for (const { check, findings } of groupFindings(pull.findings)) {
      const total = totals.get(check) ?? { check, findings: 0, pulls: 0 };
      total.findings += findings.length;
      total.pulls += 1;
      totals.set(check, total);
    }
  }
  return [...totals.values()]
    .sort((a, b) => b.pulls - a.pulls || b.findings - a.findings || a.check.localeCompare(b.check));
}

// the documentation of a clang-tidy check; compiler diagnostics have none
export function checkDocsUrl(check) {
  if (check.startsWith("clang-diagnostic-")) return null;
  const module = check.startsWith("clang-analyzer-") ? "clang-analyzer" : check.split("-")[0];
  return `https://clang.llvm.org/extra/clang-tidy/checks/${module}/${check.slice(module.length + 1)}.html`;
}

// the line of a finding in the newest commit of its pull request
export function findingUrl(pull, finding) {
  const repo = /^(https:\/\/github\.com\/[^/]+\/[^/]+)\/pull\/\d+$/.exec(pull.url);
  if (!repo || finding.path.startsWith("/")) return null;
  return `${repo[1]}/blob/${pull.sha}/${finding.path}#L${finding.line}`;
}

// pull requests whose coverage job is still going come right after the ones
// with Codecov's numbers
const COVERAGE_ORDER = ["running", "pending", "failed", "canceled", "success", "notrun"];

// The open pull requests with the status of their coverage job: the ones with
// Codecov's numbers first, then by status, then the most recently updated.
export function coveragePulls(status) {
  return (status?.code_coverage?.pulls ?? [])
    .map((pull) => ({ ...pull, status: effectiveStatus(pull.result) }))
    .sort((a, b) => Boolean(b.codecov) - Boolean(a.codecov)
      || COVERAGE_ORDER.indexOf(a.status) - COVERAGE_ORDER.indexOf(b.status)
      || Date.parse(b.updated_at) - Date.parse(a.updated_at));
}

// develop's reports, oldest first, each with its change from the one before
// in percentage points
export function coverageHistory(status) {
  const reports = [...(status?.code_coverage?.develop ?? [])].reverse();
  return reports.map((report, i) => ({ ...report, change: i ? report.coverage - reports[i - 1].coverage : null }));
}

export const formatCount = (count) => count.toLocaleString("en-US");

export function formatChange(change) {
  if (change === null) return "";
  const rounded = change.toFixed(2);
  return Number(rounded) > 0 ? `+${rounded}` : Number(rounded) < 0 ? `−${rounded.slice(1)}` : "0.00";
}

export function changedLinesText(changed) {
  if (!changed) return "Codecov has not compared it with develop yet";
  if (!changed.lines) return "changes no lines the tests can run";
  const percent = ((100 * changed.hits) / changed.lines).toFixed(1);
  const partly = changed.partials ? `, ${formatCount(changed.partials)} partly` : "";
  return `${formatCount(changed.hits)} of ${formatCount(changed.lines)} changed lines covered (${percent}%)${partly}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY = 86_400_000;

// a step for the percent axis that gives at most 8 ticks
function percentStep(range) {
  return [1, 2, 5, 10, 20].find((step) => range / step <= 8) ?? 25;
}

// Labels along the time axis: the first day of every month, or of every
// few months so that at most 6 fit; with less than two months in range,
// the first and last day.
function timeTicks(start, end) {
  const first = new Date(start);
  const months = [];
  for (let month = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 1)); month <= end;
    month = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + 1, 1))) {
    months.push(month);
  }
  if (months.length < 2) {
    const day = (time) => { const d = new Date(time); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`; };
    return end - start < DAY ? [{ time: start, label: day(start) }]
      : [{ time: start, label: day(start) }, { time: end, label: day(end) }];
  }
  const every = Math.ceil(months.length / 6);
  return months.filter((_, i) => i % every === 0).map((month) => ({
    time: month.getTime(),
    label: month.getUTCMonth() === 0 || month === months[0]
      ? `${MONTHS[month.getUTCMonth()]} ${month.getUTCFullYear()}` : MONTHS[month.getUTCMonth()],
  }));
}

// The develop chart in a width x height box: one point per report, placed
// by date and coverage, the percent axis on the left and the dates below.
export function chartModel(reports, { width = 800, height = 240, left = 48, right = 16, top = 12, bottom = 28 } = {}) {
  if (!reports.length) return null;
  const times = reports.map((report) => Date.parse(report.date));
  const values = reports.map((report) => report.coverage);
  const low = Math.max(0, Math.floor(Math.min(...values)) - 1);
  const high = Math.min(100, Math.ceil(Math.max(...values)) + 1);
  const start = Math.min(...times);
  const end = Math.max(...times);
  const x = (time) => left + (end > start ? (time - start) / (end - start) : 0.5) * (width - left - right);
  const y = (value) => top + ((high - value) / (high - low)) * (height - top - bottom);
  const points = reports.map((report, i) => ({ x: x(times[i]), y: y(values[i]), report }));
  const step = percentStep(high - low);
  const yTicks = [];
  for (let value = Math.ceil(low / step) * step; value <= high; value += step) yTicks.push({ y: y(value), label: `${value}%` });
  return {
    width, height, left, right, top, bottom, points, yTicks,
    xTicks: timeTicks(start, end).map((tick) => ({ x: x(tick.time), label: tick.label })),
    path: points.map((point, i) => `${i ? "L" : "M"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" "),
  };
}
