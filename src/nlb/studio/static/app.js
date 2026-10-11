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
  liveSrc: "live",       // capture viewer: live | test
  testView: load("testView", "frame"),  // frame | result | sensor
  testSeen: null,        // test shot id the viewer last switched to
  loadingMain: false,    // main image requested but not loaded yet (darktable takes seconds)
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
  const sig = fs.map((f) => `${f.name}:${f.hash}:${f.rejected}:${!!f.crop}:${f.engine}`).join("|");
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
      el.querySelector(".label").textContent = f.name + (f.engine === "darktable" ? " · dt" : "");
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
  $("#next-name").textContent = ui.state.next_name;

  const testMode = ui.state.shoot_mode === "test";
  $$("#shoot-mode button").forEach((b) => b.classList.toggle("on", b.dataset.mode === ui.state.shoot_mode));
  $("#capture-label").textContent = testMode ? "Test shot" : "Capture";
  const why = captureBlocker(c);
  $("#capture-why").textContent = why || (testMode
    ? "Each shot gets feedback first; keep the ones you like. The camera's shutter button works too."
    : "Shots go straight into the roll. The camera's shutter button works too.");
  $("#capture-why").classList.toggle("blocked", !!why);

  const test = ui.state.test;
  if (test && test.status !== "analyzing" && ui.testSeen !== test.id) {
    ui.testSeen = test.id;  // a fresh result: show it
    if (ui.tab === "capture") ui.liveSrc = "test";
  }
  if (!test) ui.liveSrc = "live";
  const showTest = ui.liveSrc === "test";
  live.classList.toggle("show-test", showTest);
  $("#live-src").hidden = !test;
  $$("#live-src button").forEach((b) => b.classList.toggle("on", b.dataset.src === ui.liveSrc));
  renderTest(test, showTest);

  // live view stream only while it is on screen (the server runs live view only for viewers)
  const img = $("#live-img");
  const want = ui.tab === "capture" && connected && !showTest;
  if (want && !img.dataset.on) { img.src = "/api/camera/live?t=" + Date.now(); img.dataset.on = "1"; resetFocusPeak(); }
  if (!want && img.dataset.on) { img.src = "data:,"; delete img.dataset.on; }
  if (want) pollFocus();
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

// ---------- test shots ----------

const VERDICT = { good: "good", adjust: "adjust", bad: "fix first" };
const TEST_HINT = { frame: "dashed box: picture found", result: "as it would join the roll", sensor: "red: clipped" };

function renderTest(t, showing) {
  $("#test-section").hidden = !t;
  if (!t) return;
  const r = t.report;
  $("#test-name").textContent = "#" + t.id;
  const verdict = $("#test-verdict");
  verdict.className = "verdict " + (r ? r.verdict : "");
  verdict.textContent = r ? VERDICT[r.verdict] : "";
  $("#test-summary").textContent = t.status === "analyzing" ? "Analyzing…" : t.status === "error" ? t.error : r.summary;
  const list = $("#test-checks");
  const sig = JSON.stringify([t.id, t.status, r]);
  if (list.dataset.sig !== sig) {
    list.dataset.sig = sig;
    list.replaceChildren(...(r ? r.checks : []).map((c) => {
      const li = document.createElement("li");
      li.className = c.status;
      li.innerHTML = `<span class="dot"></span><div><span class="label"></span> <span class="value"></span></div>`;
      li.querySelector(".label").textContent = c.label;
      li.querySelector(".value").textContent = c.value;
      if (c.advice) {
        const a = document.createElement("div");
        a.className = "advice";
        a.textContent = c.advice;
        li.append(a);
      }
      return li;
    }));
  }
  $("#keep-btn").firstChild.textContent = `Keep as ${ui.state.next_name} `;
  $("#keep-btn").disabled = ui.busy;
  const replace = $("#replace-btn");
  replace.hidden = !frameByName(ui.lastCaptured);
  replace.textContent = `Replace ${ui.lastCaptured}`;
  replace.disabled = ui.busy;

  $$("#test-view-seg button").forEach((b) => b.classList.toggle("on", b.dataset.view === ui.testView));
  $("#test-hint").textContent = TEST_HINT[ui.testView] || "";
  const img = $("#test-img");
  $("#test-pending").textContent = t.status === "analyzing" ? "Analyzing test shot…" : t.status === "error" ? t.error : "";
  if (img.dataset.id !== String(t.id)) {  // never show the previous shot under a new one
    img.removeAttribute("src");
    delete img.dataset.want;
    img.dataset.id = t.id;
  }
  if (showing && t.status === "ready") {
    const url = `/api/test/image?id=${t.id}&view=${ui.testView}&s=${hashText(JSON.stringify(ui.state.settings))}`;
    if (img.dataset.want !== url) {
      img.dataset.want = url;
      const pre = new Image();
      pre.onload = () => {
        if (img.dataset.want !== url) return;
        img.src = url;
        requestAnimationFrame(layoutTestBox);
      };
      pre.src = url;
    }
  }
  layoutTestBox();
}

function hashText(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

function layoutTestBox() {
  const t = ui.state && ui.state.test;
  const framed = t && t.report && t.report.checks.some((c) => c.key === "framing");  // film was found
  const pic = framed && t.metrics.picture;
  const img = $("#test-img");
  const layer = $("#test-layer");
  // the box is in sensor space: the frame and exposure views, not the (mirrored, cropped) result
  layer.hidden = !(pic && ui.testView !== "result" && img.getAttribute("src") && ui.liveSrc === "test");
  if (layer.hidden) return;
  const wrap = $("#test-wrap").getBoundingClientRect();
  const r = img.getBoundingClientRect();
  Object.assign(layer.style, { left: r.left - wrap.left + "px", top: r.top - wrap.top + "px", width: r.width + "px", height: r.height + "px" });
  const [x, y, w, h] = pic;
  Object.assign($("#test-box").style, { left: x * 100 + "%", top: y * 100 + "%", width: w * 100 + "%", height: h * 100 + "%" });
}

function shoot() {
  return ui.state && ui.state.shoot_mode === "test" ? testShot() : capture();
}

async function testShot() {
  if (ui.busy) return;
  ui.busy = true;
  renderCapture();
  try {
    const r = await api("POST", "/api/test/capture", {});
    toast(`Test shot #${r.id}: analyzing…`);
  } catch (e) {
    toast(e.message, true);
  } finally {
    ui.busy = false;
    await refresh();
  }
}

async function keepTest(replace) {
  const t = ui.state && ui.state.test;
  if (!t || ui.busy) return;
  const reshoot = replace ? ui.lastCaptured : null;
  if (replace && !frameByName(reshoot)) return;
  ui.busy = true;
  try {
    const r = await api("POST", "/api/test/keep", reshoot ? { reshoot } : {});
    ui.lastCaptured = r.name;
    ui.liveSrc = "live";
    toast(reshoot ? `Replaced ${r.name} (old raw in the roll's trash)` : `Kept as ${r.name}`);
  } catch (e) {
    toast(e.message, true);
  } finally {
    ui.busy = false;
    await refresh();
  }
}

async function discardTest() {
  if (!ui.state || !ui.state.test) return;
  await act(async () => {
    await api("POST", "/api/test/discard");
    ui.liveSrc = "live";
    await refresh();
    toast("Test shot discarded");
  });
}

function setLiveSrc(src) {
  if (src === "test" && !(ui.state && ui.state.test)) return;
  ui.liveSrc = src;
  renderCapture();
}

// ---------- live view focus meter ----------
// The score is only comparable within one scene and region, so it shows as a fraction of
// the best since the last reset (peak hold): turn through focus, then come back to 100%.

const focusMeter = { peak: 0, smooth: null, seq: -1, polling: false };
const FOCUS_SMOOTH = 0.4;   // weight of the newest frame: live-view noise jitters the score
const FOCUS_NEAR = 0.9, FOCUS_PEAK = 0.97;

function focusRegion() {
  // the part of the live frame on screen: zoom s about origin o shows [o(1 - 1/s), +1/s]
  const s = ui.liveZoom;
  if (s === 1) return [0, 0, 1, 1];
  const [ox, oy] = ($("#live-img").style.transformOrigin || "50% 50%").split(" ").map((v) => parseFloat(v) / 100);
  return [ox * (1 - 1 / s), oy * (1 - 1 / s), 1 / s, 1 / s];
}

function resetFocusPeak() {
  Object.assign(focusMeter, { peak: 0, smooth: null });
  renderFocus();
}

function renderFocus() {
  const { peak, smooth } = focusMeter;
  const frac = peak > 0 && smooth != null ? smooth / peak : null;
  $("#focus-fill").style.width = frac == null ? "0" : `${(frac * 100).toFixed(1)}%`;
  $("#focus-pct").textContent = frac == null ? "—" : `${Math.round(frac * 100)}%`;
  $("#focus-meter").classList.toggle("peak", frac != null && frac >= FOCUS_PEAK);
  $("#focus-meter").classList.toggle("near", frac != null && frac >= FOCUS_NEAR && frac < FOCUS_PEAK);
}

async function pollFocus() {
  if (focusMeter.polling) return;
  focusMeter.polling = true;
  while ($("#live-img").dataset.on && !document.hidden) {
    const [x, y, w, h] = focusRegion().map((v) => v.toFixed(4));
    try {
      const r = await api("GET", `/api/camera/focus?x=${x}&y=${y}&w=${w}&h=${h}`);
      if (r.seq !== focusMeter.seq && r.score != null) {
        focusMeter.seq = r.seq;
        focusMeter.smooth = focusMeter.smooth == null ? r.score
          : FOCUS_SMOOTH * r.score + (1 - FOCUS_SMOOTH) * focusMeter.smooth;
        focusMeter.peak = Math.max(focusMeter.peak, focusMeter.smooth);
        renderFocus();
      }
    } catch { /* camera busy or gone: the status line says so */ }
    await new Promise((r) => setTimeout(r, 150));
  }
  focusMeter.polling = false;
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
    : ui.loadingMain && f?.engine === "darktable" && ui.view !== "negative" ? "Developing in darktable…"
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
  ui.loadingMain = true;
  const pre = new Image();
  pre.onload = () => {
    if (img.dataset.want !== url) return;
    ui.loadingMain = false;
    img.src = url;
    requestAnimationFrame(layoutCrop);
    renderReview();
  };
  pre.onerror = async () => {
    if (img.dataset.want !== url) return;
    ui.loadingMain = false;
    const data = await fetch(url).then((r) => r.json()).catch(() => ({}));
    toast(data.error || "Could not load the image", true);
    renderReview();
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

  const engine = f.engine || "nlb";
  const dt = ui.state.darktable;
  $$("#engine-seg button").forEach((b) => {
    b.classList.toggle("on", b.dataset.engine === engine);
    if (b.dataset.engine === "darktable" && !dt.available) { b.disabled = engine !== "darktable"; b.title = dt.error; }
  });
  $("#engine-hint").textContent = engine === "darktable"
    ? `Style “${dt.styles?.[ui.state.settings.film] ?? "?"}”, Dmin ` +
      (ui.state.settings.base ? "from the picked film base." : "from the style (pick the film base to set it per roll).") +
      " The sliders and levels apply to nlb only."
    : "";

  const box = $("#param-sliders");
  for (const p of ui.state.params) {
    const el = slider(box, {
      ...p, value: f.params?.[p.key] ?? p.default,
      onInput: (v) => debouncedParam(p.key, v),
      onChange: (v) => debouncedParam(p.key, v, true),
    });
    el.dataset.default = p.default;
    el.querySelector("input").disabled = engine === "darktable";
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
  window.addEventListener("resize", layoutTestBox);

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

async function setEngine(engine) {
  const f = current();
  if (f && (f.engine || "nlb") !== engine) await act(() => patchFrame(f.name, { engine }));
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
  $("#capture-btn").addEventListener("click", () => shoot());
  $$("#shoot-mode button").forEach((b) => b.addEventListener("click", () => act(async () => {
    ui.state = await api("POST", "/api/test/mode", { mode: b.dataset.mode });
    render();
  })));
  $("#keep-btn").addEventListener("click", () => keepTest(false));
  $("#replace-btn").addEventListener("click", () => keepTest(true));
  $("#discard-btn").addEventListener("click", discardTest);
  $$("#live-src button").forEach((b) => b.addEventListener("click", () => setLiveSrc(b.dataset.src)));
  $$("#test-view-seg button").forEach((b) => b.addEventListener("click", () => {
    ui.testView = b.dataset.view;
    save("testView", ui.testView);
    renderCapture();
  }));
  $("#reshoot-btn").addEventListener("click", () => ui.lastCaptured && capture(ui.lastCaptured));
  $("#last-review-btn").addEventListener("click", () => { ui.selected = ui.lastCaptured; setTab("review"); });
  $("#live-invert").addEventListener("change", renderCapture);
  $$("#live-zoom button").forEach((b) => b.addEventListener("click", () => {
    ui.liveZoom = +b.dataset.zoom;
    $$("#live-zoom button").forEach((x) => x.classList.toggle("on", x === b));
    $("#live-img").style.transform = `scale(${ui.liveZoom})`;
    resetFocusPeak();  // a different region: the old peak is not comparable
  }));
  $("#focus-meter").addEventListener("click", resetFocusPeak);
  $("#live-frame").addEventListener("click", (e) => {
    const img = $("#live-img");
    const r = img.getBoundingClientRect();
    if (ui.liveZoom === 1) return;
    // r is the scaled box; convert the click into the unscaled image's percentage
    const ox = ((e.clientX - r.left) / r.width) * 100, oy = ((e.clientY - r.top) / r.height) * 100;
    img.style.transformOrigin = `${clamp(ox, 0, 100)}% ${clamp(oy, 0, 100)}%`;
    resetFocusPeak();
  });

  $("#rot-ccw").addEventListener("click", () => rotate(-90));
  $("#rot-cw").addEventListener("click", () => rotate(90));
  $("#reject-btn").addEventListener("click", toggleReject);
  $$("#engine-seg button").forEach((b) => b.addEventListener("click", () => setEngine(b.dataset.engine)));
  $("#reset-params").addEventListener("click", () => act(async () => {
    const params = Object.fromEntries(ui.state.params.map((p) => [p.key, p.default]));
    await patchFrame(ui.selected, { params, angle: 0 });
  }));
  $("#copy-params").addEventListener("click", () => {
    const f = current();
    if (!f) return;
    ui.clipboard = { rotation: f.rotation, angle: f.angle, params: { ...f.params }, engine: f.engine || "nlb" };
    toast(`Copied ${f.name}'s rotation, adjustments and processing`);
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
    if (ui.tab === "capture") {
      const test = ui.state && ui.state.test;
      if (k === " ") { e.preventDefault(); if (cameraConnected()) shoot(); return; }
      if ((k === "r" || k === "R") && ui.lastCaptured) { if (cameraConnected()) capture(ui.lastCaptured); return; }
      if (test && k === "Enter") { e.preventDefault(); keepTest(false); return; }
      if (test && (k === "Delete" || k === "Backspace")) { e.preventDefault(); discardTest(); return; }
      if (test && (k === "l" || k === "L")) { setLiveSrc(ui.liveSrc === "test" ? "live" : "test"); return; }
      if (k === "f" || k === "F") { resetFocusPeak(); return; }
    }
    if (e.target.type === "range") return;
    if (k === "ArrowLeft") { e.preventDefault(); step(-1); }
    else if (k === "ArrowRight") { e.preventDefault(); step(1); }
    else if (ui.tab !== "review") return;
    else if (k === "x" || k === "X") toggleReject();
    else if ((k === "d" || k === "D") && current()) setEngine(current().engine === "darktable" ? "nlb" : "darktable");
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
