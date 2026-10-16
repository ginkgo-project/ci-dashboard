// Renders the dashboard from coverage.json and status.json. All text goes
// through textContent (the el helper), so job names cannot inject markup.
import {
  STATUS_ORDER, effectiveStatus, countSettings, statusRows, summary,
  gridModel, chipLabel, supportedLines, ageLevel, shortSha, formatDuration, machineLabel, toolchainName,
  tidyPulls, groupFindings, checkTotals, checkDocsUrl, findingUrl,
  coveragePulls, coverageHistory, chartModel, changedLinesText, formatChange, formatCount,
} from "./logic.js";

// pull: the pull request picked by #clang-tidy/NUMBER
const state = { coverage: null, status: null, filters: {}, view: "status", pull: null };
const VIEWS = {
  status: renderStatus, coverage: renderCoverage, supported: renderSupported,
  "clang-tidy": renderClangTidy, "code-coverage": renderCodeCoverage,
};
// the filters pick jobs; these views list pull requests and commits
const WITHOUT_FILTERS = ["clang-tidy", "code-coverage"];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const isWebLink = (url) => typeof url === "string" && url.startsWith("https://");

function showBanner(level, text) {
  document.getElementById("banners").append(el("p", { class: `banner ${level}`, role: "status" }, text));
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function setFilter(setting, value) {
  if (value === "") delete state.filters[setting];
  else state.filters[setting] = value;
  render();
}

function renderMeta() {
  const { coverage, status } = state;
  const meta = document.getElementById("meta");
  if (status) {
    const level = ageLevel(status.generated_at);
    meta.append(el("span", { class: `age ${level}` }, `Results from ${new Date(status.generated_at).toLocaleString()}`));
    if (level === "old") showBanner("error", "The job results are more than a day old: the update workflow may be failing or disabled.");
  }
  meta.append(el("span", {}, `CI configuration of develop at ${shortSha(coverage.ginkgo_commit) || "unknown commit"}`));
  if (coverage.warnings.length) {
    meta.append(el("details", { class: "warnings" },
      el("summary", {}, `${coverage.warnings.length} configuration warnings`),
      el("ul", {}, coverage.warnings.map((warning) => el("li", {}, warning)))));
  }
}

// machine ids are shown with their GPU or architecture and node
function valueText(setting, value) {
  return setting === "machine" ? machineLabel(state.coverage.machines, value) : value;
}

// the values of a setting with their counts, in the order of their shown text
function sortedValues(setting, values) {
  return Object.entries(values).sort(([a], [b]) =>
    valueText(setting, a).localeCompare(valueText(setting, b), undefined, { numeric: true }));
}

function renderFilters() {
  const form = document.getElementById("filters");
  form.replaceChildren();
  const counts = countSettings(state.coverage.jobs.filter((job) => job.kind !== "status"));
  const options = { ...counts, status: Object.fromEntries(STATUS_ORDER.map((s) => [s, null])) };
  for (const [setting, values] of Object.entries(options)) {
    const id = `filter-${setting.replace(/\W+/g, "-")}`;
    form.append(el("label", { for: id }, setting,
      el("select", { id, onchange: (event) => setFilter(setting, event.target.value) },
        el("option", { value: "" }, "all"),
        sortedValues(setting, values).map(([value, count]) => el("option", { value, selected: state.filters[setting] === value },
          count === null ? value : `${valueText(setting, value)} (${count})`)))));
  }
  if (Object.keys(state.filters).length) {
    form.append(el("button", { type: "button", onclick: () => { state.filters = {}; render(); } }, "Clear filters"));
  }
}

function historyStrip(entry) {
  const { status } = state;
  if (!entry || !status) return "";
  return el("span", { class: "strip", "aria-label": "results of the last commits, oldest first" },
    entry.history.map((result, i) => {
      const s = effectiveStatus(result);
      const commit = status.commits[i];
      return el("span", { class: `dot s-${s}`, title: `${shortSha(commit.sha)} ${commit.title}: ${s}` });
    }).reverse());
}

function statusTable(rows, onDevelop) {
  const { coverage, status } = state;
  const head = ["Job", "Result", "Reason", "Ran on", "Tests", "Duration",
    onDevelop ? `Last ${status?.commits.length ?? 0} commits` : "Branch", "Log"];
  return el("div", { class: "scroll" }, el("table", { class: "jobs" },
    el("thead", {}, el("tr", {}, head.map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, rows.map(({ job, entry, latest, status: result }) => el("tr", {},
      el("th", { scope: "row" }, job.name),
      el("td", {}, el("span", { class: `badge s-${result}` }, result)),
      el("td", {}, latest?.reason ?? ""),
      el("td", {}, machineLabel(coverage.machines, latest?.machine ?? job.dispatched_to[0] ?? job.machines[0])),
      el("td", {}, latest?.tests ? `${latest.tests.total - latest.tests.failed}/${latest.tests.total}` : ""),
      el("td", {}, formatDuration(latest?.duration_s)),
      el("td", {}, onDevelop ? historyStrip(entry) : latest?.ref ?? ""),
      el("td", {}, latest && isWebLink(latest.url) ? el("a", { href: latest.url }, "log") : ""))))));
}

function renderStatus(root) {
  const { coverage, status } = state;
  const s = summary(coverage, status);
  root.append(el("p", { class: "summary" }, s
    ? `${s.green} of ${s.total} develop jobs green at ${shortSha(s.sha)}${s.total > s.ran ? `; ${s.total - s.ran} without a result for this commit yet` : ""}`
    : "No job results available."));
  const rows = statusRows(coverage, status, state.filters);
  root.append(el("h2", {}, "Jobs on develop"), statusTable(rows.filter((row) => row.onDevelop), true));
  const others = rows.filter((row) => !row.onDevelop);
  if (others.length) root.append(el("h2", {}, "Jobs that only run on pull requests"), statusTable(others, false));
  if (status?.unmatched.length) {
    root.append(el("h2", {}, "Results of jobs that are not in the configuration"),
      el("ul", { class: "unmatched" }, status.unmatched.map((item) => el("li", {},
        isWebLink(item.url) ? el("a", { href: item.url }, item.key) : item.key, ` (${item.status})`))));
  }
}

function chip({ job, latest, status, elsewhere, moved }) {
  const machines = state.coverage.machines;
  const names = (ids) => ids.map((id) => machineLabel(machines, id)).join("; ") || "?";
  const title = [
    job.name,
    `${job.build_type}, ${job.linkage}, MPI: ${job.mpi ?? "no"}, OpenMP: ${job.omp ?? "detected"}`,
    `Can run on: ${names(job.machines)}`,
    `Sent to: ${names(job.dispatched_to)}`,
    `Result: ${status}${elsewhere && latest?.ref ? ` on ${latest.ref}` : ""}${latest?.machine ? `, ran on ${machineLabel(machines, latest.machine)}` : ""}`,
  ].join("\n");
  const classes = ["chip", `s-${status}`, elsewhere && "elsewhere", moved && "moved"].filter(Boolean).join(" ");
  return latest && isWebLink(latest.url)
    ? el("a", { class: classes, href: latest.url, title }, chipLabel(job))
    : el("span", { class: classes, title }, chipLabel(job));
}

function renderCoverage(root) {
  const { coverage, status } = state;
  const model = gridModel(coverage, status, state.filters);
  root.append(el("p", { class: "legend" },
    "D debug, R release, S static, M MPI, P half or bfloat16. A dashed border marks a result from a pull request, an orange ring a job that last ran on a different machine than the one it is sent to. Hover a chip for details."));
  // a thicker line left of the first column of each vendor group
  const firsts = new Set(model.groups.slice(1).map((group) => group.columns[0]));
  const edge = (column) => (firsts.has(column) ? "group-edge" : null);
  root.append(el("div", { class: "scroll" }, el("table", { class: "grid" },
    el("thead", {},
      el("tr", {},
        el("th", { scope: "col", rowspan: 2 }, "Toolchain"),
        model.groups.map((group) => (group.name
          ? el("th", { scope: "colgroup", colspan: group.columns.length, class: ["vendor", edge(group.columns[0])].filter(Boolean).join(" ") }, group.name)
          : el("th", { scope: "col", rowspan: 2, class: edge(group.columns[0]) }, group.columns[0])))),
      el("tr", {}, model.groups.filter((group) => group.name).map((group) =>
        group.columns.map((column) => el("th", { scope: "col", class: edge(column) }, column))))),
    el("tbody", {}, model.rows.map((row, i) => el("tr", {
      class: i > 0 && toolchainName(row) !== toolchainName(model.rows[i - 1]) ? "group-start" : null,
    },
      el("th", { scope: "row" }, row),
      model.columns.map((column) => el("td", { class: edge(column) }, (model.cells[`${row}\t${column}`] ?? []).map(chip)))))))));
  root.append(el("h2", {}, "Build settings"));
  const counts = countSettings(coverage.jobs.filter((job) => job.kind === "build" && !job.disabled));
  root.append(el("div", { class: "settings" }, Object.entries(counts).map(([setting, values]) => el("section", {},
    el("h3", {}, setting),
    el("ul", {}, sortedValues(setting, values).map(([value, count]) => el("li", {},
      el("button", {
        type: "button",
        class: state.filters[setting] === value ? "active" : null,
        onclick: () => setFilter(setting, state.filters[setting] === value ? "" : value),
      }, `${valueText(setting, value)} `, el("span", { class: "count" }, String(count))))))))));
}

function renderSupported(root) {
  root.append(el("p", { class: "legend" },
    "Marks sit by version number; a line without a max ends at its newest tested version. Filled: tests run on hardware. Hollow: compiled only. Red: a job with this version fails, not counting a full disk, a timeout or a runner problem; hover a red mark for the jobs, click it for the log. Versions outside the supported range sit outside the line."));
  for (const line of supportedLines(state.coverage, state.status, state.filters)) {
    const mark = (t) => {
      // a red mark links to the log of its first failing job
      const log = t.failedJobs.find((failed) => isWebLink(failed.url));
      const attrs = {
        class: ["mark", t.hardware ? "hw" : "compile", t.failed && "failed", t.labelBelow && "label-below"].filter(Boolean).join(" "),
        style: t.position === null ? null : `left: ${(t.position * 100).toFixed(2)}%`,
        title: `${line.name} ${t.version}: ${t.hardware ? "tested on hardware" : "compiled only"}`
          + (t.failed ? `, failing in ${t.failedJobs.map((failed) => failed.name).join(", ")}` : "")
          + (log ? `\nClick for the log of ${log.name}` : ""),
      };
      const label = el("span", { class: "label" }, t.version);
      return log ? el("a", { ...attrs, href: log.url }, label) : el("span", attrs, label);
    };
    const inside = line.tested.filter((t) => !t.below && !t.above);
    root.append(el("section", { class: "range" },
      el("h3", {}, line.name),
      el("div", { class: "line" },
        line.tested.filter((t) => t.below).map(mark),
        el("span", { class: "bound" }, `min ${line.min}`),
        el("span", { class: "track" }, inside.length ? inside.map(mark) : el("span", { class: "none" }, "nothing tested in this range")),
        el("span", { class: "bound" }, line.max ? `max ${line.max}` : "max not set"),
        line.tested.filter((t) => t.above).map(mark))));
  }
}

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

function checkName(check) {
  const docs = checkDocsUrl(check);
  return docs
    ? el("a", { class: "check", href: docs, title: "Documentation of the check" }, check)
    : el("span", { class: "check" }, check);
}

function tidyDetail(pull) {
  const count = pull.findings?.length ?? 0;
  if (count) {
    const partial = pull.reported > count ? ` (the log shows ${count} of ${pull.reported})` : "";
    return `${plural(count, "finding")}${partial}: ${groupFindings(pull.findings).map((group) => group.check).join(", ")}`;
  }
  if (pull.status === "failed" && pull.findings === null) return "the log could not be read; the findings are in the log";
  if (pull.status === "failed") return "failed without findings in its log";
  if (pull.status === "success") return "no findings on the changed lines";
  if (pull.status === "notrun") return pull.result ? "skipped" : "no clang-tidy run for the newest commit";
  return pull.status;
}

function pullLine(pull) {
  return [
    el("span", { class: `badge s-${pull.status}` }, pull.status), " ",
    el("a", { href: pull.url }, `#${pull.number}`), ` ${pull.title}`,
    pull.draft ? el("span", { class: "count" }, " (draft)") : null,
    el("span", { class: "pull-detail" }, tidyDetail(pull)),
    pull.result && isWebLink(pull.result.url) ? el("a", { class: "pull-link", href: pull.result.url }, "log") : null,
    pull.findings?.length ? el("a", { class: "pull-link", href: `#clang-tidy/${pull.number}`, title: "Link to these findings" }, "link") : null,
  ];
}

function findingList(pull) {
  return groupFindings(pull.findings).map(({ check, findings }) => el("section", { class: "check-group" },
    el("h4", {}, checkName(check), el("span", { class: "count" }, ` ${findings.length}`)),
    el("ul", { class: "findings" }, findings.map((finding) => {
      const where = `${finding.path}:${finding.line}:${finding.col}`;
      const url = findingUrl(pull, finding);
      return el("li", {},
        url ? el("a", { class: "where", href: url }, where) : el("span", { class: "where" }, where),
        finding.severity === "error" ? el("span", { class: "badge s-failed" }, "error") : null,
        ` ${finding.message}`);
    }))));
}

function renderClangTidy(root) {
  const tidy = state.status?.clang_tidy;
  if (!tidy) {
    root.append(el("p", { class: "none" }, "No clang-tidy results available."));
    return;
  }
  const pulls = tidyPulls(state.status);
  root.append(el("p", { class: "summary" },
    `${pulls.filter((pull) => pull.findings?.length).length} of ${plural(pulls.length, "open pull request")} with clang-tidy findings`));
  root.append(el("p", { class: "legend" },
    `The job ${tidy.check} runs clang-tidy on the lines a pull request changes. Listed are the open pull requests updated in the last ${tidy.max_age_days} days, with the result for their newest commit. `
    + "The line numbers come from the pull request merged into its target branch; the links open the file at the pull request's newest commit, where a line can be off if the target branch changed the same file. "
    + "Silence a deliberate case with // NOLINT(check) or // NOLINTNEXTLINE(check)."));
  const totals = checkTotals(pulls);
  if (totals.length) {
    root.append(el("h2", {}, "Checks with findings"), el("ul", { class: "check-totals" }, totals.map((total) => el("li", {},
      checkName(total.check),
      el("span", { class: "count" }, ` ${plural(total.findings, "finding")} in ${plural(total.pulls, "pull request")}`)))));
  }
  root.append(el("h2", {}, "Pull requests"));
  for (const pull of pulls) {
    const id = `clang-tidy/${pull.number}`;
    root.append(pull.findings?.length
      ? el("details", { class: "pull", id, open: state.pull === String(pull.number) }, el("summary", {}, pullLine(pull)), findingList(pull))
      : el("div", { class: "pull", id }, pullLine(pull)));
  }
  if (state.pull) document.getElementById(`clang-tidy/${state.pull}`)?.scrollIntoView();
}

// drawn at the width of the page, so that its labels keep their size
function coverageChart(reports, width) {
  const model = chartModel(reports, { width: Math.max(560, width) });
  const point = ({ x, y, report }) => {
    const dot = svg("circle", { class: "point", cx: x, cy: y, r: 4 },
      svg("title", {}, `${shortSha(report.sha)} ${report.title}: ${report.coverage}%`));
    return isWebLink(report.url) ? svg("a", { href: report.url }, dot) : dot;
  };
  return el("div", { class: "scroll" }, svg("svg", {
    class: "chart", viewBox: `0 0 ${model.width} ${model.height}`, role: "img",
    "aria-label": "Line coverage of develop over time",
  },
  model.yTicks.map((tick) => [
    svg("line", { class: "rule", x1: model.left, x2: model.width - model.right, y1: tick.y, y2: tick.y }),
    svg("text", { class: "tick", x: model.left - 6, y: tick.y, "text-anchor": "end", "dominant-baseline": "middle" }, tick.label),
  ]),
  model.xTicks.map((tick) => svg("text", { class: "tick", x: tick.x, y: model.height - 8, "text-anchor": "middle" }, tick.label)),
  svg("path", { class: "trend", d: model.path }),
  model.points.map(point)));
}

function reportTable(reports) {
  const head = ["Commit", "Date", "Title", "Coverage", "Covered lines", "Change, % points"];
  return el("div", { class: "scroll" }, el("table", { class: "reports" },
    el("thead", {}, el("tr", {}, head.map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, reports.map((report) => el("tr", {},
      el("th", { scope: "row" }, isWebLink(report.url) ? el("a", { href: report.url }, shortSha(report.sha)) : shortSha(report.sha)),
      el("td", {}, new Date(report.date).toLocaleDateString()),
      el("td", {}, report.title),
      el("td", { class: "number" }, `${report.coverage.toFixed(2)}%`),
      el("td", { class: "number" }, `${formatCount(report.hits)} of ${formatCount(report.lines)}`),
      el("td", { class: "number" }, formatChange(report.change)))))));
}

function coverageDetail(pull) {
  if (pull.codecov) return changedLinesText(pull.codecov.changed);
  if (pull.status === "running" || pull.status === "pending") return "the coverage job is running";
  if (pull.status === "failed") return "the coverage job failed";
  if (pull.status === "canceled") return "the coverage job was canceled";
  if (pull.status === "success") return "Codecov has no report for it yet";
  return "no coverage run";
}

function coverageLine(pull) {
  const numbers = pull.codecov;
  return [
    el("span", { class: `badge s-${pull.status}` }, pull.status), " ",
    el("a", { href: pull.url }, `#${pull.number}`), ` ${pull.title}`,
    pull.draft ? el("span", { class: "count" }, " (draft)") : null,
    el("span", { class: "pull-detail" }, coverageDetail(pull)),
    numbers ? el("span", { class: "pull-detail" }, `all lines ${numbers.coverage.toFixed(2)}%`
      + (numbers.base_coverage === null || numbers.base_coverage === undefined ? "" : `, develop ${numbers.base_coverage.toFixed(2)}%`)) : null,
    numbers && !numbers.base_has_report
      ? el("span", { class: "pull-warning", title: "Its base commit has no report, so Codecov compared it with an older develop commit; the changed lines include what develop changed since." }, "compared with an older develop commit")
      : null,
    pull.result && isWebLink(pull.result.url) ? el("a", { class: "pull-link", href: pull.result.url }, "log") : null,
    numbers && isWebLink(numbers.url) ? el("a", { class: "pull-link", href: numbers.url, title: "The covered and missed lines on Codecov" }, "Codecov") : null,
  ];
}

function renderCodeCoverage(root) {
  const coverage = state.status?.code_coverage;
  if (!coverage) {
    root.append(el("p", { class: "none" }, "No coverage results available."));
    return;
  }
  const history = coverageHistory(state.status);
  const newest = history.at(-1);
  root.append(el("p", { class: "summary" }, newest
    ? `develop: ${newest.coverage.toFixed(2)}% of ${formatCount(newest.lines)} lines covered at ${shortSha(newest.sha)}, ${new Date(newest.date).toLocaleDateString()}`
    : `No coverage reports for develop in the last ${coverage.history_days} days.`));
  root.append(el("p", { class: "legend" },
    `Line coverage of the reference, OpenMP and MPI code, without the tests and the GPU backends. The job ${coverage.check} uploads it to Codecov on every push to develop, and on pull requests with the 1:ST:ready-to-merge or 1:ST:run-full-test label. `
    + "Until October 2026 the reports came from a GitLab job, which also counted the code of the tests."));
  if (history.length) {
    root.append(el("h2", {}, `develop over the last ${coverage.history_days} days`), coverageChart(history, root.clientWidth),
      el("h2", {}, "Newest reports"), reportTable(history.slice(-20).reverse()));
  }
  const pulls = coveragePulls(state.status);
  const shown = pulls.filter((pull) => pull.codecov || pull.status !== "notrun");
  const others = pulls.filter((pull) => !shown.includes(pull));
  root.append(el("h2", {}, "Pull requests"), el("p", { class: "legend" },
    `The open pull requests updated in the last ${coverage.max_age_days} days, with their coverage job on their newest commit and Codecov's numbers. `
    + "The changed lines are the lines with code that a pull request adds or changes, compared with the develop commit it is based on."));
  if (!shown.length) root.append(el("p", { class: "none" }, "No pull request has a coverage run."));
  for (const pull of shown) root.append(el("div", { class: "pull" }, coverageLine(pull)));
  if (others.length) {
    root.append(el("details", { class: "pull" },
      el("summary", {}, `${others.length} pull requests without a coverage run`),
      el("ul", { class: "others" }, others.map((pull) => el("li", {},
        el("a", { href: pull.url }, `#${pull.number}`), ` ${pull.title}`)))));
  }
}

function render() {
  const filters = document.getElementById("filters");
  filters.hidden = WITHOUT_FILTERS.includes(state.view);
  if (!filters.hidden) renderFilters();
  for (const link of document.querySelectorAll("#tabs a")) {
    if (link.getAttribute("href") === `#${state.view}`) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  const root = document.getElementById("view");
  root.replaceChildren();
  VIEWS[state.view](root);
}

async function main() {
  try {
    state.coverage = await loadJson("coverage.json");
  } catch (error) {
    showBanner("error", `The coverage data could not be loaded (${error.message}).`);
    return;
  }
  try {
    state.status = await loadJson("status.json");
  } catch (error) {
    showBanner("warning", `No job results (${error.message}); showing the coverage only.`);
  }
  // #view, or #clang-tidy/NUMBER for the findings of one pull request
  const fromHash = () => {
    const [view, pull] = location.hash.slice(1).split("/");
    state.pull = pull ?? null;
    return VIEWS[view] ? view : "status";
  };
  state.view = fromHash();
  window.addEventListener("hashchange", () => { state.view = fromHash(); render(); });
  renderMeta();
  render();
}

main();
