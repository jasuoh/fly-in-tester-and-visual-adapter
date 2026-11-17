/* flyin web GUI: the map player.
 *
 * Drawn like the pygame visualizer in its "Mission Control" theme
 * (flyin/visual/gui: scene.py, map_layer.py, colors.py, metrics.py):
 * glowing zones ringed in their map colour, capacity segments, star and
 * clock badges, START / GOAL tags, active connections in cyan, numbered
 * drones, and the side panel with turn, delivered, metrics and the moves
 * per turn. Uses S, $, el, svg, api and toast of app.js.
 */
"use strict";

/* --------------------------------------------------------------- colours */

const MC = {
  bg: [9, 15, 27], panel: [12, 21, 37], rule: [28, 46, 72],
  text: [226, 238, 250], muted: [120, 146, 176], accent: [56, 220, 230],
  success: [80, 230, 160], warning: [255, 184, 64], edge: [54, 84, 122],
  danger: [255, 84, 96], star: [250, 204, 21], droneText: [8, 16, 28],
  fillMix: 0.22, ring: 0.16, saturation: 0.9,
};
const RAINBOW = [[239, 68, 68], [249, 146, 40], [250, 204, 21], [52, 199, 89], [56, 140, 248], [168, 85, 247]];
const MANY_DRONES = 400;            // above this, places show counts
const TURNS_PER_SECOND = 1.6;       // playback at 1x
const SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16];

const rgb = (c, a = 1) => (a >= 1 ? `rgb(${c[0]},${c[1]},${c[2]})` : `rgba(${c[0]},${c[1]},${c[2]},${a})`);
const mix = (a, b, t) => {
  const k = Math.max(0, Math.min(1, t));
  return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * k));
};
const luminance = (c) => (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255;

function rgbToHsv([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), d = max - Math.min(r, g, b);
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
    if (h < 0) h += 1;
  }
  return [h, max ? d / max : 0, max];
}

function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6), f = h * 6 - i;
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  const table = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]];
  return table[((i % 6) + 6) % 6].map((x) => Math.round(x * 255));
}

const colorProbe = document.createElement("canvas").getContext("2d");
function parseColor(name) {
  // Any CSS colour word (crimson, darkred ...), like pygame's X11 names.
  if (!name) return null;
  colorProbe.fillStyle = "#010203";
  colorProbe.fillStyle = name;
  const first = colorProbe.fillStyle;
  colorProbe.fillStyle = "#040506";
  colorProbe.fillStyle = name;
  if (first !== colorProbe.fillStyle || !/^#[0-9a-f]{6}$/i.test(first)) return null;
  return [1, 3, 5].map((i) => parseInt(first.slice(i, i + 2), 16));
}

function zoneColor(name) {
  // Colors.for_zone: keep the hue, stay readable on the dark background.
  let c = name && name.toLowerCase() === "rainbow" ? RAINBOW[4]
    : parseColor(name) || mix(MC.muted, MC.text, 0.2);
  const [h, s, v] = rgbToHsv(c);
  c = hsvToRgb(h, s * MC.saturation, Math.min(v, 1));
  for (let i = 0; i < 8 && luminance(c) < 0.36; i++) c = mix(c, [255, 255, 255], 0.14);
  return c;
}

const droneColor = (id) => hsvToRgb((0.52 + id * 0.618034) % 1, 0.5, 1);

/* -------------------------------------------------------------- drawing */

const view = {
  box: null, fit: null, zoneR: 20, s: 1, pos: {}, radius: {},
  links: {}, active: {}, usage: {}, segments: {}, fullRing: {}, pills: {},
  layer: null, routeLayer: null, issueLayer: null, droneNodes: [], droneR: 6,
};

/* ------------------------------------------------------------- the view */
// view.box is where the camera looks; view.drawn is the viewBox the SVG
// was last rendered with. While panning or zooming only a CSS transform
// moves the rendered map (one GPU layer, no SVG repaint); the SVG is
// rendered sharp again once the gesture rests.

let commitTimer = 0;

function boxScale(box) {
  // the mapping of preserveAspectRatio "xMidYMid meet": screen = map * k + o
  const [x, y, w, h] = box;
  const k = Math.min(fx.w / w, fx.h / h);
  return { k, ox: (fx.w - w * k) / 2 - x * k, oy: (fx.h - h * k) / 2 - y * k };
}

function setBox(box, live = false) {
  view.box = box;
  if (!live || !view.drawn || !fx.w) commitBox();
  else {
    const from = boxScale(view.drawn), to = boxScale(box);
    const a = to.k / from.k;
    $("stage").style.transform =
      `translate(${(to.ox - a * from.ox).toFixed(2)}px, ${(to.oy - a * from.oy).toFixed(2)}px) scale(${a.toFixed(5)})`;
    $("stage-view").classList.add("moving");
    clearTimeout(commitTimer);
    commitTimer = setTimeout(commitBox, 180);
  }
  if (S.replay) paintDrones();
}

function commitBox() {
  clearTimeout(commitTimer);
  if (!view.box) return;
  view.drawn = view.box.slice();
  const stage = $("stage");
  stage.setAttribute("viewBox", view.box.join(" "));
  stage.style.transform = "";
  $("stage-view").classList.remove("moving");
}

const zoom = { target: null, raf: 0 };
function zoomTo(target) {
  // glide the camera to ``target`` instead of jumping
  zoom.target = target;
  if (!zoom.raf) zoom.raf = requestAnimationFrame(zoomStep);
}
function zoomStep() {
  zoom.raf = 0;
  const target = zoom.target;
  if (!target || !view.box) return;
  const next = view.box.map((v, i) => v + (target[i] - v) * 0.3);
  const done = next.every((v, i) => Math.abs(v - target[i]) < target[2] * 0.0015);
  setBox(done ? target.slice() : next, true);
  if (done) zoom.target = null;
  else zoom.raf = requestAnimationFrame(zoomStep);
}
function stopZoom() {
  cancelAnimationFrame(zoom.raf);
  zoom.raf = 0;
  zoom.target = null;
}

/* ------------------------------------------------------ the drone canvas */
// Drones are painted on a canvas laid over the SVG map. Moving SVG
// elements every frame made the browser lay out the whole map 60 times a
// second, which is what made playback lag.

const fx = { canvas: $("stage-fx"), ctx: null, w: 0, h: 0, dpr: 1, hits: [] };
fx.ctx = fx.canvas.getContext("2d");
const sizes = {};   // canvas sizes, measured by ResizeObservers, never per frame

new ResizeObserver(() => {
  const area = $("stage-view");
  fx.w = area.clientWidth;
  fx.h = area.clientHeight;
  fx.dpr = window.devicePixelRatio || 1;
  fx.canvas.width = Math.round(fx.w * fx.dpr);
  fx.canvas.height = Math.round(fx.h * fx.dpr);
  if (S.replay) paintDrones();
}).observe($("stage-view"));
for (const id of ["p-track", "mc-bars"]) {
  new ResizeObserver(() => {
    sizes[id] = { w: $(id).clientWidth, h: $(id).clientHeight };
    if (id === "p-track") drawTrack(S.replay ? S.replay.t : 0);
    else drawBars();
  }).observe($(id));
}

function fxTransform() { return boxScale(view.box); }

/* Motion, as in the pygame visualizer (flyin/visual/gui/animation.py):
   a move glides from the old slot to the new one; a restricted flight is
   one movement over two turns through the middle of the connection;
   drones sharing a zone sit on a ring; leaving the start grows in,
   reaching the goal shrinks out. A drone that keeps moving does not
   brake between turns: it only eases where it starts from or comes to
   rest. */
const easeIO = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const easeIn = (t) => t * t * (2 - t);          // from rest to full speed
const easeOut = (t) => 1 - easeIn(1 - t);       // from full speed to rest
const clamp01 = (t) => Math.max(0, Math.min(1, t));
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const win = (a, b, t) => easeIO(clamp01((t - a) / (b - a)));

function travel(t, fromRest, toRest) {
  t = clamp01(t);
  if (fromRest && toRest) return easeIO(t);
  if (fromRest) return easeIn(t);
  if (toRest) return easeOut(t);
  return t;
}

function moved(a, b, d) { return groupsAt(a).pos[d] !== groupsAt(b).pos[d]; }

function flight(first, d, s) {
  // a restricted flight starting in turn first + 1: s runs 0..1 over both
  // turns and passes the middle of the connection at the turn boundary
  const e = travel(s, !moved(first - 1, first, d), !moved(first + 2, first + 3, d));
  const origin = slot(first, d), middle = slot(first + 1, d), target = slot(first + 2, d);
  if (!origin || !middle || !target) return middle || origin || target;
  return e <= 0.5 ? lerp(origin, middle, e * 2) : lerp(middle, target, (e - 0.5) * 2);
}

function dronePosition(k, d, p) {
  const R = S.replay;
  const old = groupsAt(k).pos[d], now = groupsAt(k + 1).pos[d];
  if (R.transit[now] && !R.transit[old]) return flight(k, d, p / 2);
  if (R.transit[old] && !R.transit[now]) return flight(k - 1, d, (1 + p) / 2);
  const a = slot(k, d), b = slot(k + 1, d);
  if (!a || !b) return a || b;
  if (old === now) return lerp(a, b, easeIO(p));   // gliding to a new slot in its zone
  return lerp(a, b, travel(p, !moved(k - 1, k, d), !moved(k + 1, k + 2, d)));
}

function paintDrones() {
  const ctx = fx.ctx, R = S.replay;
  ctx.setTransform(fx.dpr, 0, 0, fx.dpr, 0, 0);
  ctx.clearRect(0, 0, fx.w, fx.h);
  fx.hits = [];
  if (!R || !view.box || !R.moves.length && R.t > 0) return;
  const { k: zoomK, ox, oy } = boxScale(view.box);
  const k = Math.min(Math.floor(R.t + 1e-9), Math.max(0, R.moves.length - 1));
  const p = clamp01(R.t - k);
  const bg = rgb(MC.bg), ink = rgb(MC.droneText);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  if (R.n > MANY_DRONES) {
    // thousands of drones: one numbered disc per place
    const shown = p > 0.5 ? k + 1 : k;
    const rad = Math.max(9 * view.s, view.zoneR * 0.6) * zoomK;
    ctx.font = `600 ${(rad * 0.75).toFixed(1)}px "Geist Mono", monospace`;
    for (const [place, drones] of groupsAt(shown).groups) {
      const c = R.coords[place];
      if (!c) continue;
      const px = c[0] * zoomK + ox, py = c[1] * zoomK + oy;
      ctx.fillStyle = bg;
      ctx.beginPath(); ctx.arc(px, py, rad + 2 * view.s * zoomK, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = rgb(MC.accent);
      ctx.beginPath(); ctx.arc(px, py, rad, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = ink;
      ctx.fillText(drones.length > 999 ? Math.round(drones.length / 100) / 10 + "k" : String(drones.length), px, py);
    }
    if (R.sel !== null) {
      const at = dronePosition(k, R.sel, p);
      if (at) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 3;
        ctx.setLineDash([5, 4]);
        ctx.beginPath(); ctx.arc(at[0] * zoomK + ox, at[1] * zoomK + oy, view.zoneR * 0.95 * zoomK, 0, 2 * Math.PI); ctx.stroke();
        ctx.setLineDash([]);
      }
    }
    return;
  }
  const before = groupsAt(k).pos, after = groupsAt(k + 1).pos;
  const resting = [], moving = [];
  for (let d = 0; d < R.n; d++) {
    const old = before[d], now = after[d];
    const hidden = old === R.endIndex || (old === 0 && now === 0);
    if (hidden && d !== R.sel) continue;
    (old !== now ? moving : resting).push(d);
  }
  const rad0 = view.droneR * zoomK, halo = 2 * view.s * zoomK;
  const numbers = view.droneR >= 7 * view.s && rad0 >= 6;
  for (const d of resting.concat(moving)) {   // moving drones on top
    const at = dronePosition(k, d, p);
    if (!at) continue;
    const old = before[d], now = after[d];
    let scale = 1, opacity = 1;
    if (old === 0 && now !== 0) { const g = win(0, 0.35, p); scale = 0.5 + 0.5 * g; opacity = g; }
    if (now === R.endIndex && old !== R.endIndex) { const sh = win(0.65, 1, p); scale *= 1 - 0.5 * sh; opacity *= 1 - sh; }
    if ((old === R.endIndex || (old === 0 && now === 0)) && d === R.sel) opacity = 0.9;
    if (R.sel !== null && d !== R.sel) opacity *= 0.28;
    if (opacity <= 0.02) continue;
    const rad = rad0 * scale;
    const px = at[0] * zoomK + ox, py = at[1] * zoomK + oy;
    if (px < -rad || py < -rad || px > fx.w + rad || py > fx.h + rad) continue;
    ctx.globalAlpha = opacity;
    ctx.fillStyle = bg;
    ctx.beginPath(); ctx.arc(px, py, rad + halo * scale, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = R.colors[d];
    ctx.beginPath(); ctx.arc(px, py, rad, 0, 2 * Math.PI); ctx.fill();
    if (d === R.sel) {
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2.5;
      ctx.stroke();
    }
    if (numbers && scale > 0.75) {
      const id = d + R.data.id_base;
      ctx.font = `600 ${(rad * (id < 10 ? 1.05 : 0.9)).toFixed(1)}px "Geist Mono", monospace`;
      ctx.fillStyle = ink;
      ctx.fillText(String(id), px, py + 0.5);
    }
    if (opacity > 0.3) fx.hits.push([px, py, d]);
  }
  ctx.globalAlpha = 1;
}

function droneAt(event) {
  // the drone under the pointer (canvas hit test), or null
  const rect = $("stage-view").getBoundingClientRect();
  const x = event.clientX - rect.left, y = event.clientY - rect.top;
  const reach = view.droneR * (view.box ? boxScale(view.box).k : 1) + 4;
  let best = null, dist = reach;
  for (const [px, py, d] of fx.hits) {
    const dd = Math.hypot(px - x, py - y);
    if (dd <= dist) { best = d; dist = dd; }
  }
  return best;
}

function fitView() { if (view.fit) zoomTo(view.fit.slice()); }

function edgePoints(a, b) {
  // scene.edge_points: a connection ends at the zone rims
  const [ax, ay] = view.pos[a], [bx, by] = view.pos[b];
  const length = Math.hypot(bx - ax, by - ay) || 1;
  const trim = Math.min(view.zoneR + 3 * view.s, length / 3);
  const ux = (bx - ax) / length, uy = (by - ay) / length;
  return [ax + ux * trim, ay + uy * trim, bx - ux * trim, by - uy * trim];
}

function arcBand(cx, cy, inner, outer, a0, a1) {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const p = (r, a) => `${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`;
  return `M${p(outer, a0)} A${outer} ${outer} 0 ${large} 1 ${p(outer, a1)} ` +
    `L${p(inner, a1)} A${inner} ${inner} 0 ${large} 0 ${p(inner, a0)} Z`;
}

function starPath(cx, cy, size) {
  const points = [];
  for (let i = 0; i < 10; i++) {
    const r = i % 2 ? size * 0.45 : size, a = -Math.PI / 2 + i * Math.PI / 5;
    points.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return points.join(" ");
}

function shortLabel(name, room) {
  if (name.length <= room) return name;
  const head = Math.ceil((room - 1) / 2), tail = room - 1 - head;
  return name.slice(0, head) + "…" + name.slice(-tail);
}

function drawMap() {
  const stage = $("stage");
  stage.replaceChildren();
  Object.assign(view, { pos: {}, radius: {}, links: {}, active: {}, usage: {}, segments: {},
    fullRing: {}, pills: {}, droneNodes: [], max: {} });
  const m = S.map;
  if (!m.zones || !m.zones.length) {
    const t = svg("text", { x: 20, y: 50, class: "mc-msg" });
    t.textContent = m.error ? `The tester cannot draw this map: ${m.error}` : "Nothing to draw.";
    stage.append(t);
    stage.setAttribute("viewBox", "0 0 700 100");
    view.layer = null;
    resetPanel();
    return;
  }
  const U = 100;
  const xs = m.zones.map((z) => z.x), ys = m.zones.map((z) => z.y);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  for (const z of m.zones) view.pos[z.name] = [(z.x - minX) * U, (z.y - minY) * U];
  let dmin = Infinity;
  for (const l of m.links) {
    const [ax, ay] = view.pos[l.a], [bx, by] = view.pos[l.b];
    const d = Math.hypot(ax - bx, ay - by);
    if (d > 0) dmin = Math.min(dmin, d);
  }
  if (!isFinite(dmin)) dmin = U;
  // Sizes in screen pixels, like pygame: s = map units per pixel when
  // the map fits the stage, so text, rings and drones keep their size on
  // wide maps too.
  const w = (Math.max(...xs) - minX) * U, h = (Math.max(...ys) - minY) * U;
  const W = stage.clientWidth || 900, H = stage.clientHeight || 600;
  const PAD = 64;
  // ui: the page's scale for large screens (style.css, html font-size)
  const ui = (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16) / 16;
  const s = (Math.max(w / Math.max(200, W - 2 * PAD * ui), h / Math.max(150, H - 2.3 * PAD * ui), 0.05) || 1) * ui;
  const r = Math.max(11 * s, Math.min(28 * s, dmin * 0.27));
  view.zoneR = r; view.s = s;
  view.droneR = Math.max(4.5 * s, Math.min(9.5 * s, r * 0.45));
  const pad = PAD * s;
  view.fit = [-pad, -pad * 1.3, w + 2 * pad, h + 2.3 * pad];
  stopZoom();
  view.drawn = null;
  setBox(view.fit.slice());

  // patterns and glows; the glow is a radial gradient, not a blur filter:
  // a filter is recomputed whenever the map repaints (laggy)
  const defs = svg("defs");
  stage.append(defs);
  const glows = {};
  const glow = (color) => {
    const key = color.join(",");
    if (!glows[key]) {
      const id = "mc-glow-" + Object.keys(glows).length;
      const g = svg("radialGradient", { id });
      for (const [offset, opacity] of [[0.45, 0.42], [0.62, 0.2], [1, 0]]) {
        g.append(svg("stop", { offset, "stop-color": rgb(color), "stop-opacity": opacity }));
      }
      defs.append(g);
      glows[key] = `url(#${id})`;
    }
    return glows[key];
  };
  const hatches = {};
  const hatch = (color) => {
    const key = color.join(",");
    if (!hatches[key]) {
      const id = "mc-hatch-" + Object.keys(hatches).length;
      const step = Math.max(4 * s, r / 3);
      const pattern = svg("pattern", { id, patternUnits: "userSpaceOnUse", width: step, height: step,
        patternTransform: "rotate(45)" });
      pattern.append(svg("line", { x1: 0, y1: 0, x2: 0, y2: step, stroke: rgb(color), "stroke-width": step / 3 }));
      defs.append(pattern);
      hatches[key] = `url(#${id})`;
    }
    return hatches[key];
  };

  const gEdges = svg("g"), gActive = svg("g"), gZones = svg("g"), gRings = svg("g"), gTags = svg("g");
  view.routeLayer = svg("g");
  view.issueLayer = svg("g");
  view.layer = true;   // the map is drawn; drones go on the canvas over it (fx)
  stage.append(gEdges, gActive, view.routeLayer, gZones, gRings, gTags, view.issueLayer);

  const kind = Object.fromEntries(m.zones.map((z) => [z.name, z.kind]));
  for (const l of m.links) {
    const [x1, y1, x2, y2] = edgePoints(l.a, l.b);
    const width = Math.min(7, 1.8 + 1.1 * (l.cap - 1)) * s;
    const faded = kind[l.a] === "blocked" || kind[l.b] === "blocked";
    gEdges.append(svg("line", { x1, y1, x2, y2, stroke: rgb(faded ? mix(MC.edge, MC.bg, 0.55) : MC.edge),
      "stroke-width": width, "stroke-linecap": "round" }));
    const key = [l.a, l.b].sort().join("|");
    view.links[key] = { x1, y1, x2, y2, width, cap: l.cap };
    // the highlight of a used connection, faded in and out
    const g = svg("g", { class: "mc-active" });
    g.append(svg("line", { x1, y1, x2, y2, stroke: rgb(mix(MC.bg, MC.accent, 0.3)),
      "stroke-width": width + 4 * s, "stroke-linecap": "round" }));
    g.append(svg("line", { x1, y1, x2, y2, stroke: rgb(MC.accent), "stroke-width": width + 1.5 * s,
      "stroke-linecap": "round" }));
    const label = svg("text", { x: (x1 + x2) / 2, y: (y1 + y2) / 2 - width - 4 * s, class: "mc-usage" });
    label.style.fontSize = 10 * s + "px";
    g.append(label);
    gActive.append(g);
    view.active[key] = { g, label };
  }

  const fontSize = 12 * s;
  const room = Math.max(4, Math.floor(dmin * 0.95 / (fontSize * 0.58)));
  for (const z of m.zones) {
    const [x, y] = view.pos[z.name];
    const hub = z.name === m.start || z.name === m.end;
    const rad = hub ? r * 1.18 : r;
    view.radius[z.name] = rad;
    const passable = z.kind !== "blocked";
    let color = zoneColor(z.color);
    const g = svg("g", { class: "mc-zone" });
    if (passable) {
      g.append(svg("circle", { cx: x, cy: y, r: rad * 1.75, fill: glow(color) }));
    } else color = mix(color, MC.bg, 0.6);
    const fill = mix(MC.bg, color, MC.fillMix);
    g.append(svg("circle", { cx: x, cy: y, r: rad + 2 * s, fill: rgb(MC.bg) }));
    g.append(svg("circle", { cx: x, cy: y, r: rad, fill: rgb(fill) }));
    if (z.kind === "restricted") g.append(svg("circle", { cx: x, cy: y, r: rad - 0.5, fill: hatch(mix(fill, color, 0.45)) }));
    const rim = Math.max(1.5 * s, rad * MC.ring);
    if (z.color && z.color.toLowerCase() === "rainbow") {
      RAINBOW.forEach((part, i) => {
        const a0 = -Math.PI / 2 + i * 2 * Math.PI / 6;
        g.append(svg("path", { d: arcBand(x, y, rad - Math.max(rim, 3 * s), rad, a0, a0 + 2 * Math.PI / 6 + 0.02),
          fill: rgb(part) }));
      });
    } else {
      g.append(svg("circle", { cx: x, cy: y, r: rad - rim / 2, fill: "none", stroke: rgb(color), "stroke-width": rim }));
    }
    if (!passable) {
      const c = rad * 0.42, stroke = rgb(mix(MC.muted, MC.bg, 0.2));
      g.append(svg("path", { d: `M${x - c} ${y - c} L${x + c} ${y + c} M${x + c} ${y - c} L${x - c} ${y + c}`,
        stroke, "stroke-width": 2 * s, "stroke-linecap": "round" }));
    }
    const label = svg("text", { x, y: y + rad + 8 * s + fontSize * 0.8, class: "mc-label" + (passable ? "" : " off") });
    label.style.fontSize = fontSize + "px";
    label.style.strokeWidth = 3.5 * s + "px";
    label.textContent = shortLabel(z.name, room);
    g.append(label);
    g.addEventListener("mousemove", (event) => showTip(event, z));
    g.addEventListener("mouseleave", () => { $("tooltip").hidden = true; });
    gZones.append(g);

    if (passable && !hub) {
      // capacity: max_drones segments (at most 24) and an outer ring when full
      const inner = r + 3 * s, outer = inner + 3 * s;
      const slots = Math.min(z.max, 24);
      const gap = slots === 1 ? 0 : Math.min(0.18, 1.2 / slots);
      const parts = [];
      for (let i = 0; i < slots; i++) {
        const a0 = -Math.PI / 2 + i * 2 * Math.PI / slots + gap / 2;
        // one slot: the whole ring, as two half bands (one SVG arc
        // cannot draw a full circle)
        const seg = svg("path", { d: slots === 1
          ? arcBand(x, y, inner, outer, -Math.PI / 2, Math.PI / 2) + " " +
            arcBand(x, y, inner, outer, Math.PI / 2, 3 * Math.PI / 2)
          : arcBand(x, y, inner, outer, a0, a0 + 2 * Math.PI / slots - gap),
        class: "mc-seg" });
        gRings.append(seg);
        parts.push(seg);
      }
      view.segments[z.name] = parts;
    view.max[z.name] = z.max;
      const full = svg("circle", { cx: x, cy: y, r: outer + 3 * s, fill: "none", stroke: rgb(MC.warning),
        "stroke-width": 1.2 * s, class: "mc-full" });
      gRings.append(full);
      view.fullRing[z.name] = full;
      // type badge: star (priority) or clock (restricted)
      if (z.kind === "priority" || z.kind === "restricted") {
        const size = Math.max(6.5 * s, r * 0.42), bx = x + r * 0.82, by = y - r * 0.82;
        gRings.append(svg("circle", { cx: bx, cy: by, r: size + 2 * s, fill: rgb(MC.bg) }));
        if (z.kind === "priority") {
          gRings.append(svg("circle", { cx: bx, cy: by, r: size, fill: rgb(mix(MC.bg, MC.star, 0.25)) }));
          gRings.append(svg("polygon", { points: starPath(bx, by, size * 0.85), fill: rgb(MC.star) }));
        } else {
          const c = size * 0.72, stroke = rgb(MC.warning);
          gRings.append(svg("circle", { cx: bx, cy: by, r: size, fill: rgb(mix(MC.bg, MC.warning, 0.18)) }));
          gRings.append(svg("circle", { cx: bx, cy: by, r: c, fill: "none", stroke, "stroke-width": size * 0.2 }));
          gRings.append(svg("path", { d: `M${bx} ${by} L${bx} ${by - c * 0.62} M${bx} ${by} L${bx + c * 0.48} ${by}`,
            fill: "none", stroke, "stroke-width": size * 0.18, "stroke-linecap": "round" }));
        }
      }
    }
  }
  // START / GOAL tags
  for (const [name, title, color] of [[m.start, "START", MC.accent], [m.end, "GOAL", MC.success]]) {
    const [x, y] = view.pos[name];
    const g = svg("g");
    const height = 19 * s;
    const top = y - view.radius[name] - 10 * s - height;
    const rect = svg("rect", { y: top, height, rx: height / 2, fill: rgb(mix(MC.bg, color, 0.14)),
      stroke: rgb(mix(MC.bg, color, 0.6)), "stroke-width": 1.1 * s });
    const label = svg("text", { y: top + height / 2, class: "mc-pill-title", fill: rgb(color) });
    label.style.fontSize = 10.5 * s + "px";
    label.textContent = title;
    const value = svg("text", { y: top + height / 2, class: "mc-pill-value" });
    value.style.fontSize = 12 * s + "px";
    g.append(rect, label, value);
    gTags.append(g);
    view.pills[title] = { x, rect, label, value, s, last: null, titleWidth: title.length * 10.5 * s * 0.8 };
  }
  updatePills(m.nb_drones, 0);
  drawLegend();
  if (S.replay) setGeometry(S.replay);
  else resetPanel();   // a newly opened map: empty panel until a solution
  drawDrones();
}

function updatePills(waiting, delivered) {
  const n = S.map.nb_drones;
  setPill("START", String(waiting));
  setPill("GOAL", `${delivered}/${n}`);
}

function setPill(title, text) {
  const p = view.pills[title];
  if (!p || p.last === text) return;
  p.last = text;
  const valueWidth = text.length * 12 * p.s * 0.62;
  const width = p.titleWidth + valueWidth + 28 * p.s;
  const left = p.x - width / 2;
  p.rect.setAttribute("x", left);
  p.rect.setAttribute("width", width);
  p.label.setAttribute("x", left + 9 * p.s);
  p.value.setAttribute("x", left + width - 9 * p.s);
  p.value.textContent = text;
}

function drawLegend() {
  const icon = (paint) => {
    const box = svg("svg", { viewBox: "-10 -10 20 20", width: 16, height: 16 });
    paint(box);
    return box;
  };
  const ring = (stroke, extra = {}) => (b) => b.append(svg("circle", { r: 6.5, fill: rgb(mix(MC.bg, stroke, 0.22)),
    stroke: rgb(stroke), "stroke-width": 2, ...extra }));
  const items = [
    ["Normal zone", ring(zoneColor(null))],
    ["Restricted · 2 turns", (b) => { ring(MC.warning)(b); b.append(svg("path", { d: "M-4 4 L4 -4 M-6 1 L1 -6 M-1 6 L6 -1",
      stroke: rgb(MC.warning), "stroke-width": 1.2 })); }],
    ["Priority", (b) => b.append(svg("polygon", { points: starPath(0, 0, 7.5), fill: rgb(MC.star) }))],
    ["Blocked", (b) => b.append(svg("path", { d: "M-5 -5 L5 5 M5 -5 L-5 5", stroke: rgb(MC.muted), "stroke-width": 1.8 }))],
    ["Zone at capacity", ring(MC.warning, { "stroke-width": 3 })],
    ["Drone", (b) => b.append(svg("circle", { r: 5.5, fill: rgb(droneColor(3)) }))],
    ["Connection in use", (b) => b.append(svg("line", { x1: -8, y1: 0, x2: 8, y2: 0, stroke: rgb(MC.accent), "stroke-width": 3 }))],
    ["Broken rule", ring(MC.danger)],
  ];
  $("mc-legend").replaceChildren(...items.map(([text, paint]) => el("span", {}, icon(paint), text)));
}

function showTip(event, z) {
  const tip = $("tooltip");
  const here = S.replay ? (S.replay.lastCounts || {})[z.name] || 0 : null;
  const kind = { normal: "normal · 1 turn", priority: "priority · 1 turn, preferred",
    restricted: "restricted · 2 turns", blocked: "blocked · never enter" }[z.kind] || z.kind;
  const hub = z.name === S.map.start ? "start · " : z.name === S.map.end ? "goal · " : "";
  const cap = hub ? "unlimited" : `max_drones ${z.max}`;
  tip.replaceChildren(el("b", { text: z.name }), el("div", { text: hub + kind }),
    el("div", { class: "mc-tip-muted", text: `(${z.x}, ${z.y}) · ${cap}${z.color ? " · " + z.color : ""}` }),
    here !== null ? el("div", { text: `drones here: ${here}${hub ? "" : " / " + z.max}` }) : null);
  const rect = $("mc-stage").getBoundingClientRect();
  tip.style.left = Math.min(rect.width - 240, event.clientX - rect.left + 14) + "px";
  tip.style.top = (event.clientY - rect.top + 14) + "px";
  tip.hidden = false;
}

// zoom (smooth, around the pointer) and pan; a click on a drone follows
// it, a click elsewhere stops following
(() => {
  const area = $("stage-view");
  let drag = null;
  area.addEventListener("wheel", (event) => {
    if (!view.box) return;
    event.preventDefault();
    const rect = area.getBoundingClientRect();
    const base = zoom.target || view.box;
    const { k, ox, oy } = boxScale(base);
    const mx = (event.clientX - rect.left - ox) / k, my = (event.clientY - rect.top - oy) / k;
    const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
    const f = Math.exp(Math.max(-300, Math.min(300, delta)) * 0.0016);
    const [x, y, w, h] = base;
    zoomTo([mx - (mx - x) * f, my - (my - y) * f, w * f, h * f]);
  }, { passive: false });
  area.addEventListener("pointerdown", (event) => {
    if (!view.box || event.button !== 0) return;
    const hit = S.replay ? droneAt(event) : null;
    if (hit !== null) { selectDrone(hit); return; }
    stopZoom();
    drag = { x: event.clientX, y: event.clientY, box: view.box.slice(), moved: false };
    area.setPointerCapture(event.pointerId);
    area.classList.add("drag");
  });
  area.addEventListener("pointermove", (event) => {
    if (!drag) {
      area.classList.toggle("over-drone", !!S.replay && droneAt(event) !== null);
      return;
    }
    const { k } = boxScale(drag.box);
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    const [x, y, w, h] = drag.box;
    setBox([x - dx / k, y - dy / k, w, h], true);
  });
  const end = (event) => {
    if (drag && !drag.moved && event.type === "pointerup" && S.replay && S.replay.sel !== null) selectDrone(null);
    if (drag && drag.moved) commitBox();
    drag = null;
    area.classList.remove("drag");
  };
  area.addEventListener("pointerup", end);
  area.addEventListener("pointercancel", end);
  area.addEventListener("dblclick", fitView);
})();

/* --------------------------------------------------------------- replay */

function placeCoords(places) {
  return places.map((p) => {
    if (p.includes(">")) {
      // in flight towards a restricted zone: on the connection
      const [a, b] = p.split(">");
      const pa = view.pos[a], pb = view.pos[b];
      return pa && pb ? [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2] : null;
    }
    return view.pos[p] || null;
  });
}

function prepareReplay(data) {
  const m = S.map;
  const n = data.drones;
  const places = [m.start];
  const index = { [m.start]: 0 };
  const placeOf = (p) => {
    if (!(p in index)) { index[p] = places.length; places.push(p); }
    return index[p];
  };
  const moves = data.moves.map((turn) => turn.map(([id, p]) => [id - data.id_base, placeOf(p)]));
  const step = n > 1000 ? 100 : 25;
  const checkpoints = [new Int32Array(n)];
  const cur = new Int32Array(n);
  for (let t = 0; t < moves.length; t++) {
    for (const [d, p] of moves[t]) if (d >= 0 && d < n) cur[d] = p;
    if ((t + 1) % step === 0) checkpoints.push(cur.slice());
  }
  // metrics like flyin/visual/metrics.py
  const cost = Object.fromEntries(m.zones.map((z) => [z.name, z.kind === "restricted" ? 2 : 1]));
  const endIndex = index[m.end] ?? -1;
  const arrivals = new Map();
  let pathCost = 0, totalMoves = 0;
  const perTurn = moves.map((turn, t) => {
    for (const [d, p] of turn) {
      totalMoves++;
      if (p === endIndex && !arrivals.has(d)) arrivals.set(d, t + 1);
      if (!places[p].includes(">")) pathCost += cost[places[p]] || 1;
    }
    return turn.length;
  });
  const arrivalSum = [...arrivals.values()].reduce((a, b) => a + b, 0);
  const issueTurns = [...new Set(data.issues.map((i) => i.turn).filter((t) => t > 0))].sort((a, b) => a - b);
  return {
    data, n, places, moves, step, checkpoints, issueTurns, perTurn,
    metrics: { turns: moves.length, mpt: moves.length ? totalMoves / moves.length : 0,
      tpd: arrivals.size ? arrivalSum / arrivals.size : 0, cost: pathCost },
    colors: Array.from({ length: n }, (_, d) => rgb(droneColor(d + data.id_base))),
    layouts: new Map(),
    endIndex, t: 0, playing: false, cache: new Map(), lastCounts: {}, sel: null, shown: -1, activeTurn: -1,
  };
}

function frame(k) {
  const R = S.replay;
  k = Math.max(0, Math.min(R.moves.length, k));
  if (R.cache.has(k)) return R.cache.get(k);
  const c = Math.floor(k / R.step);
  const cur = R.checkpoints[c].slice();
  for (let t = c * R.step; t < k; t++) for (const [d, p] of R.moves[t]) if (d >= 0 && d < R.n) cur[d] = p;
  if (R.cache.size > 8) R.cache.delete(R.cache.keys().next().value);
  R.cache.set(k, cur);
  return cur;
}

function groupsAt(k) {
  // state k: where every drone is, the drones of each place in id order
  // and each drone's index in its place (cached: playback reads the same
  // few states in many frames)
  const R = S.replay;
  k = Math.max(0, Math.min(R.moves.length, k));
  let hit = R.layouts.get(k);
  if (!hit) {
    const pos = frame(k);
    const groups = new Map(), index = new Int32Array(R.n);
    for (let d = 0; d < R.n; d++) {
      let group = groups.get(pos[d]);
      if (!group) { group = []; groups.set(pos[d], group); }
      index[d] = group.length;
      group.push(d);
    }
    hit = { pos, groups, index };
    if (R.layouts.size > 12) R.layouts.delete(R.layouts.keys().next().value);
    R.layouts.set(k, hit);
  }
  return hit;
}

function slot(k, d) {
  // where drone d rests in state k (Choreography.slot of the pygame GUI):
  // several drones in one zone sit on a ring big enough not to overlap,
  // drones in flight side by side across the middle of their connection
  const R = S.replay;
  const state = groupsAt(k), place = state.pos[d], base = R.coords[place];
  if (!base) return null;
  if (place === 0 || place === R.endIndex) return base;
  const count = state.groups.get(place).length, i = state.index[d];
  if (R.transit[place]) {
    const [nx, ny] = R.normals[place];
    const off = (i - (count - 1) / 2) * view.droneR * 2.3;
    return [base[0] + nx * off, base[1] + ny * off];
  }
  if (count === 1) return base;
  const ring = Math.max(view.zoneR * 0.5, view.droneR * 1.15 / Math.sin(Math.PI / count));
  const a = -Math.PI / 2 + i * 2 * Math.PI / count;
  return [base[0] + Math.cos(a) * ring, base[1] + Math.sin(a) * ring];
}

function setGeometry(R) {
  // screen geometry of every place (again after the map is redrawn)
  R.coords = placeCoords(R.places);
  R.transit = R.places.map((p) => p.includes(">"));
  R.normals = R.places.map((p) => {
    if (!p.includes(">")) return null;
    const [a, b] = p.split(">"), pa = view.pos[a], pb = view.pos[b];
    if (!pa || !pb) return [0, 0];
    const len = Math.hypot(pb[0] - pa[0], pb[1] - pa[1]) || 1;
    return [-(pb[1] - pa[1]) / len, (pb[0] - pa[0]) / len];
  });
}

function startReplay(data) {
  stopPlaying();
  S.replay = prepareReplay(data);
  const R = S.replay;
  setGeometry(R);
  const side = $("side-errors");
  side.replaceChildren();
  if (data.valid) side.append(el("p", { class: "empty", text: `Valid: every rule holds over ${data.turns} turns.` }));
  else {
    const list = el("ul", { class: "err-list" });
    for (const issue of data.issues) {
      list.append(el("li", { title: "jump to this turn", onclick: () => seek(Math.max(issue.turn, 0)) },
        el("span", { class: "t", text: issue.turn ? `turn ${issue.turn}` : "end" }), el("span", { text: issue.message })));
    }
    side.append(el("p", { class: "empty", text: `${data.errors.length} problem${data.errors.length === 1 ? "" : "s"}: click one to jump to its turn.` }), list);
  }
  if (data.skipped.length) {
    side.append(el("h3", { text: "Not drawn" }),
      el("ul", { class: "err-list" }, ...data.skipped.map((s) => el("li", { text: s }))));
  }
  if (!R.moves.length) side.append(el("p", { class: "muted small", text: "The output has no turn lines." }));
  view.droneNodes = [];
  if (view.routeLayer) view.routeLayer.replaceChildren();
  $("p-follow").value = "";
  $("p-follow").min = data.id_base;
  $("p-follow").max = R.n - 1 + data.id_base;
  $("p-drone").replaceChildren(el("span", { class: "mc-dim", text: "Click a drone on the map, or type its number." }));
  const m = R.metrics;
  $("mc-m-turns").textContent = m.turns;
  $("mc-m-mpt").textContent = m.mpt.toFixed(2);
  $("mc-m-tpd").textContent = m.tpd.toFixed(2);
  $("mc-m-cost").textContent = m.cost;
  $("mc-turns").textContent = R.moves.length;
  $("p-total").textContent = R.moves.length;
  $("mc-bars-h").textContent = `Moves per turn · peak ${Math.max(0, ...R.perTurn)}`;
  $("mc-title").replaceChildren(document.createTextNode(mapTitle()), data.valid ? "" : el("span", { class: "mc-bad", text: " · INVALID" }));
  seek(R.issueTurns.length ? R.issueTurns[0] : 0);
  if (!R.issueTurns.length && R.moves.length) play();
}

function clearReplay() {
  stopPlaying();
  S.replay = null;
  if (view.routeLayer) view.routeLayer.replaceChildren();
  if (view.issueLayer) view.issueLayer.replaceChildren();
  view.droneNodes = [];
  resetPanel();
  drawDrones();
}

function mapTitle() {
  const c = S.map.case;
  const stem = c.name.split("/").pop().replace(/\.txt$/, "").replace(/^\d+_/, "").replace(/_/g, " ");
  return `${c.group || "map"} · ${stem}`;
}

function resetPanel() {
  if (!S.map) return;
  $("mc-title").textContent = mapTitle();
  $("mc-rule").hidden = true;
  $("mc-turn").textContent = "0";
  $("mc-turns").textContent = "–";
  $("p-total").textContent = "–";
  const n = S.map.nb_drones || 0;
  $("mc-route").textContent = 0;
  $("mc-transit").textContent = 0;
  $("mc-waiting").textContent = n;
  $("mc-deliv").textContent = `0 / ${n}`;
  $("mc-pct").textContent = "0%";
  $("mc-progress").style.width = "0";
  $("mc-moves").replaceChildren(el("span", { class: "mc-dim",
    text: S.map.case.expect === "error" ? "This map must be rejected: ▶ Run my program shows what yours does."
      : "No solution loaded: ▶ Run my program, Last test or Paste output." }));
  for (const id of ["mc-m-turns", "mc-m-mpt", "mc-m-tpd", "mc-m-cost"]) $(id).textContent = "–";
  $("mc-bars-h").textContent = "Moves per turn";
  $("p-drone").replaceChildren(el("span", { class: "mc-dim", text: "Load a solution to follow a drone." }));
  $("side-errors").replaceChildren(el("p", { class: "muted small", text: "No solution loaded." }));
  drawBars();
  drawTrack(0);
}

function drawDrones() {
  const R = S.replay;
  if (!view.layer) return;
  if (!R) {
    fx.ctx.setTransform(1, 0, 0, 1, 0, 0);
    fx.ctx.clearRect(0, 0, fx.canvas.width, fx.canvas.height);
    fx.hits = [];
    for (const g of Object.values(view.active)) g.g.classList.remove("on");
    for (const [name, parts] of Object.entries(view.segments)) paintSegments(name, parts, 0);
    if (S.map) updatePills(S.map.nb_drones, 0);
    return;
  }
  const k = Math.floor(R.t + 1e-9);
  const f = R.t - k;
  const shown = f > 0.5 ? k + 1 : k;
  const activeTurn = f > 0 ? k + 1 : k;   // the turn being flown (or just done)

  if (R.activeTurn !== activeTurn) {
    R.activeTurn = activeTurn;
    paintActiveLinks(activeTurn);
  }
  paintDrones();

  if (R.shown !== shown) {
    R.shown = shown;
    const counts = {};
    for (const [place, drones] of groupsAt(shown).groups) counts[R.places[place]] = drones.length;
    R.lastCounts = counts;
    for (const [name, parts] of Object.entries(view.segments)) paintSegments(name, parts, counts[name] || 0);
    updatePills(counts[S.map.start] || 0, counts[S.map.end] || 0);
    const issues = R.data.issues.filter((i) => i.turn === shown && shown > 0);
    drawIssues(issues);
    renderPanel(shown, counts, issues);
    drawBars();
  }
  drawTrack(R.t);
}

function paintSegments(name, parts, here) {
  const max = view.max[name] || 1;
  const idle = rgb(mix(MC.bg, MC.muted, 0.35));
  parts.forEach((seg, i) => {
    seg.setAttribute("fill", i < here ? rgb(here >= max ? (here > max ? MC.danger : MC.warning) : MC.accent) : idle);
  });
  view.fullRing[name].classList.toggle("on", here >= max);
  view.fullRing[name].setAttribute("stroke", rgb(here > max ? MC.danger : MC.warning));
}

function paintActiveLinks(turn) {
  // connections used by the moves of ``turn``; a landing does not use its
  // connection again (RULES.md 13)
  const R = S.replay;
  const usage = {};
  if (turn > 0) {
    const before = frame(turn - 1);
    for (const [d, p] of R.moves[turn - 1]) {
      if (d < 0 || d >= R.n) continue;
      const from = R.places[before[d]], to = R.places[p];
      let pair;
      if (to.includes(">")) pair = to.split(">");
      else if (from.includes(">")) continue;
      else pair = [from, to];
      const key = pair.sort().join("|");
      usage[key] = (usage[key] || 0) + 1;
    }
  }
  for (const [key, a] of Object.entries(view.active)) {
    const used = usage[key] || 0, cap = view.links[key].cap;
    a.g.classList.toggle("on", used > 0);
    a.g.classList.toggle("over", used > cap);
    a.label.textContent = used && (cap > 1 || used > cap) ? `${used}/${cap}` : "";
  }
}

function drawIssues(issues) {
  // map_layer._draw_issues: a pulsing red ring per zone, a red line per link
  const layer = view.issueLayer;
  layer.replaceChildren();
  const s = view.s;
  for (const issue of issues) {
    if (issue.link) {
      const l = view.links[[...issue.link].sort().join("|")];
      if (l) layer.append(svg("line", { x1: l.x1, y1: l.y1, x2: l.x2, y2: l.y2, stroke: rgb(MC.danger),
        "stroke-width": 4 * s, "stroke-linecap": "round" }));
    }
    for (const z of issue.zones) {
      const p = view.pos[z];
      if (p) layer.append(svg("circle", { cx: p[0], cy: p[1], r: view.radius[z] + 9 * s, fill: "none",
        stroke: rgb(MC.danger), "stroke-width": 3 * s, class: "mc-pulse" }));
    }
  }
}

/* ---------------------------------------------------------------- panel */

function renderPanel(shown, counts, issues) {
  const R = S.replay, m = S.map;
  $("mc-turn").textContent = shown;
  let transit = 0;
  for (const [p, c] of Object.entries(counts)) if (p.includes(">")) transit += c;
  const waiting = counts[m.start] || 0, delivered = counts[m.end] || 0;
  $("mc-route").textContent = R.n - waiting - delivered;
  $("mc-transit").textContent = transit;
  $("mc-waiting").textContent = waiting;
  $("mc-deliv").textContent = `${delivered} / ${R.n}`;
  const pct = R.n ? Math.round(100 * delivered / R.n) : 0;
  $("mc-pct").textContent = pct + "%";
  $("mc-progress").style.width = pct + "%";

  // the broken rule: of this turn, else the first one
  const rule = issues[0] || R.data.issues[0];
  $("mc-rule").hidden = !rule;
  if (rule) $("mc-rule-text").textContent = rule.turn ? `Turn ${rule.turn}: ${rule.message}` : rule.message;

  const box = $("mc-moves");
  box.replaceChildren();
  if (shown === 0) box.append(el("span", { class: "mc-dim", text: `All ${R.n} drones wait at ${m.start}.` }));
  else {
    const moves = R.data.moves[shown - 1] || [];
    if (!moves.length) box.append(el("span", { class: "mc-dim", text: "(no drawable move)" }));
    const limit = 24;
    moves.slice(0, limit).forEach(([id, p]) => {
      const flight = p.includes(">");
      box.append(el("span", { class: flight ? "mc-tok flight" : p === m.end ? "mc-tok goal" : "mc-tok",
        text: `D${id}-${flight ? p.replace(">", "-") : p}` }), " ");
    });
    if (moves.length > limit) box.append(el("span", { class: "mc-dim", text: `+ ${moves.length - limit} more` }));
  }
}

function drawBars() {
  // MOVES PER TURN: past turns teal, the current one bright, future dark
  const canvas = $("mc-bars");
  const dpr = window.devicePixelRatio || 1;
  const size = sizes["mc-bars"] || {};
  const w = size.w || 300, h = size.h || 46;
  if (!size.w) return;   // hidden (another inspector tab): drawn when shown
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const R = S.replay;
  if (!R || !R.perTurn.length) {
    ctx.fillStyle = rgb(MC.rule);
    ctx.fillRect(0, h - 2, w, 2);
    return;
  }
  const turns = R.perTurn.length;
  const buckets = Math.min(turns, Math.floor(w / 3));
  const per = turns / buckets;
  const peak = Math.max(1, ...R.perTurn);
  const bw = w / buckets;
  const current = R.shown;
  for (let b = 0; b < buckets; b++) {
    const from = Math.floor(b * per), to = Math.max(from + 1, Math.floor((b + 1) * per));
    let value = 0;
    for (let t = from; t < to; t++) value = Math.max(value, R.perTurn[t]);
    const bh = Math.max(2, value / peak * (h - 2));
    const isNow = current > from && current <= to;
    const past = to <= current;
    ctx.fillStyle = isNow ? rgb(MC.accent) : past ? rgb(mix(MC.bg, MC.accent, 0.45)) : rgb(mix(MC.bg, MC.edge, 0.75));
    ctx.fillRect(b * bw + 0.5, h - bh, Math.max(1, bw - 1.5), bh);
  }
  if (R.issueTurns.length) {
    ctx.fillStyle = rgb(MC.danger);
    for (const t of R.issueTurns) ctx.fillRect(Math.min(w - 2, (t - 1) / turns * w), 0, 2, 4);
  }
}

function drawTrack(t) {
  // the timeline at the bottom: ticks, progress, knob, broken turns
  const canvas = $("p-track");
  const dpr = window.devicePixelRatio || 1;
  const size = sizes["p-track"] || {};
  const w = size.w || 600, h = size.h || 28;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const R = S.replay;
  const pad = 8, y = h / 2, span = w - 2 * pad;
  ctx.fillStyle = rgb(MC.rule);
  ctx.fillRect(pad, y - 2, span, 4);
  if (!R || !R.moves.length) return;
  const turns = R.moves.length;
  const every = Math.max(1, Math.ceil(turns / Math.max(1, span / 9)));
  ctx.fillStyle = rgb(mix(MC.bg, MC.muted, 0.6));
  for (let k = 0; k <= turns; k += every) {
    const x = pad + k / turns * span;
    const major = k % (every * 5) === 0;
    ctx.fillRect(Math.round(x), y + 5, 1, major ? 7 : 4);
  }
  const x = pad + Math.min(1, t / turns) * span;
  ctx.fillStyle = rgb(MC.accent);
  ctx.fillRect(pad, y - 2, x - pad, 4);
  ctx.fillStyle = rgb(MC.danger);
  for (const k of R.issueTurns) {
    ctx.beginPath();
    ctx.arc(pad + k / turns * span, y - 8, 3, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.shadowColor = rgb(MC.accent);
  ctx.shadowBlur = 8;
  ctx.fillStyle = rgb(MC.accent);
  ctx.beginPath();
  ctx.arc(x, y, 7, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = rgb(MC.bg);
  ctx.beginPath();
  ctx.arc(x, y, 2.5, 0, Math.PI * 2);
  ctx.fill();
}

for (const [id, toTurn] of [["p-track", (fx) => fx], ["mc-bars", (fx) => fx]]) {
  const canvas = $(id);
  let down = false;
  const go = (event) => {
    const R = S.replay;
    if (!R || !R.moves.length) return;
    const rect = canvas.getBoundingClientRect();
    const pad = id === "p-track" ? 8 : 0;
    const fx = (event.clientX - rect.left - pad) / (rect.width - 2 * pad);
    seek(Math.round(toTurn(Math.max(0, Math.min(1, fx))) * R.moves.length + (id === "mc-bars" ? 0.5 : 0)));
  };
  canvas.addEventListener("pointerdown", (e) => { down = true; canvas.setPointerCapture(e.pointerId); go(e); });
  canvas.addEventListener("pointermove", (e) => { if (down) go(e); });
  canvas.addEventListener("pointerup", () => { down = false; });
}
/* ------------------------------------------------------- follow a drone */

function selectDrone(d) {
  const R = S.replay;
  if (!R) return;
  if (d !== null && (isNaN(d) || d < 0 || d >= R.n)) d = null;
  R.sel = d;
  view.routeLayer.replaceChildren();
  const box = $("p-drone");
  if (d === null) {
    $("p-follow").value = "";
    box.replaceChildren(el("span", { class: "mc-dim", text: "Click a drone on the map, or type its number." }));
    R.shown = -1;
    drawDrones();
    return;
  }
  const route = [{ turn: 0, place: 0 }];
  R.moves.forEach((turn, t) => { for (const [dd, p] of turn) if (dd === d) route.push({ turn: t + 1, place: p }); });
  const points = route.map((r) => R.coords[r.place]).filter(Boolean);
  view.routeLayer.append(svg("polyline", { points: points.map((c) => c.map((v) => v.toFixed(1)).join(",")).join(" "),
    class: "mc-route", "stroke-width": 7 * view.s }));
  const id = d + R.data.id_base;
  $("p-follow").value = id;
  const last = route[route.length - 1];
  const done = R.places[last.place] === S.map.end;
  const waited = Math.max(0, (done ? last.turn : R.moves.length) - (route.length - 1));
  box.replaceChildren(
    el("div", {}, el("b", { text: `D${id}` }), " · ",
      done ? `delivered in turn ${last.turn}` : el("span", { class: "mc-bad", text: "never delivered" }),
      ` · ${route.length - 1} moves · waited ${waited} turn${waited === 1 ? "" : "s"}`),
    el("div", { class: "mc-steps" }, ...route.map((r, i) => el("button", { title: "jump to this turn",
      onclick: () => seek(r.turn) }, i === 0 ? `0 ${S.map.start}` : `${r.turn} ${R.places[r.place].replace(">", "→")}`))));
  R.shown = -1;
  drawDrones();
}

$("p-follow").addEventListener("change", (e) => {
  const R = S.replay;
  if (!R) return;
  const value = e.target.value.trim();
  selectDrone(value === "" ? null : parseInt(value, 10) - R.data.id_base);
});

/* --------------------------------------------------------------- player */

let rafId = null, lastTs = null, speedIndex = SPEEDS.indexOf(1);

function setPlayIcon(playing) {
  $("p-play-icon").setAttribute("d", playing ? "M4 2 H7 V14 H4 Z M9 2 H12 V14 H9 Z" : "M4 2 L13 8 L4 14 Z");
}
function play() {
  const R = S.replay;
  if (!R || !R.moves.length) return;
  if (R.t >= R.moves.length) R.t = 0;
  R.playing = true;
  setPlayIcon(true);
  lastTs = null;
  cancelAnimationFrame(rafId);
  rafId = requestAnimationFrame(tick);
}
function stopPlaying() {
  if (S.replay) S.replay.playing = false;
  cancelAnimationFrame(rafId);
  setPlayIcon(false);
}
function tick(ts) {
  const R = S.replay;
  if (!R || !R.playing) return;
  if (lastTs !== null) {
    R.t = Math.min(R.moves.length, R.t + (ts - lastTs) / 1000 * TURNS_PER_SECOND * SPEEDS[speedIndex]);
  }
  lastTs = ts;
  drawDrones();
  if (R.t >= R.moves.length) { stopPlaying(); return; }
  rafId = requestAnimationFrame(tick);
}
function seek(turn) {
  const R = S.replay;
  if (!R) return;
  stopPlaying();
  R.t = Math.max(0, Math.min(R.moves.length, Math.round(turn)));
  R.shown = -1;
  R.activeTurn = -1;
  drawDrones();
}
function nextError() {
  const R = S.replay;
  if (!R || !R.issueTurns.length) return;
  const cur = Math.round(R.t);
  const next = R.issueTurns.find((t) => t > cur);
  seek(next === undefined ? R.issueTurns[0] : next);
}
function changeSpeed(step) {
  speedIndex = Math.max(0, Math.min(SPEEDS.length - 1, speedIndex + step));
  $("p-speed").textContent = SPEEDS[speedIndex] + "×";
}

$("p-play").addEventListener("click", () => (S.replay && S.replay.playing ? stopPlaying() : play()));
$("p-speed").addEventListener("click", () => {
  speedIndex = (speedIndex + 1) % SPEEDS.length;
  changeSpeed(0);
});
$("fit-view").addEventListener("click", fitView);
$("full-view").addEventListener("click", () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else if ($("mc").requestFullscreen) $("mc").requestFullscreen();
});
document.addEventListener("fullscreenchange", () => setTimeout(() => {
  drawBars();
  drawTrack(S.replay ? S.replay.t : 0);
}, 50));

document.addEventListener("keydown", (event) => {
  if ($("tab-maps").hidden || !S.map) return;
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
  const R = S.replay;
  const keys = {
    " ": () => R && (R.playing ? stopPlaying() : play()),
    ArrowLeft: () => R && seek(Math.ceil(R.t) - 1),
    ArrowRight: () => R && seek(Math.floor(R.t) + 1),
    Home: () => R && seek(0),
    End: () => R && seek(R.moves.length),
    r: () => R && (seek(0), play()), R: () => R && (seek(0), play()),
    e: nextError, E: nextError,
    "+": () => changeSpeed(1), "=": () => changeSpeed(1), "-": () => changeSpeed(-1),
    f: () => $("full-view").click(), F: () => $("full-view").click(),
    Escape: () => R && R.sel !== null && selectDrone(null),
  };
  if (keys[event.key]) { event.preventDefault(); keys[event.key](); }
});
