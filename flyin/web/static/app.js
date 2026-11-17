/* flyin web GUI: talks to the JSON API of flyin/web/server.py.
 * The map player (drawing, replay, timeline) is in viewer.js. */
"use strict";

const TOKEN = document.querySelector('meta[name="flyin-token"]').content;
const SVGNS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);
const STATUS_RANK = { FAIL: 0, WARN: 1, PASS: 2 };
const GROUP_TEXT = {
  "subject": "the subject's maps from your project",
  "subject-invalid": "the subject's broken maps (must be rejected)",
  "extra": "hand-made maps: capacity, deadlocks, mazes",
  "extra-invalid": "more broken maps (must be rejected)",
  "edge-valid": "tricky but valid input: comments, CRLF, 10 000 drones",
  "edge-invalid": "every parser rule broken once (must be rejected)",
  "challenge": "hard maps, target = exact optimum (optional)",
  "fuzz": "300 random maps with their exact optimum (optional)",
};

const S = {
  state: null,      // /api/state
  maps: [],         // /api/maps
  test: null,       // /api/test
  current: null,    // name of the map in the viewer
  map: null,        // /api/map of it
  replay: null,     // prepared replay (viewer.js)
  polling: null,
  problemFilter: "all",
};

/* ------------------------------------------------------------------ api */

async function api(path, body) {
  const options = { headers: { "X-Flyin-Token": TOKEN } };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    throw new Error("The flyin server does not answer. Is `flyin web` still running?");
  }
  const type = response.headers.get("Content-Type") || "";
  const data = type.startsWith("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error((data && data.error) || `HTTP ${response.status}`);
  return data;
}

let toastTimer = null;
function toast(text, bad = false) {
  const box = $("toast");
  box.textContent = text;
  box.className = "toast" + (bad ? " bad" : "");
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, bad ? 7000 : 3500);
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVGNS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  return node;
}

function icon(name) {
  const node = svg("svg", { class: "ic", "aria-hidden": "true" });
  node.append(svg("use", { href: "#i-" + name }));
  return node;
}

function statusTag(status) {
  return el("span", { class: "status " + (status || "none"), text: status || "—" });
}

const shortName = (name) => name.replace(/\.txt$/, "");
const inGroup = (name) => shortName(name.split("/").slice(1).join("/") || name);

function stackBar(counts, total) {
  const bar = el("span", { class: "stack", title: `${counts.PASS || 0} pass · ${counts.WARN || 0} warn · ${counts.FAIL || 0} fail` });
  if (!total) return bar;
  for (const [key, cls] of [["PASS", "p"], ["WARN", "w"], ["FAIL", "f"]]) {
    if (counts[key]) bar.append(el("i", { class: cls, style: `width:${100 * counts[key] / total}%` }));
  }
  return bar;
}

/* ----------------------------------------------------------------- tabs */

function showTab(name) {
  for (const button of document.querySelectorAll("#tabs button")) {
    button.classList.toggle("active", button.dataset.tab === name);
    if (button.dataset.tab === name) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  for (const section of document.querySelectorAll("main > .view")) {
    section.hidden = section.id !== "tab-" + name;
  }
  if (name === "overview" && S.overviewStale) renderTest();
  if (name === "history") loadHistory();
  if (name === "rules") loadRules();
  if (name === "maps" && S.map) requestAnimationFrame(() => { fitView(); drawBars(); drawTrack(S.replay ? S.replay.t : 0); });
}

document.querySelectorAll("#tabs button").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab)));
document.querySelectorAll("[data-goto]").forEach((b) =>
  b.addEventListener("click", (event) => { event.preventDefault(); showTab(b.dataset.goto); }));

/* ---------------------------------------------------------------- state */

async function refreshState() {
  S.state = await api("/api/state");
  const cfg = S.state.config;
  $("project-name").textContent = cfg ? cfg.project.split(/[\\/]/).filter(Boolean).pop() : "not set up";
  $("project-cmd").textContent = cfg ? cfg.command + (cfg.output_file ? ` → ${cfg.output_file}` : "") : "";
  $("project").title = cfg ? `${cfg.project}\n${cfg.command}\n(Settings)` : "Set up your project";
  $("setup-banner").hidden = !!cfg;
  $("subject-banner").hidden = !cfg || S.state.subject.imported > 0;
  $("subject-version").textContent = `subject ${S.state.subject.version}`;
  $("about").textContent = `Serving ${S.state.cwd} on 127.0.0.1 only. Settings and results ` +
    "are shared with the flyin menu and command line (the .flyin/ folder there).";
  fillSettings();
}

async function refreshMaps() {
  S.maps = await api("/api/maps");
  renderMapList();
  const group = $("map-group");
  if (group.options.length <= 1) {
    for (const g of S.state.groups) group.append(el("option", { value: g.name, text: `${g.name} (${g.count})` }));
  }
}

/* -------------------------------------------------------------- testing */

async function startTest(only) {
  try {
    S.test = await api("/api/test", { only });
    renderTest();
    pollTest();
  } catch (error) {
    toast(error.message, true);
    if (/not set up/.test(error.message)) showTab("settings");
  }
}

$("test-all").addEventListener("click", () => startTest(null));
$("test-selected").addEventListener("click", () => {
  const groups = [...document.querySelectorAll("#group-chips input:checked")].map((i) => i.value);
  if (!groups.length) { toast("Tick at least one group."); return; }
  startTest(groups);
});
$("test-stop").addEventListener("click", async () => {
  S.test = await api("/api/test/stop", {});
  toast("Stopping after the maps that are running…");
});
$("report-link").addEventListener("click", async () => {
  try {
    const text = await api("/api/report");
    const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
    const link = el("a", { href: url, download: "flyin-report.md" });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (error) { toast(error.message, true); }
});

function pollTest() {
  clearTimeout(S.polling);
  S.polling = setTimeout(async () => {
    try {
      S.test = await api("/api/test");
    } catch (error) { toast(error.message, true); return; }
    renderTest();
    if (S.test.running) pollTest();
    else {
      await refreshState();
      await refreshMaps();
      if (S.test.error) toast("The test stopped: " + S.test.error, true);
      else toast(`Test done: ${S.test.counts.PASS} passed · ${S.test.counts.WARN} warnings · ${S.test.counts.FAIL} failed`);
    }
  }, 600);
}

function bestStats(results) {
  // like cli.score_line: valid solutions against the best possible
  const scored = results.filter((r) => r.turns && r.best &&
    (r.status !== "FAIL" || (r.message || "").startsWith("valid, but")));
  if (!scored.length) return null;
  const atBest = scored.filter((r) => r.turns === r.best).length;
  const gaps = scored.map((r) => 100 * (r.turns - r.best) / r.best);
  const worst = scored.reduce((a, b) => (b.turns - b.best > a.turns - a.best ? b : a));
  return { atBest, total: scored.length, avg: gaps.reduce((a, b) => a + b, 0) / gaps.length, worst };
}

function renderTest() {
  const t = S.test || { running: false, results: [], total: 0, done: 0, counts: {} };
  const running = t.running;
  const results = t.results || [];
  $("test-all").disabled = running;
  $("test-selected").disabled = running;
  $("test-stop").hidden = !running;
  $("run-progress").hidden = !running;
  $("run-text").textContent = `${t.done} / ${t.total}`;
  $("run-bar").style.width = (t.total ? Math.round(100 * t.done / t.total) : 0) + "%";
  $("report-link").hidden = running || !results.length || t.from_last;

  // the rest only while the overview is visible (it is rebuilt on the way
  // back): polling every 600 ms must not rebuild hidden tables
  if ($("tab-overview").hidden) { S.overviewStale = true; return; }
  S.overviewStale = false;

  // KPIs
  const counts = t.counts || {};
  for (const [id, key] of [["k-pass", "PASS"], ["k-warn", "WARN"], ["k-fail", "FAIL"]]) {
    $(id).textContent = results.length ? counts[key] || 0 : "–";
  }
  const best = bestStats(results);
  $("k-best").textContent = best ? `${best.atBest}/${best.total}` : "–";
  $("k-best-sub").textContent = best ? "solved maps at the optimum or bound" : "";
  $("k-gap").textContent = best ? `+${best.avg.toFixed(1)}%` : "–";
  $("k-gap-sub").textContent = best && best.worst.turns !== best.worst.best
    ? `most to win: ${inGroup(best.worst.map)} (${best.worst.turns} vs ${best.worst.best})` : "";
  $("k-when-label").textContent = running ? "Testing" : t.from_last ? "Last test" : "This test";
  $("k-when").textContent = running ? `${t.done} / ${t.total}`
    : t.from_last ? (t.time || "–") : results.length ? `${results.length} maps` : "–";
  $("k-when-sub").textContent = running ? `${t.seconds || 0}s` : t.from_last ? `${results.length} maps`
    : results.length ? `${t.seconds || 0}s${t.stopped ? " · stopped" : ""}` : "no test yet";

  // checklist
  const list = $("checklist");
  list.replaceChildren();
  if (!t.checklist || !t.checklist.length) list.append(el("li", { class: "empty", text: "Run a test to fill this." }));
  for (const row of t.checklist || []) {
    list.append(el("li", {},
      el("span", { class: "mark " + (row.ok ? "ok" : "no"), "aria-label": row.ok ? "met" : "not met" }, icon(row.ok ? "check" : "x")),
      el("div", {}, el("div", { class: "label", text: row.label }), el("div", { class: "detail", text: row.detail }))));
  }
  renderSubjectTable(results);
  renderProblems(results);
  renderGroups(results);
}

function renderSubjectTable(results) {
  const body = $("subject-table").tBodies[0];
  body.replaceChildren();
  const byName = Object.fromEntries(results.map((r) => [r.map, r]));
  const level = (name) => {
    const i = ["easy", "medium", "hard", "challenger"].findIndex((l) => name.includes("/" + l + "/"));
    return i < 0 ? 9 : i;
  };
  const subject = S.maps.filter((m) => m.group === "subject")
    .sort((a, b) => level(a.name) - level(b.name) || a.name.localeCompare(b.name));
  if (!subject.length) {
    body.append(el("tr", {}, el("td", { colspan: 5, class: "empty",
      text: "Not imported yet: Settings → Subject maps." })));
    return;
  }
  for (const m of subject) {
    const r = byName[m.name] || m;
    const turns = r.turns;
    let verdict;
    if (!r.status) verdict = el("span", { class: "empty", text: "not tested" });
    else if (r.status === "FAIL" && !(r.message || "").startsWith("valid, but")) verdict = [statusTag("FAIL"), r.message];
    else if (m.optimum && turns && turns <= m.optimum) verdict = [statusTag("PASS"), el("span", { class: "badge star", text: "optimum" })];
    else if (m.optional) verdict = [statusTag(r.status), turns && m.target ? `${turns} / ${m.target}, optional` : "optional"];
    else if (turns && m.target && turns <= m.target) verdict = [statusTag("PASS"), m.optimum ? `+${turns - m.optimum} over the optimum` : "within the target"];
    else if (turns && m.target) verdict = [statusTag(r.status), `${turns - m.target} too many`];
    else verdict = [statusTag(r.status), r.message || ""];
    body.append(el("tr", { class: "click", onclick: () => openMap(m.name), title: m.note || m.name },
      el("td", { class: "name" }, shortName(m.name.replace(/^subject\//, "")),
        m.target && !m.optimum ? el("span", { class: "badge old", text: "older subject" }) : null),
      el("td", { class: "num", text: turns ?? "—" }),
      el("td", { class: "num", text: m.optimum ?? "—" }),
      el("td", { class: "num", text: m.optional ? "opt." : (m.target ?? "—") }),
      el("td", {}, el("span", { class: "verdict-cell" }, ...[].concat(verdict)))));
  }
}

$("problem-filter").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  S.problemFilter = button.dataset.f;
  for (const b of $("problem-filter").children) b.classList.toggle("on", b === button);
  renderProblems((S.test && S.test.results) || []);
});

function renderProblems(results) {
  const body = $("problems-table").tBodies[0];
  body.replaceChildren();
  const all = results.filter((r) => r.status !== "PASS");
  $("problems-count").textContent = all.length;
  const shown = all.filter((r) => S.problemFilter === "all" || r.status === S.problemFilter)
    .sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || a.map.localeCompare(b.map));
  const empty = (text) => body.append(el("tr", {}, el("td", { colspan: 5, class: "empty", text })));
  if (!results.length) return empty("No results yet: run a test.");
  if (!shown.length) return empty(all.length ? "Nothing of this kind." : "No problems: every map passed.");
  for (const r of shown.slice(0, 400)) {
    body.append(el("tr", { class: "click", onclick: () => openMap(r.map) },
      el("td", {}, statusTag(r.status)),
      el("td", { class: "name", text: shortName(r.map) }),
      el("td", { class: "msg", text: r.message }),
      el("td", { class: "num", text: r.turns ?? "—" }),
      el("td", { class: "num", text: r.best ?? "—" })));
  }
}

function renderGroups(results) {
  const box = $("group-chips");
  const ticked = new Set([...box.querySelectorAll("input:checked")].map((i) => i.value));
  const first = !box.childElementCount;
  box.replaceChildren();
  const per = {};
  for (const r of results) {
    per[r.group] = per[r.group] || { PASS: 0, WARN: 0, FAIL: 0, n: 0 };
    per[r.group][r.status]++;
    per[r.group].n++;
  }
  for (const g of S.state.groups) {
    const c = per[g.name];
    box.append(el("li", {}, el("label", {},
      el("input", { type: "checkbox", value: g.name, checked: first ? g.default : ticked.has(g.name) }),
      el("span", { class: "g-name", text: g.name }),
      el("span", { class: "g-count", text: c ? `${c.PASS}/${g.count}` : `${g.count}` }),
      el("span", { class: "g-text", text: GROUP_TEXT[g.name] || "" }),
      stackBar(c || {}, g.count))));
  }
}

/* ------------------------------------------------------------- map list */

["map-search", "map-group", "map-status"].forEach((id) =>
  $(id).addEventListener("input", renderMapList));
$("map-search").addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  const first = $("map-items").querySelector("li.item");
  if (first) first.click();
});

function renderMapList() {
  const query = $("map-search").value.trim().toLowerCase();
  const group = $("map-group").value;
  const status = $("map-status").value;
  const list = $("map-items");
  list.replaceChildren();
  let lastGroup = null, shown = 0;
  for (const m of S.maps) {
    if (group && m.group !== group) continue;
    if (!group && m.group === "fuzz" && !query.includes("fuzz") && status === "") continue;
    if (query && !m.name.toLowerCase().includes(query)) continue;
    if (status === "none" ? m.status : status && m.status !== status) continue;
    if (m.group !== lastGroup) {
      list.append(el("li", { class: "head", text: m.group }));
      lastGroup = m.group;
    }
    const info = m.expect === "error" ? "reject"
      : m.turns ? `${m.turns}${m.target ? "/" + m.target : ""}` : (m.target ? `≤${m.target}` : "");
    list.append(el("li", { class: "item" + (m.name === S.current ? " active" : ""), role: "option",
      "aria-selected": m.name === S.current ? "true" : "false", title: m.message || m.note || m.name,
      onclick: () => openMap(m.name) },
      el("span", { class: "dot " + (m.status || "") }),
      el("span", { class: "name", text: inGroup(m.name) }),
      el("span", { class: "t", text: info })));
    if (++shown >= 600) {
      list.append(el("li", { class: "more", text: "… type to filter for more" }));
      break;
    }
  }
  if (!shown) list.append(el("li", { class: "more", text: "No map matches." }));
  if (!group && !query && !status) {
    const fuzz = S.maps.filter((m) => m.group === "fuzz").length;
    if (fuzz) list.append(el("li", { class: "more", text: `+ ${fuzz} fuzz maps: choose the group` }));
  }
}

/* --------------------------------------------------------------- viewer */

function showPane(name) {
  for (const b of $("itabs").children) {
    b.classList.toggle("on", b.dataset.pane === name);
    b.setAttribute("aria-selected", b.dataset.pane === name ? "true" : "false");
  }
  for (const pane of document.querySelectorAll(".ipane")) pane.hidden = pane.dataset.pane !== name;
  if (name === "live") requestAnimationFrame(drawBars);
}
$("itabs").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) showPane(button.dataset.pane);
});

async function openMap(name, autoload = true) {
  showTab("maps");
  stopPlaying();
  S.current = name;
  S.replay = null;
  history.replaceState(null, "", "#map=" + encodeURIComponent(name));
  renderMapList();
  const active = $("map-items").querySelector("li.active");
  if (active) active.scrollIntoView({ block: "nearest" });
  try {
    S.map = await api("/api/map?name=" + encodeURIComponent(name));
  } catch (error) { toast(error.message, true); return; }
  if (S.current !== name) return;
  $("viewer-empty").hidden = true;
  const c = S.map.case;
  $("map-title").textContent = shortName(c.name);
  const parts = [];
  if (c.expect === "error") parts.push("must be rejected with an error message");
  if (S.map.nb_drones) parts.push(`${S.map.nb_drones} drones`, `${S.map.zones.length} zones`, `${S.map.links.length} links`);
  if (c.optimum) parts.push(`optimum ${c.optimum}`);
  if (c.required) parts.push(`allowed ≤ ${c.target}`);
  else if (c.target && c.target !== c.optimum) parts.push(`target ≤ ${c.target}`);
  if (!c.optimum && S.map.bound) parts.push(`lower bound ${S.map.bound}`);
  if (c.note && !c.required) parts.push(c.note);
  $("map-meta").textContent = parts.join(" · ");
  $("map-meta").title = parts.join("\n");
  $("map-text").textContent = S.map.text;
  $("output-text").textContent = "No output yet: run your program or load a test.";
  $("verdict").hidden = true;
  $("problems-badge").hidden = true;
  const solve = c.expect === "solve";
  $("run-map").disabled = false;
  $("load-last").disabled = !solve;
  $("load-previous").disabled = !solve;
  $("paste-toggle").disabled = !solve || !!S.map.error;
  $("paste").hidden = true;
  showPane(solve && !S.map.error ? "live" : "file");
  drawMap();
  const row = S.maps.find((m) => m.name === name);
  if (row && row.status) showVerdict(row.status, row.message, "last test");
  if (autoload && solve && row && row.status) loadSolution("last", true);
}

function showVerdict(status, message, source) {
  const box = $("verdict");
  box.className = "verdict " + status;
  box.title = message || "";
  box.replaceChildren(statusTag(status), el("span", { class: "msg", text: message || "" }),
    source ? el("span", { class: "src", text: source }) : null);
  box.hidden = false;
}

function showReplay(data) {
  startReplay(data);
  const n = data.errors.length;
  $("problems-badge").hidden = !n;
  $("problems-badge").textContent = n;
}

$("run-map").addEventListener("click", async () => {
  if (!S.current) return;
  const button = $("run-map");
  button.disabled = true;
  button.lastChild.textContent = "Running…";
  const name = S.current;
  try {
    const data = await api("/api/run", { name });
    if (S.current !== name) return;
    const o = data.outcome;
    showVerdict(o.status, o.message, `just now · ${o.seconds}s`);
    showOutput(data.output);
    if (data.replay) showReplay(data.replay);
    else {
      clearReplay();
      showPane("output");
    }
  } catch (error) {
    toast(error.message, true);
    if (/not set up/.test(error.message)) showTab("settings");
  } finally {
    button.disabled = false;
    button.lastChild.textContent = "Run my program";
  }
});

async function loadSolution(which, quiet = false) {
  const name = S.current;
  try {
    const data = await api(`/api/solution?name=${encodeURIComponent(name)}&which=${which}`);
    if (S.current !== name) return;
    showOutput(data.output);
    showReplay(data.replay);
  } catch (error) {
    if (!quiet) toast(error.message, true);
  }
}
$("load-last").addEventListener("click", () => loadSolution("last"));
$("load-previous").addEventListener("click", () => loadSolution("previous"));
$("paste-toggle").addEventListener("click", () => {
  $("paste").hidden = !$("paste").hidden;
  if (!$("paste").hidden) $("paste-text").focus();
});
$("paste-close").addEventListener("click", () => { $("paste").hidden = true; });
$("paste-check").addEventListener("click", async () => {
  try {
    const data = await api("/api/check", { name: S.current, output: $("paste-text").value });
    showOutput(data.output);
    showReplay(data.replay);
    const r = data.replay;
    showVerdict(r.valid ? "PASS" : "FAIL", r.valid ? `valid, ${r.turns} turns` : `invalid: ${r.errors[0] || "?"}`, "pasted");
    $("paste").hidden = true;
  } catch (error) { toast(error.message, true); }
});

function showOutput(text) {
  $("output-text").textContent = text && text.length > 200000 ? text.slice(0, 200000) + "\n…" : (text || "(the program printed nothing)");
}

document.addEventListener("keydown", (event) => {
  if (event.key !== "/" || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
  event.preventDefault();
  showTab("maps");
  $("map-search").focus();
  $("map-search").select();
});

/* ------------------------------------------------------------ settings */

function fillSettings() {
  const cfg = S.state.config;
  if (!cfg || (document.activeElement && $("settings-form").contains(document.activeElement))) return;
  $("f-project").value = cfg.project;
  $("f-command").value = cfg.command;
  $("f-output").value = cfg.output_file;
  $("f-timeout").value = cfg.timeout;
  $("f-jobs").value = cfg.jobs;
  const mode = cfg.output_file ? "file" : cfg.command.includes("{out}") ? "out" : "terminal";
  document.querySelector(`input[name=mode][value=${mode}]`).checked = true;
}

$("f-detect").addEventListener("click", async () => {
  const project = $("f-project").value.trim();
  if (!project) { toast("Enter the project folder first."); return; }
  try {
    const found = await api("/api/detect?project=" + encodeURIComponent(project));
    if (found.command) {
      $("f-command").value = found.command;
      $("settings-note").textContent = "Guessed from the files of the project: check it, then save.";
    } else {
      $("settings-note").textContent = "No main.py, fly_in program or package found: type the command.";
    }
    if (found.maps_folder && !$("f-import").value) {
      $("f-import").value = found.maps_folder;
      $("import-note").textContent = `${found.maps} maps found in the project.`;
    }
  } catch (error) { toast(error.message, true); }
});

$("settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const mode = document.querySelector("input[name=mode]:checked").value;
  const command = $("f-command").value.trim();
  const outputFile = $("f-output").value.trim();
  if (mode === "file" && !outputFile) { toast("Which file does your program write?", true); $("f-output").focus(); return; }
  if (mode === "out" && !command.includes("{out}")) { toast("Put {out} in the command where the output file goes.", true); $("f-command").focus(); return; }
  try {
    await api("/api/config", {
      project: $("f-project").value.trim(), command,
      output_file: mode === "file" ? outputFile : "",
      timeout: $("f-timeout").value || 30, jobs: $("f-jobs").value || 4,
    });
    $("settings-note").textContent = "Saved.";
    await refreshState();
    toast("Settings saved. Try a map: Maps → Run my program.");
  } catch (error) { toast(error.message, true); }
});

$("f-import-go").addEventListener("click", async () => {
  try {
    const r = await api("/api/import", { folder: $("f-import").value.trim() });
    $("import-note").textContent = `Imported ${r.imported} maps, ${r.with_target} with a subject target.`;
    await refreshState();
    await refreshMaps();
    await loadTestStatus();
  } catch (error) { toast(error.message, true); }
});

/* ------------------------------------------------------ history, rules */

async function loadHistory() {
  const body = $("history-table").tBodies[0];
  let runs;
  try { runs = await api("/api/history"); } catch (error) { toast(error.message, true); return; }
  body.replaceChildren();
  if (!runs.length) body.append(el("tr", {}, el("td", { colspan: 7, class: "empty", text: "No test run yet." })));
  runs.forEach((run, i) => {
    const before = runs[i + 1];
    let change = el("span", { class: "empty", text: before ? "no change" : "first run" });
    if (before) {
      let better = 0, worse = 0;
      for (const [name, [status, turns]] of Object.entries(run.results)) {
        const old = before.results[name];
        if (!old) continue;
        const [ostatus, oturns] = old;
        const d = STATUS_RANK[status] - STATUS_RANK[ostatus];
        if (d > 0 || (d === 0 && turns && oturns && turns < oturns)) better++;
        else if (d < 0 || (d === 0 && turns && oturns && turns > oturns)) worse++;
      }
      if (better || worse) {
        change = el("span", {}, el("span", { class: "delta-up", text: `${better} better` }), " · ",
          el("span", { class: "delta-down", text: `${worse} worse` }));
      }
    }
    body.append(el("tr", {},
      el("td", { class: "when", text: run.time }), el("td", { class: "num", text: run.maps }),
      el("td", { class: "bar-col" }, stackBar(run.counts, run.maps)),
      el("td", { class: "num", text: run.counts.PASS }), el("td", { class: "num", text: run.counts.WARN }),
      el("td", { class: "num", text: run.counts.FAIL }), el("td", {}, change)));
  });
}

let rulesLoaded = false;
async function loadRules() {
  if (rulesLoaded) return;
  try {
    const text = await api("/api/rules");
    $("rules").replaceChildren(...markdown(text));
    rulesLoaded = true;
  } catch (error) { toast(error.message, true); }
}

function inline(text) {
  // `code`, **bold**, *em*, [link](url): built as nodes, never as HTML.
  const out = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("`")) out.push(el("code", { text: t.slice(1, -1) }));
    else if (t.startsWith("**")) out.push(el("b", { text: t.slice(2, -2) }));
    else if (t.startsWith("*")) out.push(el("em", { text: t.slice(1, -1) }));
    else {
      const [, label, url] = t.match(/\[([^\]]+)\]\(([^)]+)\)/);
      out.push(/^https?:/.test(url) ? el("a", { href: url, target: "_blank", rel: "noopener", text: label }) : label);
    }
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function markdown(text) {
  const nodes = [];
  let list = null, sub = null, para = [];
  const flush = () => {
    if (para.length) nodes.push(el("p", {}, ...inline(para.join(" "))));
    para = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const head = line.match(/^(#{1,3}) (.*)/);
    const item = line.match(/^(\d+\.|-) (.*)/);
    const nested = line.match(/^\s{2,}- (.*)/);
    if (head) { flush(); list = sub = null; nodes.push(el("h" + head[1].length, {}, ...inline(head[2]))); }
    else if (nested && list && list.lastChild) {
      if (!sub) { sub = el("ul"); list.lastChild.append(sub); }
      sub.append(el("li", {}, ...inline(nested[1])));
    } else if (item) {
      flush();
      sub = null;
      if (!list) { list = el(item[1] === "-" ? "ul" : "ol"); nodes.push(list); }
      const li = el("li", {}, ...inline(item[2]));
      if (item[1] !== "-") li.value = parseInt(item[1], 10);
      list.append(li);
    } else if (/^\s+\S/.test(line) && list && list.lastChild) {
      (sub && sub.lastChild ? sub.lastChild : list.lastChild).append(" ", ...inline(line.trim()));
    } else if (!line.trim()) { flush(); list = sub = null; }
    else { list = sub = null; para.push(line); }
  }
  flush();
  return nodes;
}

/* --------------------------------------------------------------- start */

async function loadTestStatus() {
  S.test = await api("/api/test");
  renderTest();
  if (S.test.running) pollTest();
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await refreshState();
    await refreshMaps();
    await loadTestStatus();
  } catch (error) {
    toast(error.message, true);
    return;
  }
  const hash = decodeURIComponent(location.hash.replace(/^#map=/, ""));
  if (hash && S.maps.some((m) => m.name === hash)) openMap(hash);
  else if (!S.state.config) showTab("settings");
});
