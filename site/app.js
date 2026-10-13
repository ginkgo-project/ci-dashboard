// Renders the dashboard from coverage.json and status.json. All text goes
// through textContent (the el helper), so job names cannot inject markup.
import {
  STATUS_ORDER, effectiveStatus, countSettings, statusRows, summary,
  gridModel, chipLabel, supportedLines, ageLevel, shortSha, formatDuration, machineLabel, toolchainName,
} from "./logic.js";

const state = { coverage: null, status: null, filters: {}, view: "status" };
const VIEWS = { status: renderStatus, coverage: renderCoverage, supported: renderSupported };

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
    "Filled: tests run on hardware. Hollow: compiled only. Red: the latest result failed. Versions outside the supported range sit outside the line."));
  for (const line of supportedLines(state.coverage, state.status, state.filters)) {
    const mark = (t) => el("span", {
      class: ["mark", t.hardware ? "hw" : "compile", t.failed && "failed"].filter(Boolean).join(" "),
      title: `${line.name} ${t.version}: ${t.hardware ? "tested on hardware" : "compiled only"}${t.failed ? ", failing" : ""}`,
    }, el("span", { class: "label" }, t.version));
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

function render() {
  renderFilters();
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
  const fromHash = () => (VIEWS[location.hash.slice(1)] ? location.hash.slice(1) : "status");
  state.view = fromHash();
  window.addEventListener("hashchange", () => { state.view = fromHash(); render(); });
  renderMeta();
  render();
}

main();
