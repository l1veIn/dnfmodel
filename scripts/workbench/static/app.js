"use strict";
// Patch workbench page. All state lives on the server (design/<id>/workbench/issues.jsonl); this page only shows it and sends events.
const $ = id => document.getElementById(id);
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
const STATUS = {"": "未审", pass: "通过", open: "待修", fixed: "待复核", recheck: "需复核"};
const ISSUE = {open: "待修", fixed: "已修，待你复核", verified: "已复核", withdrawn: "已撤回"};
const OPS = {open: "提出", fixed: "已修", reopen: "退回", verify: "复核通过", withdraw: "撤回", note: "备注"};
const S = {projects: [], pid: null, data: null, asset: null, unit: null, k: 0, playing: true, timer: null, images: new Map(), zoom: 1,
           draft: {frames: [], marks: []}};

async function api(path, options) {
  const r = await fetch(path, options);
  const body = await r.json().catch(() => ({error: `HTTP ${r.status}`}));
  if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
  return body;
}

const asset = () => S.data?.assets.find(a => a.id === S.asset);
const unit = () => asset()?.units.find(u => u.id === S.unit);
const frameLabel = (u, value) => (asset().kind === "character" ? `第 ${value + 1} 帧` : `#${value}`);
const unitIssues = () => S.data.issues.filter(i => i.asset === S.asset && i.unit === S.unit);

// ---------------------------------------------------------------- loading

async function loadProjects() {
  S.projects = await api("/api/designs");
  $("project").replaceChildren(...S.projects.map(p => el("option", {value: p.id, textContent: `${p.title}（${p.id}）`})));
  const hash = new URLSearchParams(location.hash.slice(1));
  const wanted = hash.get("p") || (S.projects.find(p => p.events) || S.projects[0]).id;
  $("project").value = wanted;
  await openProject(wanted, hash.get("a"), hash.get("u"));
}

async function openProject(pid, assetId, unitId, refresh = false) {
  S.pid = pid;
  const owner = S.projects.find(p => p.id === pid)?.project;
  $("back").href = owner ? `/#/p/${encodeURIComponent(owner)}` : "/";
  $("back").textContent = owner ? "← 回到项目" : "← 项目总览";
  $("unitTitle").textContent = "读取中…（第一次打开要启动渲染进程，约几秒）";
  $("unitSub").textContent = "";
  try {
    S.data = await api(`/api/p/${encodeURIComponent(pid)}/state` + (refresh ? "?refresh=1" : ""));
  } catch (error) {
    $("unitTitle").textContent = "读取失败";
    $("unitSub").textContent = error.message;
    return;
  }
  if (!S.data.assets.length) {
    $("unitTitle").textContent = "这个项目还没有可审核的内容";
    $("unitSub").textContent = "人物要先跑 final；其他资产写在 design/<id>/workbench/assets.json";
    $("assets").replaceChildren(); $("list").replaceChildren();
    return;
  }
  S.asset = S.data.assets.some(a => a.id === assetId) ? assetId : S.data.assets[0].id;
  renderTabs(); summary();
  const target = asset().units.find(u => u.id === unitId) || firstTodo() || asset().units[0];
  selectUnit(target.id);
}

function summary() {
  const all = S.data.issues;
  const n = s => all.filter(i => i.status === s).length;
  $("summary").textContent = `待修 ${n("open")} · 待复核 ${n("fixed")} · 已复核 ${n("verified")}`;
}

// ---------------------------------------------------------------- unit list

function renderTabs() {
  $("assets").replaceChildren(...S.data.assets.map(a => {
    const open = a.units.filter(u => u.review.status === "open").length;
    const b = el("button", {type: "button", role: "tab", textContent: `${a.label} ${a.units.length}` + (open ? ` · ${open} 待修` : "")});
    b.setAttribute("aria-selected", String(a.id === S.asset));
    b.addEventListener("click", () => { S.asset = a.id; renderTabs(); selectUnit((firstTodo() || asset().units[0]).id); });
    return b;
  }));
}

function visibleUnits() {
  const f = $("filter").value, q = $("search").value.trim().toLowerCase();
  return asset().units.filter(u => {
    const st = u.review.status;
    if (f === "todo" && st) return false;
    if (f !== "all" && f !== "todo" && st !== f) return false;
    return !q || u.label.toLowerCase().includes(q) || (u.group || "").toLowerCase().includes(q);
  });
}

function firstTodo() {
  return asset().units.find(u => !u.review.status) || asset().units.find(u => u.review.status === "fixed");
}

function renderList() {
  const units = asset().units, done = units.filter(u => u.review.status === "pass").length;
  $("progress").textContent = `通过 ${done} / ${units.length}`;
  $("bar").style.width = `${100 * done / Math.max(units.length, 1)}%`;
  const items = [];
  let group = null;
  for (const u of visibleUnits()) {
    if (u.group && u.group !== group) { group = u.group; items.push(el("li", {className: "group", textContent: group})); }
    const st = u.review.status;
    const tag = el("span", {className: `tag ${st}`, textContent: STATUS[st] + (u.review.open + u.review.fixed > 1 ? ` ${u.review.open + u.review.fixed}` : "")});
    const b = el("button", {type: "button", title: u.id}, el("span", {className: "name", textContent: u.label}), tag);
    b.setAttribute("aria-current", String(u.id === S.unit));
    b.addEventListener("click", () => selectUnit(u.id));
    items.push(el("li", {}, b));
  }
  if (!items.length) items.push(el("li", {className: "group", textContent: "没有符合筛选的单元"}));
  $("list").replaceChildren(...items);
  $("list").querySelector('[aria-current="true"]')?.scrollIntoView({block: "nearest"});
}

// ---------------------------------------------------------------- player

// A unit's frames come as one atlas per side (a grid of equal cells); full-screen cut-ins are scaled down in it,
// so a paused cut-in also loads its one frame at full size.
function load(url, onload) {
  if (!S.images.has(url)) {
    const img = new Image();
    img.decoding = "async";
    img.onload = onload;
    img.src = url;
    S.images.set(url, img);
  }
  return S.images.get(url);
}

function weaponFlag() { return asset().kind === "character" && $("weapon").checked ? 1 : 0; }

function sheet(side) {
  const u = unit();
  return load(`/api/p/${encodeURIComponent(S.pid)}/atlas?` + new URLSearchParams({asset: S.asset, unit: u.id, side, weapon: weaponFlag(), v: u.version}),
    () => { if (unit() === u) { draw(); strip(); } });
}

function cell(side, k, atlasOnly = false) {
  const u = unit(), g = u.atlas, img = sheet(side);
  const src = {img, sx: (k % g.cols) * g.cw, sy: Math.floor(k / g.cols) * g.ch, sw: g.cw, sh: g.ch};
  if (u.player === "screen" && !S.playing && !atlasOnly) {
    const full = load(`/api/p/${encodeURIComponent(S.pid)}/frame?` + new URLSearchParams({asset: S.asset, unit: u.id, side, k, weapon: 0, v: u.version}), () => { if (unit() === u) draw(); });
    if (full.complete && full.naturalWidth) return {img: full, sx: 0, sy: 0, sw: full.naturalWidth, sh: full.naturalHeight};
  }
  return src;
}

function selectUnit(id) {
  S.unit = id; S.k = 0; S.draft = {frames: [], marks: []};
  const u = unit(), a = asset();
  history.replaceState(null, "", `#${new URLSearchParams({p: S.pid, a: S.asset, u: id})}`);
  $("unitTitle").textContent = (u.group ? `${u.group} · ` : "") + u.label;
  $("unitSub").textContent = `${u.frames.length} 帧` + (a.kind === "character" ? `，第 ${u.frames[0] + 1}–${u.frames[u.frames.length - 1] + 1} 帧` : `，${u.id}`) + (u.npk ? `，官方包 ${u.npk}` : a.kind === "img" ? "，没找到官方原图" : "");
  $("weaponField").hidden = !(a.kind === "character" && a.weapon);
  $("weaponLabel").textContent = a.weapon ? `带${a.weapon}（武器总画在最上面，遮挡顺序不对）` : "";
  $("fps").value = u.player === "screen" ? 8 : 10;
  $("fpsText").textContent = fpsText();
  sheet("native"); sheet("new");
  layout(); strip(); renderList(); renderReview(); draw(); info(); setPlaying(true);
}

function fpsText() {
  const fps = Number($("fps").value), screen = unit()?.player === "screen";
  return `${fps} 帧/秒（${Math.round(1000 / fps)}ms）${screen || asset()?.kind === "img" ? "，游戏节奏读不到，是估计值" : ""}`;
}

function layout() {
  const u = unit(), [x0, y0, x1, y1] = u.box, w = x1 - x0, h = y1 - y0, view = $("view").value;
  const labels = view === "overlay" ? ["原版（实色）叠新版（半透明）"] : view === "new" ? ["新版"] : ["原版", "新版"];
  const room = Math.max(200, $("stage").clientWidth || 600), tall = Math.max(200, window.innerHeight - 330);
  const fit = Math.min((room - 12 * (labels.length - 1)) / labels.length / w, tall / h);
  S.zoom = fit >= 1 ? Math.min(8, Math.floor(fit)) : fit;
  $("stage").replaceChildren(...labels.map((label, n) => {
    const c = el("canvas", {width: Math.round(w * S.zoom), height: Math.round(h * S.zoom)});
    if (n === labels.length - 1 || view === "overlay") { c.className = "new"; c.addEventListener("click", markAt); c.title = "点一下落标记"; }
    return el("figure", {}, el("figcaption", {textContent: label}), c);
  }));
}

function paint(canvas, layers) {
  const g = canvas.getContext("2d");
  g.imageSmoothingEnabled = S.zoom < 1;
  g.globalAlpha = 1;
  g.fillStyle = $("backdrop").value;
  g.fillRect(0, 0, canvas.width, canvas.height);
  for (const [c, alpha] of layers) {
    if (c.img.complete && c.img.naturalWidth) { g.globalAlpha = alpha; g.drawImage(c.img, c.sx, c.sy, c.sw, c.sh, 0, 0, canvas.width, canvas.height); }
  }
  g.globalAlpha = 1;
}

function ring(canvas, m, color, dashed) {
  const [x0, y0] = unit().box, g = canvas.getContext("2d");
  g.save();
  g.strokeStyle = color; g.lineWidth = 2; g.setLineDash(dashed ? [5, 3] : []);
  g.beginPath(); g.arc((m.x - x0 + 0.5) * S.zoom, (m.y - y0 + 0.5) * S.zoom, Math.max(6, m.r * S.zoom), 0, Math.PI * 2); g.stroke();
  g.restore();
}

function draw() {
  if (!unit()) return;
  const k = S.k, value = unit().frames[k], view = $("view").value, canvases = [...$("stage").querySelectorAll("canvas")];
  if (view === "overlay") paint(canvases[0], [[cell("native", k), 1], [cell("new", k), 0.6]]);
  else if (view === "new") paint(canvases[0], [[cell("new", k), 1]]);
  else { paint(canvases[0], [[cell("native", k), 1]]); paint(canvases[1], [[cell("new", k), 1]]); }
  const target = canvases[canvases.length - 1];
  for (const i of unitIssues()) {
    if (i.status !== "open" && i.status !== "fixed") continue;
    for (const m of i.marks) if (m.frame === value) ring(target, m, i.status === "open" ? "#ff8a7a" : "#f2c46d", false);
  }
  for (const m of S.draft.marks) if (m.frame === value) ring(target, m, "#7fb0ff", true);
}

function markAt(event) {
  const c = event.currentTarget, rect = c.getBoundingClientRect(), [x0, y0] = unit().box;
  const x = Math.round(x0 + (event.clientX - rect.left) / rect.width * c.width / S.zoom);
  const y = Math.round(y0 + (event.clientY - rect.top) / rect.height * c.height / S.zoom);
  const value = unit().frames[S.k];
  setPlaying(false);
  const near = S.draft.marks.findIndex(m => m.frame === value && Math.hypot(m.x - x, m.y - y) <= Math.max(m.r, 6 / S.zoom));
  if (near >= 0) S.draft.marks.splice(near, 1);
  else {
    S.draft.marks.push({frame: value, x, y, r: Math.max(4, Math.round(10 / Math.max(S.zoom, 0.25)))});
    if (!S.draft.frames.includes(value)) S.draft.frames.push(value);
  }
  renderDraft(); draw(); markStrip();
}

function strip() {
  const u = unit(), [x0, y0, x1, y1] = u.box;
  const tall = 64, wide = Math.max(8, Math.round((x1 - x0) * tall / (y1 - y0)));
  $("strip").replaceChildren(...u.frames.map((value, k) => {
    const c = el("canvas", {width: wide, height: tall});
    const b = el("button", {type: "button", title: frameLabel(u, value)}, c, el("span", {textContent: asset().kind === "character" ? value + 1 : value}));
    b.addEventListener("click", () => { setPlaying(false); go(k); });
    const src = cell("new", k, true), g = c.getContext("2d");
    g.fillStyle = $("backdrop").value; g.fillRect(0, 0, wide, tall);
    if (src.img.complete && src.img.naturalWidth) g.drawImage(src.img, src.sx, src.sy, src.sw, src.sh, 0, 0, wide, tall);
    return b;
  }));
  markStrip();
}

function markStrip() {
  const u = unit(), flagged = new Set(unitIssues().filter(i => i.status === "open" || i.status === "fixed").flatMap(i => [...i.frames, ...i.marks.map(m => m.frame)]));
  [...$("strip").children].forEach((b, k) => {
    b.setAttribute("aria-current", String(k === S.k));
    b.classList.toggle("draft", S.draft.frames.includes(u.frames[k]));
    b.classList.toggle("issue", flagged.has(u.frames[k]));
    if (k === S.k && !S.playing) b.scrollIntoView({block: "nearest", inline: "nearest"});
  });
}

function info() {
  const u = unit(), value = u.frames[S.k], meta = u.meta[S.k] || {}, parts = [frameLabel(u, value)];
  if (asset().kind === "character") parts.push(`工具编号 ${value}`);
  if (meta.ratio != null) parts.push(`身高比 ${meta.ratio.toFixed(2)}`);
  if (meta.hand) parts.push(`手：${meta.hand}${meta.gap != null ? `，移动 ${meta.gap}px` : ""}`);
  if (meta.source) parts.push(`来源 ${meta.source}`);
  $("info").textContent = parts.join(" · ");
}

function go(k) {
  const n = unit().frames.length;
  S.k = (k + n) % n;
  draw(); markStrip(); info();
}

function setPlaying(on) {
  S.playing = on; clearTimeout(S.timer);
  $("play").textContent = on ? "暂停" : "播放";
  if (on) tick();
  markStrip();
}

function tick() {
  S.timer = setTimeout(() => { if (!S.playing) return; go(S.k + 1); tick(); }, 1000 / Number($("fps").value));
}

// ---------------------------------------------------------------- review

async function send(event) {
  $("saved").textContent = "保存中…";
  try {
    const r = await api(`/api/p/${encodeURIComponent(S.pid)}/event`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(event)});
    S.data = r.state;
    $("saved").textContent = `已保存 ${r.event.t.slice(11)}`;
    renderTabs(); renderList(); renderReview(); summary(); draw(); markStrip();
    return r.event;
  } catch (error) {
    $("saved").textContent = `没保存上：${error.message}`;
    throw error;
  }
}

function renderReview() {
  const u = unit(), r = u.review;
  $("pass").setAttribute("aria-pressed", String(r.status === "pass" || r.status === "recheck"));
  const verdict = S.data.units[`${S.asset}/${u.id}`];
  $("verdictText").textContent = r.status === "recheck" ? `通过于 ${verdict.t}，之后帧又改过，需要再看一遍` : verdict?.verdict === "pass" ? `通过于 ${verdict.t}` : r.open ? `还有 ${r.open} 个待修的问题` : "";
  renderDraft();
  renderIssues();
}

function renderDraft() {
  const u = unit();
  $("draftFrames").replaceChildren(...S.draft.frames.sort((a, b) => a - b).map(value => {
    const b = el("button", {type: "button", textContent: `${frameLabel(u, value)} ×`, title: "去掉这一帧"});
    b.addEventListener("click", () => { S.draft.frames = S.draft.frames.filter(f => f !== value); S.draft.marks = S.draft.marks.filter(m => m.frame !== value); renderDraft(); draw(); markStrip(); });
    return b;
  }));
  $("draftMarks").replaceChildren(...S.draft.marks.map((m, n) => {
    const b = el("button", {type: "button", textContent: `标记 ${n + 1}：${frameLabel(u, m.frame)} (${m.x},${m.y}) ×`});
    b.addEventListener("click", () => { S.draft.marks.splice(n, 1); renderDraft(); draw(); });
    return b;
  }));
}

function jump(i) {
  if (i.asset !== S.asset || i.unit !== S.unit) { S.asset = i.asset; renderTabs(); selectUnit(i.unit); }
  const target = i.marks[0]?.frame ?? i.frames[0];
  const k = unit().frames.indexOf(target);
  if (k >= 0) { setPlaying(false); go(k); }
}

function issueCard(i, withPlace) {
  const u = S.data.assets.find(a => a.id === i.asset)?.units.find(x => x.id === i.unit);
  const label = v => (i.asset === "character" ? `第 ${v + 1} 帧` : `#${v}`);
  const head = el("div", {className: "head"}, el("b", {textContent: `#${i.issue}`}), el("span", {className: "st", textContent: ISSUE[i.status]}));
  if (withPlace) {
    const where = el("button", {type: "button", className: "where", textContent: `${S.data.assets.find(a => a.id === i.asset)?.label || i.asset} · ${u?.group ? u.group + " · " : ""}${u?.label || i.unit}`});
    where.addEventListener("click", () => { $("overlay").hidden = true; jump(i); });
    head.append(where);
  }
  const frames = [...new Set([...i.frames, ...i.marks.map(m => m.frame)])].sort((a, b) => a - b);
  if (frames.length) {
    const f = el("button", {type: "button", className: "where", textContent: frames.map(label).join("、")});
    f.addEventListener("click", () => { $("overlay").hidden = true; jump(i); });
    head.append(f);
  }
  const li = el("li", {className: `issue ${i.status}`}, head, el("div", {className: "note", textContent: i.note || "（没有文字）"}));
  for (const h of i.history.slice(1)) {
    li.append(el("div", {className: "hist"}, el("b", {textContent: `${h.by === "claude" ? "Claude" : "你"} ${OPS[h.op] || h.op}`}), ` ${h.t.slice(5, 16)}${h.note ? "：" + h.note : ""}`));
  }
  if (!withPlace) {
    const reply = el("textarea", {placeholder: "补充说明（退回时写原因）"});
    const row = el("div", {className: "row"});
    const add = (text, op, primary) => {
      const b = el("button", {type: "button", textContent: text, className: primary ? "primary" : ""});
      b.addEventListener("click", () => send({op, issue: i.issue, note: reply.value.trim()}));
      row.append(b);
    };
    if (i.status === "fixed") { add("复核通过", "verify", true); add("退回", "reopen"); }
    if (i.status === "verified") add("退回", "reopen");
    if (i.status === "open") add("撤回", "withdraw");
    add("只加备注", "note");
    li.append(reply, row);
  }
  return li;
}

function renderIssues() {
  const list = unitIssues().sort((a, b) => (a.status === "open" || a.status === "fixed" ? 0 : 1) - (b.status === "open" || b.status === "fixed" ? 0 : 1) || b.issue - a.issue);
  $("issuesTitle").textContent = `问题（${list.length}）`;
  $("issues").replaceChildren(...(list.length ? list.map(i => issueCard(i, false)) : [el("li", {className: "muted small", textContent: "这个单元没有问题记录"})]));
}

function toggleDraftFrame() {
  const value = unit().frames[S.k];
  setPlaying(false);
  if (S.draft.frames.includes(value)) { S.draft.frames = S.draft.frames.filter(f => f !== value); S.draft.marks = S.draft.marks.filter(m => m.frame !== value); }
  else S.draft.frames.push(value);
  renderDraft(); draw(); markStrip();
}

async function submitDraft() {
  const note = $("draftNote").value.trim();
  if (!note && !S.draft.frames.length) { $("saved").textContent = "写一句哪里不对，或者先选帧、点标记"; return; }
  await send({op: "open", asset: S.asset, unit: S.unit, frames: S.draft.frames, marks: S.draft.marks, note});
  S.draft = {frames: [], marks: []}; $("draftNote").value = "";
  renderDraft(); draw(); markStrip();
}

function renderOverlay() {
  const active = $("overlayFilter").value === "active";
  const list = S.data.issues.filter(i => !active || i.status === "open" || i.status === "fixed").sort((a, b) => b.issue - a.issue);
  $("overlayList").replaceChildren(...(list.length ? list.map(i => issueCard(i, true)) : [el("li", {className: "muted", textContent: "没有问题"})]));
}

// ---------------------------------------------------------------- wiring

$("project").addEventListener("change", () => openProject($("project").value));
$("reload").addEventListener("click", () => { S.images.clear(); openProject(S.pid, S.asset, S.unit, true); });
$("filter").addEventListener("change", renderList);
$("search").addEventListener("input", renderList);
$("play").addEventListener("click", () => setPlaying(!S.playing));
$("prev").addEventListener("click", () => { setPlaying(false); go(S.k - 1); });
$("next").addEventListener("click", () => { setPlaying(false); go(S.k + 1); });
$("fps").addEventListener("input", () => { $("fpsText").textContent = fpsText(); setPlaying(S.playing); });
$("view").addEventListener("change", () => { layout(); draw(); });
$("backdrop").addEventListener("change", () => { strip(); draw(); });
$("weapon").addEventListener("change", () => { sheet("native"); sheet("new"); strip(); draw(); });
$("pass").addEventListener("click", () => send({op: "pass", asset: S.asset, unit: S.unit}).then(() => { const next = firstTodo(); if (next && next.id !== S.unit) selectUnit(next.id); }));
$("clear").addEventListener("click", () => send({op: "clear", asset: S.asset, unit: S.unit}));
$("submit").addEventListener("click", submitDraft);
$("discard").addEventListener("click", () => { S.draft = {frames: [], marks: []}; $("draftNote").value = ""; renderDraft(); draw(); markStrip(); });
$("allIssues").addEventListener("click", () => { renderOverlay(); $("overlay").hidden = false; });
$("overlayClose").addEventListener("click", () => { $("overlay").hidden = true; });
$("overlayFilter").addEventListener("change", renderOverlay);
$("overlay").addEventListener("click", e => { if (e.target === $("overlay")) $("overlay").hidden = true; });
window.addEventListener("resize", () => { if (unit()) { layout(); draw(); } });
document.addEventListener("keydown", event => {
  if (!unit() || event.target.matches("textarea, input, select") || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.key === "Escape") { $("overlay").hidden = true; return; }
  const list = visibleUnits(), at = list.findIndex(u => u.id === S.unit);
  const keys = {
    " ": () => setPlaying(!S.playing),
    ArrowLeft: () => { setPlaying(false); go(S.k - 1); },
    ArrowRight: () => { setPlaying(false); go(S.k + 1); },
    ArrowUp: () => list.length && selectUnit(list[(at - 1 + list.length) % list.length].id),
    ArrowDown: () => list.length && selectUnit(list[(at + 1) % list.length].id),
    1: () => $("pass").click(),
    f: toggleDraftFrame, F: toggleDraftFrame,
  };
  if (keys[event.key]) { event.preventDefault(); keys[event.key](); }
});

loadProjects().catch(error => { $("unitTitle").textContent = "读取失败"; $("unitSub").textContent = error.message; });
