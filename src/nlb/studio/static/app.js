"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const ui = {
  state: null,
  tab: load("tab", "review"),
  selected: null,
  view: "crop",          // crop | full | negative
  picking: false,        // picking the film base on the negative view
  lastCaptured: null,
  knownFrames: null,     // names seen so far, to spot captures from the camera's own shutter button
  clipboard: null,
  stripSig: "",
  rollName: null,
  liveZoom: 1,
  busy: false,
};

function load(key, fallback) {
  try { return localStorage.getItem("nlb." + key) ?? fallback; } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem("nlb." + key, value); } catch { /* private mode etc. */ }
}

// ---------- API ----------

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

let toastTimer;
function toast(msg, error = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show" + (error ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), error ? 6000 : 2500);
}

async function act(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); }
}

async function refresh() {
  try {
    const s = await api("GET", "/api/state");
    ui.state = s;
    render();
  } catch (e) {
    $("#cam-pill-text").textContent = "server offline";
    $("#cam-pill").className = "cam-pill error";
  }
}

// ---------- helpers ----------

const frames = () => (ui.state ? ui.state.frames : []);
const frameByName = (n) => frames().find((f) => f.name === n);
const current = () => frameByName(ui.selected);
const imgUrl = (f, view, thumb) =>
  `/api/frames/${encodeURIComponent(f.name)}/image?roll=${encodeURIComponent(ui.state.roll)}` +
  `&view=${view}&h=${f.hash}${thumb ? "&size=thumb" : ""}`;
const paramDefault = (key) => ui.state.params.find((p) => p.key === key).default;

function select(name) {
  if (!name) return;
  ui.selected = name;
  save("selected." + ui.rollName, name);
  render();
  const el = $(`.thumb[data-name="${CSS.escape(name)}"]`);
  if (el) el.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function step(delta) {
  const fs = frames();
  const i = fs.findIndex((f) => f.name === ui.selected);
  const next = fs[Math.min(fs.length - 1, Math.max(0, i + delta))];
  if (next) select(next.name);
}

async function patchFrame(name, patch) {
  await api("PATCH", `/api/frames/${encodeURIComponent(name)}`, patch);
  await refresh();
}

// ---------- render ----------

function render() {
  const s = ui.state;
  if (!s) return;
  document.body.className = "tab-" + ui.tab;
  $$(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === ui.tab));
  if (s.roll !== ui.rollName) enterRoll(s.roll);
  renderRollSelect();
  $("#roll-path").textContent = s.library;
  $("#roll-path").title = s.folder;

  if (!frameByName(ui.selected)) ui.selected = s.frames.length ? s.frames[s.frames.length - 1].name : null;
  spotNewCaptures();
  renderCameraPill();
  renderJob();
  renderStrip();
  renderCapture();
  renderReview();
}

function enterRoll(name) {
  // a different roll: forget per-roll UI state
  ui.rollName = name;
  ui.selected = load("selected." + name, null);
  ui.knownFrames = null;
  ui.lastCaptured = null;
  ui.stripSig = "";
  ui.picking = false;
  $("#strip").replaceChildren();
  delete $("#main-img").dataset.want;
  $("#main-img").removeAttribute("src");
  $("#last-img").removeAttribute("src");
}

const NEW_ROLL = "\u0000new";

function renderRollSelect() {
  const sel = $("#roll-select");
  const s = ui.state;
  const sig = s.rolls.join("|") + "#" + s.roll;
  if (sel.dataset.sig === sig) return;
  sel.dataset.sig = sig;
  sel.replaceChildren(...s.rolls.map((r) => new Option(r, r, false, r === s.roll)),
    new Option("+ New roll…", NEW_ROLL));
}

function suggestRollName() {
  const nums = ui.state.rolls.map((r) => /^roll(\d+)$/.exec(r)).filter(Boolean).map((m) => +m[1]);
  return "roll" + String(Math.max(0, ...nums) + 1).padStart(2, "0");
}

async function chooseRoll(value) {
  if (value === NEW_ROLL) {
    const name = prompt("Name for the new roll folder:", suggestRollName());
    if (!name) { $("#roll-select").dataset.sig = ""; renderRollSelect(); return; }
    await act(async () => { ui.state = await api("POST", "/api/rolls", { name: name.trim() }); render(); toast(`Created ${name.trim()}`); });
  } else {
    await act(async () => { ui.state = await api("POST", "/api/rolls/open", { name: value }); render(); });
  }
  $("#roll-select").dataset.sig = "";
  renderRollSelect();
}

function spotNewCaptures() {
  const names = frames().map((f) => f.name);
  if (ui.knownFrames) {
    const fresh = names.filter((n) => !ui.knownFrames.has(n));
    if (fresh.length) {
      ui.lastCaptured = fresh[fresh.length - 1];
      if (ui.tab === "capture") ui.selected = ui.lastCaptured;
    }
  } else {
    ui.lastCaptured = names[names.length - 1] ?? null;  // after a reload, reshoot the newest frame
  }
  ui.knownFrames = new Set(names);
}

const CAMERA_LABELS = { unavailable: "no gphoto2", nocamera: "no camera" };

function renderCameraPill() {
  const c = ui.state.camera;
  const pill = $("#cam-pill");
  const busy = c.busy || c.status === "capturing" || c.status === "connecting";
  pill.className = "cam-pill " + (c.status === "error" ? "error" : busy ? "busy" : c.status === "ready" ? "ready" : "");
  const label = CAMERA_LABELS[c.status] || c.status;
  $("#cam-pill-text").textContent = c.model ? `${c.model} · ${label}` : label;
  pill.title = c.message || "camera status";
  const tab = $('.tab[data-tab="capture"]');
  tab.classList.toggle("unavailable", c.status === "unavailable");
  tab.title = c.status === "unavailable" ? c.message : "";
}

const cameraConnected = () => ["ready", "capturing"].includes(ui.state?.camera.status);

// why the shutter is grayed out, or "" when it isn't
function captureBlocker(c) {
  if (cameraConnected()) return "";
  if (c.status === "unavailable") return "Capture unavailable: gphoto2 isn't installed.";
  if (c.status === "nocamera") return "No camera found. Plug one in and it connects automatically.";
  if (c.status === "connecting") return "Connecting to the camera…";
  return "Camera not connected.";
}

function renderJob() {
  const j = ui.state.job;
  const el = $("#job");
  if (j.running) el.textContent = `Rendering ${j.done + 1}/${j.total} (${j.current})…`;
  else if (j.total) el.textContent = `Rendered ${j.done - j.errors.length}/${j.total}` + (j.errors.length ? ` · ${j.errors.length} failed` : "");
  else el.textContent = "";
  el.title = j.errors.join("\n") || (j.out ? `→ ${j.out}` : "");
  $("#render-btn").disabled = j.running || !frames().some((f) => !f.rejected);
}

function renderStrip() {
  const fs = frames();
  const sig = fs.map((f) => `${f.name}:${f.hash}:${f.rejected}:${!!f.crop}`).join("|");
  if (sig !== ui.stripSig) {
    ui.stripSig = sig;
    const strip = $("#strip");
    const existing = new Map([...strip.children].map((el) => [el.dataset.name, el]));
    strip.replaceChildren(...fs.map((f) => {
      let el = existing.get(f.name);
      if (!el) {
        el = document.createElement("button");
        el.className = "thumb";
        el.dataset.name = f.name;
        el.innerHTML = `<img alt="" loading="lazy"><span class="label"></span>`;
        el.addEventListener("click", () => select(f.name));
      }
      el.querySelector(".label").textContent = f.name;
      el.classList.toggle("rejected", !!f.rejected);
      el.classList.toggle("pending", !f.crop);
      const img = el.querySelector("img");
      if (f.crop) {
        const url = imgUrl(f, "crop", true);
        if (img.getAttribute("src") !== url) img.src = url;
      }
      return el;
    }));
  }
  $$(".thumb").forEach((el) => el.classList.toggle("sel", el.dataset.name === ui.selected));
}

// ---------- capture tab ----------

function renderCapture() {
  const c = ui.state.camera;
  const connected = cameraConnected();
  const unavailable = c.status === "unavailable";
  const live = $("#live");
  live.classList.toggle("connected", connected);
  live.classList.toggle("unavailable", unavailable);
  $("#live-message").textContent = c.status === "connecting" ? "Connecting…" : c.message || "Camera not connected.";
  $("#connect-btn").disabled = c.status === "connecting" || unavailable;
  $("#connect-btn").hidden = unavailable;
  $("#connect-hint").hidden = unavailable || c.status === "nocamera";  // the message says it
  $("#cam-model").textContent = c.model || "—";
  $("#cam-msg").textContent = connected ? c.message : "";
  $("#capture-btn").disabled = !connected || ui.busy || c.busy;
  $("#disconnect-btn").disabled = !connected;
  const why = captureBlocker(c);
  $("#capture-why").textContent = why || "The shutter button on the camera works too.";
  $("#capture-why").classList.toggle("blocked", !!why);
  $("#next-name").textContent = ui.state.next_name;

  // live view stream only while it is on screen (the server runs live view only for viewers)
  const img = $("#live-img");
  const want = ui.tab === "capture" && connected;
  if (want && !img.dataset.on) { img.src = "/api/camera/live?t=" + Date.now(); img.dataset.on = "1"; }
  if (!want && img.dataset.on) { img.src = "data:,"; delete img.dataset.on; }
  $("#live-frame").classList.toggle("invert", $("#live-invert").checked);

  renderCameraConfig(c.config || {});

  const last = frameByName(ui.lastCaptured);
  $("#last-section").hidden = !last;
  if (last) {
    $("#last-name").textContent = last.name;
    if (last.crop) {
      const url = imgUrl(last, "crop", false);
      if ($("#last-img").getAttribute("src") !== url) $("#last-img").src = url;
    }
    $("#reshoot-btn").disabled = !connected || ui.busy;
  }
}

function renderCameraConfig(config) {
  const box = $("#cam-config");
  const sig = JSON.stringify(config);
  if (box.dataset.sig === sig || box.contains(document.activeElement)) return;
  box.dataset.sig = sig;
  box.replaceChildren(...Object.entries(config).map(([name, w]) => {
    const div = document.createElement("div");
    div.className = "cfg";
    const label = document.createElement("label");
    label.textContent = w.label || name;
    let input;
    if (w.choices.length) {
      input = document.createElement("select");
      for (const ch of w.choices) input.add(new Option(ch, ch, false, ch === w.value));
    } else {
      input = document.createElement("select");
      input.add(new Option(String(w.value), String(w.value)));
    }
    input.disabled = w.readonly;
    input.addEventListener("change", () => act(async () => {
      await api("POST", "/api/camera/config", { name, value: input.value });
      await refresh();
    }));
    div.append(label, input);
    return div;
  }));
}

async function capture(reshoot) {
  if (ui.busy) return;
  ui.busy = true;
  renderCapture();
  try {
    const r = await api("POST", "/api/camera/capture", reshoot ? { reshoot } : {});
    ui.lastCaptured = r.name;
    ui.selected = r.name;
    await refresh();
    toast(`${reshoot ? "Reshot" : "Captured"} ${r.name}`);
  } catch (e) {
    toast(e.message, true);
  } finally {
    ui.busy = false;
    await refresh();
  }
}

// ---------- review tab ----------

function renderReview() {
  const f = current();
  const stage = $("#stage");
  stage.classList.toggle("no-frames", !f);
  stage.classList.toggle("view-full", ui.view === "full");
  $$("#view-seg button").forEach((b) => b.classList.toggle("on", b.dataset.view === ui.view));
  $("#view-hint").textContent = ui.picking ? "Click the clear film rebate (between the sprocket holes and the picture)"
    : ui.view === "full" ? "Drag to move or resize the crop" : "";
  const wrap = $("#img-wrap");
  wrap.classList.toggle("cropping", ui.view === "full" && !!f);
  wrap.classList.toggle("picking", ui.picking);

  if (f && f.crop) showMain(imgUrl(f, ui.view, false));
  if (f) $("#frame-name").textContent = f.name;
  renderFramePanel(f);
  renderRollPanel();
  layoutCrop();
}

function showMain(url) {
  const img = $("#main-img");
  if (img.dataset.want === url) return;
  img.dataset.want = url;
  const pre = new Image();
  pre.onload = () => {
    if (img.dataset.want !== url) return;
    img.src = url;
    requestAnimationFrame(layoutCrop);
  };
  pre.src = url;
}

function slider(container, { key, label, min, max, step, value, onInput, onChange }) {
  let el = container.querySelector(`[data-key="${key}"]`);
  if (!el) {
    el = document.createElement("div");
    el.className = "slider";
    el.dataset.key = key;
    el.innerHTML = `<div class="top"><span></span><output></output></div><input type="range">`;
    el.querySelector("span").textContent = label;
    const input = el.querySelector("input");
    Object.assign(input, { min, max, step });
    input.addEventListener("input", () => { el.querySelector("output").textContent = fmt(input.value); onInput?.(+input.value); });
    input.addEventListener("pointerdown", () => (el.dataset.dragging = "1"));
    input.addEventListener("change", () => { delete el.dataset.dragging; onChange(+input.value); });
    input.addEventListener("dblclick", () => { input.value = el.dataset.default; input.dispatchEvent(new Event("input")); onChange(+input.value); });
    container.append(el);
  }
  const input = el.querySelector("input");
  if (!el.dataset.dragging) {  // don't fight the user's thumb while polling
    input.value = value;
    el.querySelector("output").textContent = fmt(value);
  }
  return el;
}
const fmt = (v) => (+v).toFixed(2).replace(/^-?0\.00$/, "0.00");

function renderFramePanel(f) {
  $$("#review-panel button").forEach((b) => (b.disabled = !f && !b.closest("section:last-child")));
  if (!f) return;
  $("#reject-btn").classList.toggle("danger-on", !!f.rejected);
  $("#reject-btn").firstChild.textContent = f.rejected ? "Rejected " : "Reject ";

  const angle = slider($("#angle-slider"), {
    key: "angle", label: "Straighten (°)", min: -5, max: 5, step: 0.05, value: f.angle || 0,
    onChange: (v) => act(() => patchFrame(ui.selected, { angle: v })),
  });
  angle.dataset.default = 0;

  const box = $("#param-sliders");
  for (const p of ui.state.params) {
    const el = slider(box, {
      ...p, value: f.params?.[p.key] ?? p.default,
      onInput: (v) => debouncedParam(p.key, v),
      onChange: (v) => debouncedParam(p.key, v, true),
    });
    el.dataset.default = p.default;
  }
  $("#paste-params").disabled = !ui.clipboard;
  $("#paste-all").disabled = !ui.clipboard;
}

// live-ish slider feedback: send while dragging, at most one request in flight
let paramTimer, paramInFlight = false, paramPending = null;
function debouncedParam(key, value, now = false) {
  paramPending = { name: ui.selected, params: { ...(paramPending?.name === ui.selected ? paramPending.params : {}), [key]: value } };
  clearTimeout(paramTimer);
  paramTimer = setTimeout(flushParams, now ? 0 : 120);
}
async function flushParams() {
  if (paramInFlight || !paramPending) return;
  const { name, params } = paramPending;
  paramPending = null;
  paramInFlight = true;
  try { await patchFrame(name, { params }); } catch (e) { toast(e.message, true); }
  paramInFlight = false;
  if (paramPending) flushParams();
}

function renderRollPanel() {
  const st = ui.state.settings;
  $$("#film-seg button").forEach((b) => b.classList.toggle("on", b.dataset.film === st.film));
  $("#flip").checked = !!st.flip;
  const sw = $("#base-swatch");
  if (st.base) {
    const m = Math.max(...st.base) || 1;
    const [r, g, b] = st.base.map((v) => Math.round(255 * Math.pow(v / m, 1 / 2.2)));
    sw.style.background = `rgb(${r},${g},${b})`;
    $("#base-text").textContent = st.base.map((v) => v.toFixed(3)).join(" / ");
  } else {
    sw.style.background = "";
    $("#base-text").textContent = "auto";
  }
  $("#auto-base").disabled = !st.base;
  $("#pick-base").classList.toggle("on", ui.picking);
  $("#levels-text").textContent = st.levels ? "locked to roll" : "per frame";
  $("#unlock-levels").disabled = !st.levels;
  $("#out-path").textContent = `Renders go to ${ui.state.out}`;
}

// ---------- crop editor ----------

function imageBox() {
  const img = $("#main-img");
  const wrap = $("#img-wrap").getBoundingClientRect();
  const r = img.getBoundingClientRect();
  return { left: r.left - wrap.left, top: r.top - wrap.top, width: r.width, height: r.height };
}

let drag = null;   // { mode, handle, start: [x,y,w,h], p0: [x,y] }
let dragCrop = null;

function layoutCrop() {
  const f = current();
  if (!f || ui.view !== "full" || !f.crop) return;
  const box = imageBox();
  Object.assign($("#crop-layer").style, {
    left: box.left + "px", top: box.top + "px", width: box.width + "px", height: box.height + "px",
  });
  const [x, y, w, h] = dragCrop || f.crop;
  Object.assign($("#crop-rect").style, {
    left: x * 100 + "%", top: y * 100 + "%", width: w * 100 + "%", height: h * 100 + "%",
  });
}

function pointerNorm(e) {
  const r = $("#crop-layer").getBoundingClientRect();
  return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function cropFromDrag(p) {
  const [sx, sy, sw, sh] = drag.start;
  const dx = p[0] - drag.p0[0], dy = p[1] - drag.p0[1];
  if (drag.mode === "move") {
    return [clamp(sx + dx, 0, 1 - sw), clamp(sy + dy, 0, 1 - sh), sw, sh];
  }
  let x0 = sx, y0 = sy, x1 = sx + sw, y1 = sy + sh;
  const hd = drag.handle;
  if (drag.mode === "draw") { x0 = drag.p0[0]; y0 = drag.p0[1]; x1 = p[0]; y1 = p[1]; }
  else {
    if (hd.includes("w")) x0 = sx + dx;
    if (hd.includes("e")) x1 = sx + sw + dx;
    if (hd.includes("n")) y0 = sy + dy;
    if (hd.includes("s")) y1 = sy + sh + dy;
  }
  if (x1 < x0) [x0, x1] = [x1, x0];
  if (y1 < y0) [y0, y1] = [y1, y0];
  x0 = clamp(x0, 0, 1); x1 = clamp(x1, 0, 1); y0 = clamp(y0, 0, 1); y1 = clamp(y1, 0, 1);

  if ($("#lock-aspect").checked) {
    const box = $("#crop-layer").getBoundingClientRect();
    const W = box.width, H = box.height;
    const landscape = drag.mode === "draw" ? Math.abs(x1 - x0) * W >= Math.abs(y1 - y0) * H : sw * W >= sh * H;
    const R = landscape ? 1.5 : 1 / 1.5;
    const horizontal = drag.mode === "draw" || /[ew]/.test(hd);
    if (horizontal) {
      const h = ((x1 - x0) * W) / R / H;
      if (drag.mode === "draw") { if (p[1] < drag.p0[1]) y0 = y1 - h; else y1 = y0 + h; }
      else if (hd.includes("n")) y0 = y1 - h;
      else if (hd.includes("s")) y1 = y0 + h;
      else { const cy = (sy + sh / 2); y0 = cy - h / 2; y1 = cy + h / 2; }
    } else {
      const w = ((y1 - y0) * H * R) / W;
      const cx = sx + sw / 2;
      x0 = cx - w / 2; x1 = cx + w / 2;
    }
    x0 = clamp(x0, 0, 1); x1 = clamp(x1, 0, 1); y0 = clamp(y0, 0, 1); y1 = clamp(y1, 0, 1);
  }
  return [x0, y0, Math.max(0.01, x1 - x0), Math.max(0.01, y1 - y0)];
}

function initCropEditor() {
  const layer = $("#crop-layer");
  layer.addEventListener("pointerdown", (e) => {
    const f = current();
    if (!f || !f.crop) return;
    e.preventDefault();
    layer.setPointerCapture(e.pointerId);
    const handle = e.target.dataset.h;
    const mode = handle ? "resize" : e.target.id === "crop-rect" ? "move" : "draw";
    drag = { mode, handle: handle || "", start: f.crop.slice(), p0: pointerNorm(e) };
  });
  layer.addEventListener("pointermove", (e) => {
    if (!drag) return;
    dragCrop = cropFromDrag(pointerNorm(e));
    layoutCrop();
  });
  const end = () => {
    if (!drag) return;
    const crop = dragCrop;
    drag = null;
    if (!crop) return;
    act(async () => { await patchFrame(ui.selected, { crop }); dragCrop = null; layoutCrop(); });
  };
  layer.addEventListener("pointerup", end);
  layer.addEventListener("pointercancel", end);
  window.addEventListener("resize", layoutCrop);

  $("#main-img").addEventListener("click", (e) => {
    if (!ui.picking) return;
    const r = e.target.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    act(async () => {
      await api("POST", "/api/base", { name: ui.selected, x, y });
      ui.picking = false;
      ui.view = "crop";
      await refresh();
      toast("Film base set for the roll");
    });
  });
}

// ---------- wiring ----------

function setTab(tab) {
  ui.tab = tab;
  save("tab", tab);
  render();
}

function setView(view) {
  ui.view = view;
  if (view !== "negative") ui.picking = false;
  render();
}

async function rotate(delta) {
  const f = current();
  if (f) await act(() => patchFrame(f.name, { rotation: (f.rotation + delta + 360) % 360 }));
}

async function toggleReject() {
  const f = current();
  if (f) await act(() => patchFrame(f.name, { rejected: !f.rejected }));
}

function wire() {
  $$(".tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
  $("#roll-select").addEventListener("change", (e) => chooseRoll(e.target.value));
  $$("#view-seg button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  $("#connect-btn").addEventListener("click", () => act(async () => {
    const p = api("POST", "/api/camera/connect");
    setTimeout(refresh, 100);
    await p;
    await refresh();
  }).then(refresh));
  $("#disconnect-btn").addEventListener("click", () => act(async () => { await api("POST", "/api/camera/disconnect"); await refresh(); }));
  $("#capture-btn").addEventListener("click", () => capture());
  $("#reshoot-btn").addEventListener("click", () => ui.lastCaptured && capture(ui.lastCaptured));
  $("#last-review-btn").addEventListener("click", () => { ui.selected = ui.lastCaptured; setTab("review"); });
  $("#live-invert").addEventListener("change", renderCapture);
  $$("#live-zoom button").forEach((b) => b.addEventListener("click", () => {
    ui.liveZoom = +b.dataset.zoom;
    $$("#live-zoom button").forEach((x) => x.classList.toggle("on", x === b));
    $("#live-img").style.transform = `scale(${ui.liveZoom})`;
  }));
  $("#live-frame").addEventListener("click", (e) => {
    const img = $("#live-img");
    const r = img.getBoundingClientRect();
    if (ui.liveZoom === 1) return;
    // r is the scaled box; convert the click into the unscaled image's percentage
    const ox = ((e.clientX - r.left) / r.width) * 100, oy = ((e.clientY - r.top) / r.height) * 100;
    img.style.transformOrigin = `${clamp(ox, 0, 100)}% ${clamp(oy, 0, 100)}%`;
  });

  $("#rot-ccw").addEventListener("click", () => rotate(-90));
  $("#rot-cw").addEventListener("click", () => rotate(90));
  $("#reject-btn").addEventListener("click", toggleReject);
  $("#reset-params").addEventListener("click", () => act(async () => {
    const params = Object.fromEntries(ui.state.params.map((p) => [p.key, p.default]));
    await patchFrame(ui.selected, { params, angle: 0 });
  }));
  $("#copy-params").addEventListener("click", () => {
    const f = current();
    if (!f) return;
    ui.clipboard = { rotation: f.rotation, angle: f.angle, params: { ...f.params } };
    toast(`Copied ${f.name}'s rotation and adjustments`);
    render();
  });
  $("#paste-params").addEventListener("click", () => act(() => patchFrame(ui.selected, ui.clipboard)));
  $("#paste-all").addEventListener("click", () => act(async () => {
    for (const f of frames()) await api("PATCH", `/api/frames/${encodeURIComponent(f.name)}`, ui.clipboard);
    await refresh();
    toast(`Pasted to ${frames().length} frames`);
  }));

  $$("#film-seg button").forEach((b) => b.addEventListener("click", () =>
    act(async () => { await api("PATCH", "/api/settings", { film: b.dataset.film }); await refresh(); })));
  $("#flip").addEventListener("change", (e) =>
    act(async () => { await api("PATCH", "/api/settings", { flip: e.target.checked }); await refresh(); }));
  $("#pick-base").addEventListener("click", () => {
    if (!current()) return;
    ui.picking = !ui.picking;
    ui.view = ui.picking ? "negative" : "crop";
    render();
  });
  $("#auto-base").addEventListener("click", () => act(async () => { await api("POST", "/api/base", { auto: true }); await refresh(); }));
  $("#lock-levels").addEventListener("click", () => act(async () => {
    toast("Analyzing the roll…");
    await api("POST", "/api/levels", { lock: true });
    await refresh();
    toast("Levels locked to the roll");
  }));
  $("#unlock-levels").addEventListener("click", () => act(async () => { await api("POST", "/api/levels", { lock: false }); await refresh(); }));
  $("#render-btn").addEventListener("click", () => act(async () => {
    const kept = frames().filter((f) => !f.rejected).length;
    await api("POST", "/api/render", {});
    toast(`Rendering ${kept} frames to ${ui.state.out}`);
    await refresh();
  }));

  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, select, textarea") && e.target.type !== "range" && e.target.type !== "checkbox") return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key;
    if (ui.tab === "capture" && k === " ") { e.preventDefault(); if (cameraConnected()) capture(); return; }
    if (ui.tab === "capture" && (k === "r" || k === "R") && ui.lastCaptured) { if (cameraConnected()) capture(ui.lastCaptured); return; }
    if (e.target.type === "range") return;
    if (k === "ArrowLeft") { e.preventDefault(); step(-1); }
    else if (k === "ArrowRight") { e.preventDefault(); step(1); }
    else if (ui.tab !== "review") return;
    else if (k === "x" || k === "X") toggleReject();
    else if (k === "[" || e.code === "BracketLeft") rotate(-90);
    else if (k === "]" || e.code === "BracketRight") rotate(90);
    else if (k === "v" || k === "V") setView("crop");
    else if (k === "c" || k === "C") setView("full");
    else if (k === "n" || k === "N") setView("negative");
    else if (k === "Escape") { ui.picking = false; setView("crop"); }
  });
}

wire();
initCropEditor();
refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 1000);
