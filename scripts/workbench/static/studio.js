"use strict";
// A saved outfit contains its non-destructive customization and a manually aligned effect scene.
// Only the customization is baked into clothing exports; skill effects belong to the preview.
const SLOTS = [["skin", "皮肤"], ["hair", "头部"], ["cap", "帽子"], ["face", "脸部"], ["neck", "胸部"], ["coat", "上衣"], ["belt", "腰带"], ["pants", "下装"], ["shoes", "鞋子"], ["weapon", "武器"]];
const WEAPON_CN = {revolver: "左轮", automatic: "自动手枪", hcannon: "手炮", musket: "步枪", bowgun: "手弩", weapon: "其他"};
const T = {roles: [], role: null, info: null, outfit: {}, names: {}, overlay: "", plan: null, k: 0, start: 0, end: 0,
  playing: true, timer: null, pick: "coat", weaponKind: "", tab: "items", query: "", wardrobe: [], current: {}, exports: [],
  customization: {}, scene: {effects: []}, effectMeta: new Map(), effectImages: new Map(), skills: [], skillItems: [], effectPick: -1,
  characterImage: null, fullFrame: null, frameRequest: 0, pendingPixels: [], undo: [], redo: [], stroke: null, hover: null,
  sceneTick: 0, sampleRequest: 0, busy: false, page: 0, roleRequest: 0, composeRequest: 0,
  pickerRequest: 0, skillRequest: 0, dyeTimer: null, searchTimer: null, zoomChoice: "auto", viewBox: null};
const stCopy = value => JSON.parse(JSON.stringify(value));
const stPost = (url, payload) => api(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
const stHere = () => /^#\/studio(?:$|[/?])/.test(location.hash) && !!$("stCanvas");
const stPayload = () => ({role: T.role, outfit: stCopy(T.outfit), overlay: T.overlay, customization: stCopy(T.customization)});

function stStatus(message, error = false) {
  if ($("stStatus")) { $("stStatus").textContent = message; $("stStatus").classList.toggle("bad", error); }
}
async function stTask(fn) {
  try { return await fn(); }
  catch (error) { if (stHere()) { stStatus(error.message, true); toast(error.message); } }
}
const stButton = (label, fn, props = {}) => {
  const b = el("button", {type: "button", textContent: label, ...props});
  b.addEventListener("click", () => stTask(fn)); return b;
};
const stOn = (id, event, fn) => $(id).addEventListener(event, e => stTask(() => fn(e)));
const stField = (text, control) => el("label", {className: "field"}, text, control);
const stSelect = (id, choices) => el("select", {id}, ...choices.map(([value, textContent]) => el("option", {value, textContent})));

function stCleanup() {
  clearTimeout(T.timer); clearTimeout(T.dyeTimer); clearTimeout(T.searchTimer);
  T.page++; T.roleRequest++; T.composeRequest++; T.pickerRequest++; T.skillRequest++; T.frameRequest++; T.sampleRequest++;
  T.busy = false; T.stroke = null; T.hover = null; T.pendingPixels = []; T.fullFrame = null;
}

async function studioPage() {
  stCleanup(); const page = T.page;
  $("crumb").textContent = "/ 试衣间"; document.title = "试衣间 · 补丁工作台";
  const [roles, wardrobe, exports] = await Promise.all([
    T.roles.length ? Promise.resolve(T.roles) : api("/api/studio/roles"), api("/api/studio/wardrobe"), api("/api/studio/exports")]);
  if (page !== T.page || !/^#\/studio/.test(location.hash)) return;
  T.roles = roles; T.wardrobe = wardrobe.outfits; T.current = wardrobe.current || {}; T.exports = exports;
  $("page").className = "page wide";
  const roleSel = stSelect("stRole", T.roles.map(r => [r.role, `${r.label}（${r.frames || "?"} 帧）`]));
  $("page").replaceChildren(el("div", {className: "studio"},
    el("aside", {className: "stLeft"},
      el("div", {className: "row"}, roleSel, el("select", {id: "stOverlay", ariaLabel: "叠加补丁"})),
      el("ul", {id: "stSlots"}),
      el("div", {className: "stCurrent"}, el("div", {id: "stCurrentText", className: "small"}),
        el("div", {className: "row"}, stButton("把这套设为当前穿戴", setCurrent), stButton("穿上当前穿戴", wearCurrent))),
      el("div", {className: "stPicker"},
        el("div", {className: "row"}, el("b", {id: "stPickTitle"}), el("span", {className: "spacer"}),
          el("button", {type: "button", id: "stTabItems", textContent: "单件"}), el("button", {type: "button", id: "stTabSets", textContent: "套装"})),
        el("div", {className: "row"}, el("select", {id: "stWeaponKind", hidden: true}), el("input", {type: "search", id: "stQuery", placeholder: "搜名字、物品 ID 或代码"})),
        el("ul", {id: "stResults"}))),
    el("section", {className: "stMain"},
      el("div", {className: "row"}, el("h2", {textContent: "试衣间"}), el("span", {id: "stSub", className: "muted small"})),
      el("div", {className: "controls"},
        stButton("暂停", () => stPlay(!T.playing), {id: "stPlay"}),
        stButton("上一帧", () => { stPlay(false); stStep(-1); }), stButton("下一帧", () => { stPlay(false); stStep(1); }),
        stField("动作", el("select", {id: "stAction"})),
        stField("帧", el("input", {type: "number", id: "stStart", min: 0, className: "stNumber"})), "–",
        el("input", {type: "number", id: "stEnd", min: 0, className: "stNumber", ariaLabel: "结束帧（工具编号）"}),
        stField("帧/秒", el("input", {type: "number", id: "stFps", min: 1, max: 60, value: 10, className: "stNumber"})),
        stField("缩放", stSelect("stZoom", [["auto", "自动"], ["1", "1×"], ["2", "2×"], ["4", "4×"], ["6", "6×"], ["8", "8×"], ["12", "12×"]])),
        stField("背景", stSelect("stBack", [["#56617a", "灰蓝"], ["#22282a", "深色"], ["#c2c0ac", "浅色"]]))),
      stPixelTools(),
      el("div", {id: "stStage"}, el("canvas", {id: "stCanvas", width: 10, height: 10, tabIndex: 0, ariaLabel: "人物与技能组合预览"})),
      el("div", {id: "stInfo", className: "small muted"}),
      el("div", {id: "stStatus", className: "small stStatus", role: "status", ariaLive: "polite"}),
      stSceneTools()),
    el("aside", {className: "stRight"},
      stDyeTools(),
      el("section", {className: "card"}, el("h3", {textContent: "衣橱"}),
        el("div", {className: "row"}, el("input", {type: "text", id: "stSaveName", maxLength: 60, placeholder: "给这套起个名字"}), stButton("保存", saveOutfit)),
        el("p", {className: "small muted", textContent: "保存穿搭、调色、像素修改和技能组合。"}), el("ul", {id: "stWardrobe", className: "plain"})),
      el("section", {className: "card"}, el("h3", {textContent: "按当前穿戴导出补丁"}),
        el("p", {className: "small muted", textContent: "将目标衣装及调色、像素修改写进当前穿戴的 IMG；其余时装和身体置空。武器保持原样，技能组合仅供预览。导出后逐帧回读核对，不会安装。"}),
        el("div", {id: "stExportPlan", className: "small"}),
        el("div", {className: "row"}, el("input", {type: "text", id: "stExportName", placeholder: "补丁名字"}), stButton("导出", exportOutfit, {id: "stExport"})),
        el("ul", {id: "stExports", className: "plain small"})),
      el("details", {className: "card"}, el("summary", {textContent: "图层（从后到前）"}), el("ol", {id: "stLayers", className: "plain small"})))));
  stOn("stRole", "change", () => setRole($("stRole").value, null, {}, {effects: []}));
  stOn("stTabItems", "click", () => { T.tab = "items"; return renderPicker(); });
  stOn("stTabSets", "click", () => { T.tab = "sets"; return renderPicker(); });
  stOn("stQuery", "input", () => { clearTimeout(T.searchTimer); T.searchTimer = setTimeout(() => stTask(() => { T.query = $("stQuery").value.trim(); return renderPicker(); }), 250); });
  stOn("stWeaponKind", "change", () => { T.weaponKind = $("stWeaponKind").value; return renderPicker(); });
  stOn("stOverlay", "change", () => { T.overlay = $("stOverlay").value; return refresh(); });
  stOn("stAction", "change", () => { const [a, b] = $("stAction").value.split(":").map(Number); setRange(a, b); });
  for (const id of ["stStart", "stEnd"]) stOn(id, "change", () => setRange(Number($("stStart").value), Number($("stEnd").value)));
  stOn("stFps", "change", () => { $("stFps").value = Math.max(1, Math.min(60, Number($("stFps").value) || 10)); stRememberPlayback(); stPlay(T.playing); stDraw(); });
  stOn("stZoom", "change", () => { T.zoomChoice = $("stZoom").value; stLayout(); });
  stOn("stBack", "change", stDraw);
  stBindPixelTools(); stBindDyeTools(); stBindSceneTools(); renderWardrobe();
  $("stZoom").value = T.zoomChoice;
  await setRole(T.role || "gunner_at", T.role ? T.outfit : null, T.customization, T.scene);
}

async function setRole(role, outfit, customization = {}, scene = {effects: []}) {
  const request = ++T.roleRequest; ++T.composeRequest; ++T.pickerRequest; ++T.skillRequest;
  clearTimeout(T.dyeTimer); ++T.sampleRequest; stCancelStroke(); stPlay(false); T.busy = false;
  stStatus("读取职业…");
  const info = await api(`/api/studio/role?${new URLSearchParams({role})}`);
  if (request !== T.roleRequest || !stHere()) return;
  T.role = role; T.info = info; $("stRole").value = role;
  T.outfit = stCopy(outfit || info.default); T.customization = stCopy(customization || {});
  T.scene = stCopy(scene || {effects: []}); T.scene.effects ||= [];
  T.undo = []; T.redo = []; T.pendingPixels = []; T.hover = null; T.plan = null; T.characterImage = null; T.fullFrame = null; T.skills = []; T.skillItems = []; T.effectPick = -1;
  T.weaponKind = info.role.weapons.find(w => w !== "weapon") || info.role.weapons[0] || "";
  $("stOverlay").replaceChildren(...info.overlays.map(o => el("option", {value: o.id, textContent: o.label})));
  T.overlay = info.overlays.some(o => o.id === T.overlay) ? T.overlay : ""; $("stOverlay").value = T.overlay;
  $("stWeaponKind").replaceChildren(...info.role.weapons.map(w => el("option", {value: w, textContent: WEAPON_CN[w] || w})));
  $("stWeaponKind").value = T.weaponKind;
  const n = info.role.frames || 1, first = info.actions[0];
  $("stAction").replaceChildren(el("option", {value: `0:${n - 1}`, textContent: `全部 ${n} 帧`}), ...info.actions.map(a => el("option", {value: `${a.start}:${a.end}`, textContent: `${a.name}（${a.start + 1}–${a.end + 1}）`})));
  const playback = stPlayback(T.scene, n, first);
  $("stFps").value = playback.fps;
  setRange(playback.start, playback.end, true);
  $("stAction").value = `${T.start}:${T.end}`;
  renderDye(); renderEffects(); renderCurrent(); renderExports();
  await Promise.all([refresh(), stTask(renderPicker), stTask(() => stLoadSkills(request)), stTask(() => stRestoreEffects(request))]);
  if (request === T.roleRequest && stHere()) stPlay(true);
}

function setRange(a, b, quiet) {
  if (T.stroke) {
    $("stStart").value = T.start; $("stEnd").value = T.end; $("stAction").value = `${T.start}:${T.end}`;
    toast("请先结束或取消当前笔画，再切换动作。"); return;
  }
  ++T.sampleRequest;
  const n = T.info?.role.frames || 1;
  T.start = Math.max(0, Math.min(n - 1, Math.trunc(a) || 0)); T.end = Math.max(T.start, Math.min(n - 1, Number.isFinite(b) ? Math.trunc(b) : n - 1));
  $("stStart").value = T.start; $("stEnd").value = T.end; T.k = T.start; T.sceneTick = 0;
  stRememberPlayback();
  if (!quiet) { stDraw(); stPlay(T.playing); }
}

function stPlayback(scene, frames, first) {
  const saved = scene?.playback, fallback = first || {start: 0, end: frames - 1};
  const start = Math.max(0, Math.min(frames - 1, Math.trunc(saved?.start ?? fallback.start) || 0));
  return {start, end: Math.max(start, Math.min(frames - 1, Math.trunc(saved?.end ?? fallback.end) || 0)),
    fps: Math.max(1, Math.min(60, Number(saved?.fps) || 10))};
}
function stRememberPlayback() {
  T.scene.playback = {start: T.start, end: T.end, fps: stCharacterFps()};
}
const stCharacterFps = () => Math.max(1, Math.min(60, Number($("stFps")?.value) || 10));

async function stImageBlob(response) {
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.error || `HTTP ${response.status}`); }
  const url = URL.createObjectURL(await response.blob());
  try { const img = new Image(); img.src = url; await img.decode(); return img; }
  finally { URL.revokeObjectURL(url); }
}

async function refresh() {
  if (!T.info || !stHere()) return;
  stCancelStroke(); ++T.sampleRequest;
  const request = ++T.composeRequest, roleRequest = T.roleRequest, payload = stPayload();
  T.busy = true; stStatus("正在合成，修改会保留在这套搭配中…");
  try {
    const plan = await stPost("/api/studio/compose", payload);
    if (request !== T.composeRequest || roleRequest !== T.roleRequest || !stHere()) return;
    const image = await stImageBlob(await fetch("/api/studio/atlas", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)}));
    if (request !== T.composeRequest || roleRequest !== T.roleRequest || !stHere()) return;
    T.plan = plan; T.characterImage = image; T.pendingPixels = []; T.fullFrame = null;
    for (const l of plan.layers) if (l.item_id) T.names[l.item_id] = l.name;
    renderSlots(); renderLayers(); renderDye(); stLayout(); renderCurrent(); stPixelCount();
    const patched = plan.layers.filter(l => l.patched).length;
    $("stSub").textContent = `${T.info.role.label} · ${plan.layers.length} 个图层` + (T.overlay ? `，${patched} 个来自补丁` : "") + (plan.hidden.length ? `，被隐藏：${plan.hidden.join("、")}` : "") + (plan.missing.length ? `，${plan.missing.length} 个 IMG 在本地找不到` : "");
    stStatus("已更新。保存到衣橱可保留本次修改。");
    if (!T.playing) stTask(stLoadFullFrame);
  } catch (error) {
    if (request === T.composeRequest && stHere()) { stStatus(`合成失败：${error.message}；修改仍在，可点“重试合成”。`, true); toast(`合成失败：${error.message}`); }
  } finally { if (request === T.composeRequest) T.busy = false; }
}

function stEffectKey(effect) {
  const stamp = T.effectMeta.get(effect.path)?.mods?.find(m => m.project === effect.source)?.stamp || "o";
  return `${effect.source}|${effect.path}|${stamp}`;
}
function stSceneBox() {
  const box = T.plan.box.slice();
  if ($("stPixelMode")?.value && $("stPixelMode").value !== "view") return box;
  for (const effect of T.scene.effects) {
    if (effect.enabled === false) continue;
    const meta = T.effectMeta.get(effect.path); if (!meta) continue;
    const b = meta.box, s = effect.scale;
    box[0] = Math.min(box[0], Math.floor(b[0] * s + effect.x)); box[1] = Math.min(box[1], Math.floor(b[1] * s + effect.y));
    box[2] = Math.max(box[2], Math.ceil(b[2] * s + effect.x)); box[3] = Math.max(box[3], Math.ceil(b[3] * s + effect.y));
  }
  return box;
}

function stLayout() {
  if (!T.plan || !stHere()) return;
  T.sceneTick = Math.min(T.sceneTick, stSceneLength() - 1); T.k = stTimelineFrame(T.sceneTick);
  const box = stSceneBox(), w = box[2] - box[0], h = box[3] - box[1]; T.viewBox = box;
  const room = Math.max(200, $("stStage").clientWidth - 8), tall = Math.max(260, Math.min(650, window.innerHeight - 300));
  const fit = Math.min(room / w, tall / h);
  T.zoom = T.zoomChoice === "auto" ? (fit >= 1 ? Math.min(6, Math.floor(fit)) : fit) : Number(T.zoomChoice);
  // The stage scrolls at fixed zoom; cap backing buffers for very large skill canvases.
  T.zoom = Math.min(T.zoom, 8192 / w, 8192 / h, Math.sqrt(16000000 / (w * h)));
  const c = $("stCanvas"); c.width = Math.max(1, Math.round(w * T.zoom)); c.height = Math.max(1, Math.round(h * T.zoom));
  stDraw();
}

function stEffectFrame(effect, frame, actionStart, characterFps, frames) {
  if (effect.enabled === false) return null;
  const elapsed = frame - actionStart - effect.start;
  if (elapsed < 0 || frames < 1) return null;
  const k = Math.floor(elapsed * effect.fps / characterFps);
  return effect.loop ? k % frames : k < frames ? k : null;
}

function stSceneLength(capped = true) {
  const fps = stCharacterFps();
  let length = T.end - T.start + 1;
  for (const effect of T.scene.effects) {
    if (effect.enabled === false) continue;
    const frames = T.effectMeta.get(effect.path)?.frames || 0;
    length = Math.max(length, effect.start + Math.ceil(frames * fps / effect.fps));
  }
  return Math.max(1, capped ? Math.min(Math.ceil(fps * 600), length) : length);
}
function stTimelineFrame(tick, start = T.start, end = T.end) {
  const span = Math.max(1, end - start + 1);
  return start + ((tick % span) + span) % span;
}
function stSeekTimeline(tick, wrap = false) {
  if (T.stroke) return;
  const length = stSceneLength();
  T.sceneTick = wrap ? ((Math.trunc(tick) % length) + length) % length : Math.max(0, Math.min(length - 1, Math.trunc(tick) || 0));
  T.k = stTimelineFrame(T.sceneTick); ++T.sampleRequest; stDraw();
  if (!T.playing) stTask(stLoadFullFrame);
}
function stStep(delta) {
  if ($("stPixelMode")?.value === "view" && T.scene.effects.some(e => e.enabled !== false)) stSeekTimeline(T.sceneTick + delta, true);
  else stGo(T.k + delta);
}
function stTimelineStatus() {
  if (!$("stSceneTime")) return;
  const fps = stCharacterFps(), length = stSceneLength();
  $("stSceneTime").max = length - 1; $("stSceneTime").value = T.sceneTick;
  const limited = stSceneLength(false) > length;
  $("stSceneClock").textContent = `${(T.sceneTick / fps).toFixed(2)} / ${(length / fps).toFixed(2)} 秒 · 组合节拍 ${T.sceneTick}` +
    (limited ? " · 已达 10 分钟预览上限，超出部分无法显示，请减少技能延后或时长。" : "");
  const e = T.scene.effects[T.effectPick], meta = e && T.effectMeta.get(e.path);
  if ($("stEffectState")) {
    const frame = meta && stEffectFrame(e, T.sceneTick, 0, fps, meta.frames);
    $("stEffectState").textContent = !e ? "选择图层可查看当前播放状态。" : e.enabled === false ? "当前图层已隐藏" : !meta ? "当前图层正在读取" :
      e.start >= length ? "当前图层出场时间超出 10 分钟预览上限，请减少延后。" :
      T.sceneTick < e.start ? `当前图层待出场 · ${(Math.max(0, e.start - T.sceneTick) / fps).toFixed(2)} 秒后` : frame === null ? "当前图层已结束" : `当前图层第 ${frame + 1} / ${meta.frames} 帧`;
  }
}

function stDrawEffect(ctx, effect, front, sx, sy) {
  if ($("stPixelMode").value !== "view") return;
  if (effect.front !== front || effect.enabled === false) return;
  const meta = T.effectMeta.get(effect.path), img = T.effectImages.get(stEffectKey(effect));
  if (!meta || !img?.naturalWidth) return;
  const k = stEffectFrame(effect, T.sceneTick, 0, stCharacterFps(), meta.frames);
  if (k === null) return;
  const [x0, y0, x1, y1] = meta.box, g = meta.atlas;
  ctx.save();
  try {
    ctx.globalAlpha = effect.opacity;
    ctx.globalCompositeOperation = effect.blend === "add" ? "lighter" : "source-over";
    ctx.drawImage(img, (k % g.cols) * g.cw, Math.floor(k / g.cols) * g.ch, g.cw, g.ch,
      (x0 * effect.scale + effect.x - T.viewBox[0]) * sx, (y0 * effect.scale + effect.y - T.viewBox[1]) * sy,
      (x1 - x0) * effect.scale * sx, (y1 - y0) * effect.scale * sy);
  } finally { ctx.restore(); }
}

function stCharacterCanvas() {
  if (!T.plan || !T.characterImage) return null;
  const [x0, y0, x1, y1] = T.plan.box, g = T.plan.atlas;
  const c = document.createElement("canvas"); c.width = x1 - x0; c.height = y1 - y0;
  const ctx = c.getContext("2d"); ctx.imageSmoothingEnabled = false;
  if (T.fullFrame?.key === T.plan.key && T.fullFrame.k === T.k) ctx.drawImage(T.fullFrame.image, 0, 0);
  else ctx.drawImage(T.characterImage, (T.k % g.cols) * g.cw, Math.floor(T.k / g.cols) * g.ch, g.cw, g.ch, 0, 0, c.width, c.height);
  for (const p of T.pendingPixels) {
    if (p.frame !== T.k) continue;
    ctx.clearRect(p.x - x0, p.y - y0, 1, 1);
    if (p.color.slice(7) !== "00") { ctx.fillStyle = p.color; ctx.fillRect(p.x - x0, p.y - y0, 1, 1); }
  }
  return c;
}

function stDraw() {
  if (!T.plan || !T.viewBox || !stHere()) return;
  const c = $("stCanvas"), ctx = c.getContext("2d"), b = T.viewBox;
  const sx = c.width / (b[2] - b[0]), sy = c.height / (b[3] - b[1]);
  ctx.imageSmoothingEnabled = T.zoom < 1; ctx.fillStyle = $("stBack").value; ctx.fillRect(0, 0, c.width, c.height);
  for (const effect of T.scene.effects) stDrawEffect(ctx, effect, false, sx, sy);
  const character = stCharacterCanvas();
  if (character) ctx.drawImage(character, (T.plan.box[0] - b[0]) * sx, (T.plan.box[1] - b[1]) * sy, character.width * sx, character.height * sy);
  for (const effect of T.scene.effects) stDrawEffect(ctx, effect, true, sx, sy);
  stDrawPixelGuides(ctx, sx, sy);
  $("stInfo").textContent = `第 ${T.k + 1} / ${T.plan.frames} 帧（工具编号 ${T.k}） · ${T.zoom.toFixed(2)}×` + (T.scene.effects.length ? ` · ${T.scene.effects.length} 个技能图层，手动配时` : "");
  stPixelCount(); stTimelineStatus();
}

function stGo(k) {
  if (T.stroke) return;
  const span = T.end - T.start + 1; T.k = T.start + ((k - T.start) % span + span) % span;
  T.sceneTick = T.k - T.start; ++T.sampleRequest; stDraw();
  if (!T.playing) stTask(stLoadFullFrame);
}
async function stLoadFullFrame() {
  if (!T.plan || T.plan.atlas.scale === 1 || !stHere()) return;
  if (T.fullFrame?.key === T.plan.key && T.fullFrame.k === T.k) return;
  const request = ++T.frameRequest, roleRequest = T.roleRequest, key = T.plan.key, k = T.k;
  const response = await fetch("/api/studio/frame", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...stPayload(), k})});
  const image = await stImageBlob(response);
  if (request !== T.frameRequest || roleRequest !== T.roleRequest || !stHere() || key !== T.plan?.key || k !== T.k) return;
  T.fullFrame = {key, k, image}; stDraw();
}
function stPlay(on) {
  if (on && T.stroke) { toast("请先结束或取消当前笔画。"); return; }
  T.playing = on; clearTimeout(T.timer);
  if ($("stPlay")) $("stPlay").textContent = on ? "暂停" : "播放";
  if (!on || !stHere()) { if (!on) stTask(stLoadFullFrame); return; }
  if ($("stPixelMode") && $("stPixelMode").value !== "view") { $("stPixelMode").value = "view"; stPixelMode(); }
  const tick = () => { T.timer = setTimeout(() => { if (!T.playing || !stHere()) return; stSeekTimeline(T.sceneTick + 1, true); tick(); }, 1000 / stCharacterFps()); }; tick();
}

function renderSlots() {
  $("stSlots").replaceChildren(...SLOTS.map(([slot, label]) => {
    const id = T.outfit[slot], hidden = T.plan.hidden.includes(slot), name = id ? T.names[id] || id : slot === "skin" ? "默认皮肤" : "（空）";
    const li = el("li", {className: slot === T.pick ? "on" : "", tabIndex: 0, role: "button"},
      el("span", {className: "slotname", textContent: label}), el("span", {className: `itemname${hidden ? " muted" : ""}`, title: id || "", textContent: name + (hidden ? "（被隐藏）" : "")}));
    const choose = () => { T.pick = slot; T.query = ""; $("stQuery").value = ""; T.tab = "items"; $("stDyeSlot").value = slot; renderDye(); renderSlots(); return renderPicker(); };
    li.addEventListener("click", () => stTask(choose));
    li.addEventListener("keydown", e => { if (e.target === li && ["Enter", " "].includes(e.key)) { e.preventDefault(); stTask(choose); } });
    if (id) {
      const remove = stButton("×", () => {}, {className: "x", title: "脱下"});
      remove.addEventListener("click", e => { e.stopPropagation(); delete T.outfit[slot]; stTask(refresh); }); li.append(remove);
    }
    return li;
  }));
}

async function renderPicker() {
  if (!stHere() || !T.info) return;
  const request = ++T.pickerRequest, roleRequest = T.roleRequest, slot = T.pick, label = SLOTS.find(s => s[0] === slot)[1];
  $("stPickTitle").textContent = T.tab === "sets" ? "套装" : `换${label}`;
  $("stTabItems").setAttribute("aria-pressed", String(T.tab === "items")); $("stTabSets").setAttribute("aria-pressed", String(T.tab === "sets"));
  $("stWeaponKind").hidden = !(slot === "weapon" && T.tab === "items");
  $("stResults").replaceChildren(el("li", {className: "muted small", textContent: "读取中…"}));
  try {
    if (T.tab === "sets") {
      const sets = await api(`/api/studio/sets?${new URLSearchParams({role: T.role, q: T.query})}`);
      if (request !== T.pickerRequest || roleRequest !== T.roleRequest || !stHere()) return;
      $("stResults").replaceChildren(...(sets.length ? sets.map(s => {
        const b = stButton(s.name, () => {
          for (const m of s.members) { const key = SLOTS.some(x => x[0] === m.slot) ? m.slot : "weapon"; T.outfit[key] = m.item_id; T.names[m.item_id] = m.name; }
          return refresh();
        }, {className: "stItemButton", title: s.members.map(m => m.name).join("、")});
        return el("li", {}, b, el("div", {className: "small muted", textContent: s.members.map(m => m.name).join("、")}));
      }) : [el("li", {className: "muted small", textContent: "没有找到套装"})])); return;
    }
    const kind = slot === "weapon" ? T.weaponKind : slot;
    const r = await api(`/api/studio/items?${new URLSearchParams({role: T.role, slot: kind, q: T.query})}`);
    if (request !== T.pickerRequest || roleRequest !== T.roleRequest || !stHere()) return;
    $("stResults").replaceChildren(...(r.items.length ? r.items.map(i => el("li", {className: T.outfit[slot] === i.item_id ? "on" : ""},
      stButton(i.name, async () => { T.outfit[slot] = i.item_id; T.names[i.item_id] = i.name; await Promise.all([refresh(), renderPicker()]); }, {className: "stItemButton", title: `物品 ID ${i.item_id}`}),
      el("span", {className: "small muted", textContent: ` ${i.code ?? ""}${i.hide.length ? " · 会隐藏 " + i.hide.join("") : ""}`}))) : [el("li", {className: "muted small", textContent: "没有找到"})]),
      ...(r.more ? [el("li", {className: "muted small", textContent: "只显示前 60 个，换关键词缩小范围"})] : []));
  } catch (error) { if (request === T.pickerRequest && stHere()) { $("stResults").replaceChildren(el("li", {className: "bad small", textContent: `读取失败：${error.message}`})); throw error; } }
}

function renderLayers() {
  $("stLayers").replaceChildren(...T.plan.layers.map(l => el("li", {className: l.source ? "" : "bad", title: l.path},
    el("span", {className: "z", textContent: l.z}), ` ${l.tag} ${l.name}`, l.patched ? el("span", {className: "badge info", textContent: "补丁"}) : null, l.source ? null : el("span", {className: "badge bad", textContent: "缺"}))));
}

// Dye recipes are applied to a slot before its layers are composited. RGB replacements can address a palette color exactly.
function stDyeTools() {
  const range = (id, label, min, max, step, value) => stField(label, el("span", {className: "stRange"}, el("input", {id, type: "range", min, max, step, value}), el("output", {id: `${id}Value`})));
  return el("section", {className: "card stDye"}, el("h3", {textContent: "调色"}),
    stField("部位", stSelect("stDyeSlot", SLOTS)),
    range("stHue", "色相", -180, 180, 1, 0), range("stSaturation", "饱和度", 0, 2, .05, 1), range("stLightness", "明度", -100, 100, 1, 0),
    el("div", {className: "row"}, stButton("重置这个部位", () => { if (T.customization.dyes) delete T.customization.dyes[$("stDyeSlot").value]; renderDye(); return refresh(); })),
    el("details", {}, el("summary", {textContent: "指定颜色替换"}),
      el("div", {className: "row stColorRow"}, stField("原色", el("input", {type: "color", id: "stColorFrom", value: "#ffffff"})), stField("新色", el("input", {type: "color", id: "stColorTo", value: "#c39bff"}))),
      el("div", {className: "row"}, stField("容差", el("input", {type: "number", id: "stColorTolerance", min: 0, max: 255, value: 0, className: "stNumber"})),
        stButton("替换原色取样", () => { $("stPixelMode").value = "source"; stPixelMode(); stStatus("点击人物，读取所选部位的原始颜色。"); }), stButton("添加替换", stAddReplacement)),
      el("div", {id: "stSampleInfo", className: "stSampleInfo small", role: "status", textContent: "替换匹配原始部位颜色；取样不受当前调色或半透明混合影响。"}),
      el("ul", {id: "stColorRules", className: "plain small"})),
    el("p", {id: "stDyeNote", className: "small muted", textContent: "按部位保存配方，不改原始资源。"}),
    el("p", {id: "stDyeHint", className: "small muted", hidden: true,
      textContent: "整体绘制补丁的画面可能集中在一个部位；某部位调色无变化时，可试选“皮肤”，再用指定颜色替换调整局部。"}));
}
function stBindDyeTools() {
  stOn("stDyeSlot", "change", () => { ++T.sampleRequest; renderDye(); });
  for (const id of ["stColorFrom", "stColorTo", "stColorTolerance"]) stOn(id, "input", () => { ++T.sampleRequest; });
  for (const id of ["stHue", "stSaturation", "stLightness"]) stOn(id, "input", () => {
    ++T.sampleRequest;
    const slot = $("stDyeSlot").value; T.customization.dyes ||= {};
    const dye = T.customization.dyes[slot] ||= {}; dye.hue = Number($("stHue").value); dye.saturation = Number($("stSaturation").value); dye.lightness = Number($("stLightness").value);
    stDyeValues(); clearTimeout(T.dyeTimer); T.dyeTimer = setTimeout(() => stTask(refresh), 220);
  });
}
async function stSampleSource(point) {
  const request = ++T.sampleRequest, roleRequest = T.roleRequest, composeRequest = T.composeRequest;
  const slot = $("stDyeSlot").value, frame = T.k, payload = {...stPayload(), slot, frame, x: point.x, y: point.y};
  const before = [$("stColorFrom").value, $("stColorTo").value, $("stColorTolerance").value].join("|");
  $("stSampleInfo").textContent = "正在读取部位原色…";
  let data;
  try { data = await stPost("/api/studio/sample", payload); }
  catch (error) { if (request !== T.sampleRequest || roleRequest !== T.roleRequest || !stHere()) return; throw error; }
  if (request !== T.sampleRequest || roleRequest !== T.roleRequest || composeRequest !== T.composeRequest || !stHere() ||
      slot !== $("stDyeSlot").value || frame !== T.k || $("stPixelMode").value !== "source" ||
      before !== [$("stColorFrom").value, $("stColorTo").value, $("stColorTolerance").value].join("|")) return;
  const label = SLOTS.find(s => s[0] === slot)?.[1] || slot;
  if (data.matched) {
    $("stColorFrom").value = data.color;
    $("stSampleInfo").textContent = `${label}原色 ${data.color} · alpha ${data.alpha} · 世界坐标 ${point.x}, ${point.y}`;
  } else {
    $("stSampleInfo").replaceChildren(el("span", {textContent: `${label}在此处无原始像素。整体绘制人物可试选“皮肤”。`}),
      ...data.available_slots.map(candidate => stButton(`改用${SLOTS.find(s => s[0] === candidate.slot)?.[1] || candidate.slot} ${candidate.color}`, () => {
        if (request !== T.sampleRequest || roleRequest !== T.roleRequest || composeRequest !== T.composeRequest || frame !== T.k) return;
        ++T.sampleRequest; $("stDyeSlot").value = candidate.slot; $("stColorFrom").value = candidate.color; renderDye();
        $("stSampleInfo").textContent = `已选择${SLOTS.find(s => s[0] === candidate.slot)?.[1] || candidate.slot}原色 ${candidate.color} · alpha ${candidate.alpha}`;
      })));
  }
}
function stDyeValues() {
  $("stHueValue").textContent = `${$("stHue").value}°`; $("stSaturationValue").textContent = `${Math.round(Number($("stSaturation").value) * 100)}%`; $("stLightnessValue").textContent = $("stLightness").value;
}
function renderDye() {
  if (!$("stDyeSlot")) return;
  const slot = $("stDyeSlot").value, dye = T.customization.dyes?.[slot] || {};
  $("stHue").value = dye.hue ?? 0; $("stSaturation").value = dye.saturation ?? 1; $("stLightness").value = dye.lightness ?? 0; stDyeValues();
  $("stDyeNote").textContent = slot === "weapon" ? "武器调色仅供预览和保存。导出衣装补丁前请重置武器调色，武器将保持原样。" : "按部位保存配方。容差 0 精确匹配颜色；像素修改会在调色之后应用。";
  $("stDyeHint").hidden = !T.overlay;
  $("stColorRules").replaceChildren(...(dye.colors || []).map((rule, i) => {
    const swatch = color => { const span = el("span", {className: "stSwatch", title: color}); span.style.backgroundColor = color; return span; };
    return el("li", {className: "row"}, swatch(rule.from), "→", swatch(rule.to), `容差 ${rule.tolerance || 0}`,
      stButton("移除", () => { T.customization.dyes[slot].colors.splice(i, 1); renderDye(); return refresh(); }));
  }));
}
async function stAddReplacement() {
  ++T.sampleRequest;
  const slot = $("stDyeSlot").value; T.customization.dyes ||= {}; const dye = T.customization.dyes[slot] ||= {}; dye.colors ||= [];
  if (dye.colors.length >= 32) throw new Error("每个部位最多 32 条颜色替换。");
  dye.colors.push({from: $("stColorFrom").value, to: $("stColorTo").value, tolerance: Math.max(0, Math.min(255, Math.trunc(Number($("stColorTolerance").value) || 0)))});
  renderDye(); await refresh();
}

function stPixelTools() {
  return el("div", {className: "card stPixelTools"},
    el("div", {className: "row"},
      stField("像素", stSelect("stPixelMode", [["view", "查看"], ["paint", "画笔"], ["erase", "透明橡皮"], ["sample", "画笔画面取色"], ["source", "替换原色取样"]])),
      el("input", {type: "color", id: "stPixelColor", value: "#ffffff", ariaLabel: "画笔颜色"}),
      stField("笔宽", stSelect("stBrush", [[1, "1 px"], [2, "2 px"], [3, "3 px"], [5, "5 px"]])),
      stButton("撤销笔画", stUndoPixel, {id: "stUndo"}), stButton("重做笔画", stRedoPixel, {id: "stRedo"}),
      stButton("清除此帧", stClearFrame), stButton("重试合成", refresh),
      stField("像素网格", el("input", {type: "checkbox", id: "stPixelGrid"}))),
    el("div", {className: "small muted", id: "stPixelCount", textContent: "画笔和橡皮只改当前帧；切到编辑工具会暂停。"}),
    el("output", {className: "small muted", id: "stPixelCoords", textContent: "移到人物画布查看世界像素坐标；网格在 4× 以上显示。"}));
}
function stPixelMode() {
  stCancelStroke(); ++T.sampleRequest; T.hover = null;
  const editing = $("stPixelMode").value !== "view";
  if (editing) stPlay(false);
  $("stCanvas").classList.toggle("editing", editing);
  stLayout();
}
function stPixelCount() {
  if (!$("stPixelCount")) return;
  const pixels = T.customization.pixels || [], n = pixels.filter(p => p.frame === T.k).length;
  $("stPixelCount").textContent = `当前帧 ${n} 个修改像素，合计 ${pixels.length} / 2000 个 · 编辑人物合成帧；编辑时隐藏技能。`;
  $("stUndo").disabled = !T.undo.length || !!T.stroke;
  $("stRedo").disabled = !T.redo.length || !!T.stroke;
}
function stPixelPoint(clientX, clientY, rect, box) {
  return {x: Math.floor(box[0] + (clientX - rect.left) / rect.width * (box[2] - box[0])), y: Math.floor(box[1] + (clientY - rect.top) / rect.height * (box[3] - box[1]))};
}
function stBindPixelTools() {
  stOn("stPixelMode", "change", stPixelMode);
  stOn("stPixelGrid", "change", stDraw);
  const c = $("stCanvas");
  c.addEventListener("pointerdown", e => stTask(() => {
    if (e.button !== 0 || T.stroke || !T.plan || $("stPixelMode").value === "view") return;
    if (T.busy) { toast("正在合成，完成后即可编辑。"); return; }
    if (T.plan.atlas.scale !== 1 && !(T.fullFrame?.key === T.plan.key && T.fullFrame.k === T.k)) { stTask(stLoadFullFrame); toast("正在读取原尺寸单帧，完成后即可编辑。"); return; }
    e.preventDefault(); c.focus({preventScroll: true}); stPlay(false);
    const p = stPixelPoint(e.clientX, e.clientY, c.getBoundingClientRect(), T.viewBox);
    if ($("stPixelMode").value === "source") return stSampleSource(p);
    if ($("stPixelMode").value === "sample") {
      const image = stCharacterCanvas(), x = p.x - T.plan.box[0], y = p.y - T.plan.box[1];
      if (x < 0 || y < 0 || x >= image.width || y >= image.height) return;
      const color = image.getContext("2d").getImageData(x, y, 1, 1).data;
      if (!color[3]) { toast("这里是透明像素。"); return; }
      const hex = "#" + [...color.slice(0, 3)].map(v => v.toString(16).padStart(2, "0")).join("");
      $("stPixelColor").value = hex; toast(`画笔已取画面色 ${hex}`); return;
    }
    const b = T.plan.box;
    if (p.x < b[0] || p.x >= b[2] || p.y < b[1] || p.y >= b[3]) { toast("请在人物画布范围内编辑；技能图层仅供预览。"); return; }
    if (stBeginStroke(e.pointerId, p, c.getBoundingClientRect())) c.setPointerCapture(e.pointerId);
  }));
  c.addEventListener("pointermove", e => {
    if (T.stroke) { stMoveStroke(e.pointerId, e.clientX, e.clientY); return; }
    if (!T.plan || $("stPixelMode").value === "view") return;
    T.hover = stPixelPoint(e.clientX, e.clientY, c.getBoundingClientRect(), T.viewBox);
    $("stPixelCoords").textContent = `世界像素 ${T.hover.x}, ${T.hover.y} · 人物工具帧 ${T.k}`; stDraw();
  });
  c.addEventListener("pointerup", e => stTask(() => stEndStroke(e.pointerId)));
  c.addEventListener("pointercancel", e => stCancelStroke(e.pointerId));
  c.addEventListener("lostpointercapture", e => stCancelStroke(e.pointerId));
  c.addEventListener("pointerleave", () => { if (!T.stroke) { T.hover = null; stDraw(); } });
}
function stBeginStroke(pointerId, point, rect) {
  if (T.stroke) return false;
  const mode = $("stPixelMode").value;
  if (mode !== "paint" && mode !== "erase") return false;
  T.stroke = {pointerId, frame: T.k, box: T.plan.box.slice(), viewBox: T.viewBox.slice(), key: T.plan.key,
    rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height}, mode,
    color: mode === "erase" ? "#00000000" : $("stPixelColor").value + "ff", width: Number($("stBrush").value),
    before: stCopy(T.customization.pixels || []), points: new Map(), previous: point};
  T.hover = point; stPaintPoint(point); return true;
}
function stMoveStroke(pointerId, clientX, clientY) {
  const stroke = T.stroke; if (!stroke || stroke.pointerId !== pointerId) return false;
  const p = stPixelPoint(clientX, clientY, stroke.rect, stroke.viewBox), a = stroke.previous;
  const steps = Math.max(Math.abs(p.x - a.x), Math.abs(p.y - a.y), 1);
  for (let i = 1; i <= Math.min(steps, 4096); i++) stPaintPoint({x: Math.round(a.x + (p.x - a.x) * i / steps), y: Math.round(a.y + (p.y - a.y) * i / steps)}, true);
  stroke.previous = p; T.hover = p; stDraw(); return true;
}
function stCancelStroke(pointerId) {
  if (!T.stroke || (pointerId !== undefined && T.stroke.pointerId !== pointerId)) return false;
  T.stroke = null; T.pendingPixels = []; stDraw(); return true;
}
async function stEndStroke(pointerId) {
  const stroke = T.stroke; if (!stroke || stroke.pointerId !== pointerId) return false;
  T.stroke = null;
  if (stroke.key !== T.plan?.key) { T.pendingPixels = []; stDraw(); return false; }
  const pixels = new Map(stroke.before.map(p => [`${p.frame}:${p.x}:${p.y}`, p]));
  for (const [key, p] of stroke.points) pixels.set(key, p);
  if (pixels.size > 2000) { T.pendingPixels = []; stDraw(); throw new Error("每套搭配最多保存 2000 个修改像素，这笔已取消，请缩小修改范围。"); }
  if (!stroke.points.size) return false;
  stPixelHistory(stroke.before); T.customization.pixels = [...pixels.values()]; stPixelCount(); await refresh(); return true;
}
function stPaintPoint(p, quiet = false) {
  const stroke = T.stroke; if (!stroke) return;
  const width = stroke.width, half = Math.floor(width / 2), b = stroke.box, color = stroke.color;
  for (let y = p.y - half; y < p.y - half + width; y++) for (let x = p.x - half; x < p.x - half + width; x++) {
    if (x < b[0] || x >= b[2] || y < b[1] || y >= b[3]) continue;
    if (T.stroke.points.size > 2000) break;
    const pixel = {frame: stroke.frame, x, y, color}; T.stroke.points.set(`${stroke.frame}:${x}:${y}`, pixel);
  }
  T.pendingPixels = [...T.stroke.points.values()]; if (!quiet) stDraw();
}
function stPixelHistory(before) {
  T.undo.push(stCopy(before)); if (T.undo.length > 30) T.undo.shift(); T.redo = [];
}
async function stUndoPixel() {
  if (T.stroke || !T.undo.length) return;
  T.redo.push(stCopy(T.customization.pixels || [])); T.customization.pixels = T.undo.pop(); await refresh();
}
async function stRedoPixel() {
  if (T.stroke || !T.redo.length) return;
  T.undo.push(stCopy(T.customization.pixels || [])); T.customization.pixels = T.redo.pop(); await refresh();
}
async function stClearFrame() {
  if (T.stroke) throw new Error("请先结束或取消当前笔画。");
  const before = T.customization.pixels || []; if (!before.some(p => p.frame === T.k)) return;
  stPixelHistory(before);
  T.customization.pixels = before.filter(p => p.frame !== T.k); await refresh();
}

function stDrawPixelGuides(ctx, sx, sy) {
  if ($("stPixelMode").value === "view") return;
  const b = T.viewBox;
  ctx.save();
  if ($("stPixelGrid")?.checked && Math.min(sx, sy) >= 4) {
    ctx.beginPath();
    for (let x = T.plan.box[0]; x <= T.plan.box[2]; x++) { ctx.moveTo((x - b[0]) * sx + .5, (T.plan.box[1] - b[1]) * sy); ctx.lineTo((x - b[0]) * sx + .5, (T.plan.box[3] - b[1]) * sy); }
    for (let y = T.plan.box[1]; y <= T.plan.box[3]; y++) { ctx.moveTo((T.plan.box[0] - b[0]) * sx, (y - b[1]) * sy + .5); ctx.lineTo((T.plan.box[2] - b[0]) * sx, (y - b[1]) * sy + .5); }
    ctx.lineWidth = 1; ctx.strokeStyle = "rgba(255,255,255,.22)"; ctx.stroke();
  }
  if (T.hover) {
    const width = T.stroke?.width || Number($("stBrush").value), half = Math.floor(width / 2);
    ctx.lineWidth = 1; ctx.strokeStyle = "#111"; ctx.strokeRect((T.hover.x - half - b[0]) * sx, (T.hover.y - half - b[1]) * sy, width * sx, width * sy);
    ctx.strokeStyle = "#fff"; ctx.strokeRect((T.hover.x - half - b[0]) * sx + 1, (T.hover.y - half - b[1]) * sy + 1, Math.max(0, width * sx - 2), Math.max(0, width * sy - 2));
  }
  ctx.restore();
}

// A scene intentionally has manual timing. The source ANI/PVF timing is not inferred from an IMG's frame count.
function stSceneTools() {
  return el("section", {className: "card stScene"}, el("h3", {textContent: "角色 + 武器 + 技能 · 手动组合"}),
    el("p", {className: "small muted", textContent: "选择技能 IMG，手动调整出场时机、位置和图层。播放速度与混合方式需在游戏中确认；这里只预览，不写入时装补丁。"}),
    el("div", {className: "stTimeline"}, stButton("从头重播", () => {
      if (T.stroke) throw new Error("请先结束或取消当前笔画。");
      $("stPixelMode").value = "view"; stPixelMode(); stSeekTimeline(0); stPlay(true);
    }, {id: "stSceneRestart"}),
      el("input", {type: "range", id: "stSceneTime", min: 0, max: 0, step: 1, value: 0, ariaLabel: "组合播放进度"}),
      el("output", {id: "stSceneClock", className: "small muted"})),
    el("div", {className: "row"}, el("input", {type: "search", id: "stEffectQuery", placeholder: "搜技能名或目录"}), el("select", {id: "stEffectFolder", ariaLabel: "技能目录"})),
    el("div", {className: "row"}, el("select", {id: "stEffectImg", ariaLabel: "技能 IMG"}), el("select", {id: "stEffectSource", ariaLabel: "技能原版或项目改版"}), stButton("添加图层", stAddEffect, {id: "stAddEffect"})),
    el("ul", {id: "stEffects", className: "plain"}), el("output", {id: "stEffectState", className: "small muted"}), el("div", {id: "stEffectEditor"}));
}
function stClass() { return T.info.cls || T.info.role.cls || T.role.replace(/_at$/, ""); }
function stBindSceneTools() {
  stOn("stSceneTime", "input", () => { stPlay(false); stSeekTimeline(Number($("stSceneTime").value)); });
  stOn("stEffectQuery", "input", stFilterSkills);
  stOn("stEffectFolder", "change", stLoadSkill);
  stOn("stEffectImg", "change", stEffectSources);
}
async function stLoadSkills(roleRequest) {
  const data = await api(`/api/game/skills?${new URLSearchParams({cls: stClass()})}`);
  if (roleRequest !== T.roleRequest || !stHere()) return;
  T.skills = data.skills.filter(s => !s.special && !s.folder.startsWith("@")); $("stEffectQuery").value = "";
  stFilterSkills();
}
function stFilterSkills() {
  const query = $("stEffectQuery").value.trim().toLowerCase(), before = $("stEffectFolder").value;
  const list = T.skills.filter(s => !query || `${s.folder} ${s.name} ${s.transfer}`.toLowerCase().includes(query));
  $("stEffectFolder").replaceChildren(el("option", {value: "", textContent: list.length ? "选择技能目录" : "没有找到技能目录"}), ...list.map(s => el("option", {value: s.folder, textContent: `${s.name || s.folder}${s.name && !s.checked ? "（未核实）" : ""} · ${s.imgs} IMG`})));
  $("stEffectFolder").value = list.some(s => s.folder === before) ? before : "";
  if (!$("stEffectFolder").value) { ++T.skillRequest; T.skillItems = []; $("stEffectImg").replaceChildren(); $("stEffectSource").replaceChildren(); }
}
async function stLoadSkill() {
  const request = ++T.skillRequest, roleRequest = T.roleRequest, folder = $("stEffectFolder").value;
  T.skillItems = []; $("stEffectImg").replaceChildren(el("option", {textContent: "读取 IMG…"})); $("stEffectSource").replaceChildren();
  if (!folder) { $("stEffectImg").replaceChildren(); return; }
  const data = await api(`/api/game/skill?${new URLSearchParams({cls: stClass(), folder})}`);
  if (request !== T.skillRequest || roleRequest !== T.roleRequest || !stHere()) return;
  T.skillItems = data.items.filter(it => !it.still);
  for (const it of T.skillItems) T.effectMeta.set(it.path, it);
  $("stEffectImg").replaceChildren(...T.skillItems.map(it => el("option", {value: it.path, textContent: `${it.label}（${it.frames} 帧）`})));
  stEffectSources();
}
function stEffectSources() {
  const it = T.skillItems.find(i => i.path === $("stEffectImg").value);
  $("stEffectSource").replaceChildren(...(it ? [el("option", {value: "official", textContent: "官方原版"}), ...it.mods.map(m => el("option", {value: m.project, textContent: `${m.name} ${m.version}`}))] : []));
}
async function stAddEffect() {
  if (T.scene.effects.length >= 8) throw new Error("一个组合最多 8 个技能图层。");
  const path = $("stEffectImg").value, source = $("stEffectSource").value;
  if (!path || !source) throw new Error("先选择技能目录和 IMG。");
  const effect = {path, source, start: 0, fps: 15, x: 0, y: 0, scale: 1, opacity: 1, front: true, loop: false, enabled: true, blend: "normal"};
  T.scene.effects.push(effect); T.effectPick = T.scene.effects.length - 1; renderEffects(); stLayout();
  await stLoadEffectImage(effect);
}
async function stLoadEffectImage(effect) {
  const key = stEffectKey(effect); if (T.effectImages.has(key)) return;
  const meta = T.effectMeta.get(effect.path), mod = meta?.mods?.find(m => m.project === effect.source);
  const response = await fetch(`/api/game/atlas?${new URLSearchParams({path: effect.path, src: effect.source, v: mod?.stamp || "o"})}`);
  const image = await stImageBlob(response); T.effectImages.set(key, image);
  if (T.effectImages.size > 24) T.effectImages.delete(T.effectImages.keys().next().value);
  if (stHere()) stDraw();
}
async function stRestoreEffects(roleRequest) {
  const cls = stClass(), effects = T.scene.effects;
  const folders = new Set(effects.map(e => {
    const prefix = `sprite/character/${cls}/effect/`, rest = e.path.startsWith(prefix) ? e.path.slice(prefix.length) : "";
    return rest.includes("/") ? rest.split("/")[0] : "(根目录)";
  }));
  for (const folder of folders) {
    const data = await api(`/api/game/skill?${new URLSearchParams({cls, folder})}`);
    if (roleRequest !== T.roleRequest || !stHere()) return;
    for (const it of data.items) T.effectMeta.set(it.path, it);
  }
  if (roleRequest !== T.roleRequest || !stHere()) return;
  await Promise.all(effects.map(e => stLoadEffectImage(e)));
  if (roleRequest === T.roleRequest && stHere()) { renderEffects(); stLayout(); }
}
function renderEffects() {
  if (!$("stEffects")) return;
  $("stEffects").replaceChildren(...T.scene.effects.map((e, i) => {
    const meta = T.effectMeta.get(e.path), name = meta?.label || e.path.split("/").pop();
    const visible = el("input", {type: "checkbox", checked: e.enabled !== false, ariaLabel: `${name}图层显示`});
    visible.addEventListener("change", () => { e.enabled = visible.checked; renderEffects(); stLayout(); });
    return el("li", {className: `row${i === T.effectPick ? " on" : ""}`}, visible, stButton(`${i + 1}. ${name}`, () => { T.effectPick = i; renderEffects(); }, {className: "stEffectName", title: e.path}),
      el("span", {className: "small muted", textContent: `${e.source === "official" ? "原版" : "改版"} · ${e.front ? "前景" : "后景"}`}),
      stButton("上移", () => stMoveEffect(i, -1), {ariaLabel: `${name}在同景别上移`}), stButton("下移", () => stMoveEffect(i, 1), {ariaLabel: `${name}在同景别下移`}),
      stButton("移除", () => { T.scene.effects.splice(i, 1); T.effectPick = Math.min(T.effectPick, T.scene.effects.length - 1); renderEffects(); stLayout(); }));
  }));
  stTimelineStatus();
  const effect = T.scene.effects[T.effectPick]; $("stEffectEditor").replaceChildren(); if (!effect) return;
  const fields = [["start", "延后（人物帧）", 0, 9999, 1], ["fps", "技能帧/秒", 1, 60, 1], ["x", "X 位移", -4096, 4096, 1], ["y", "Y 位移", -4096, 4096, 1], ["scale", "缩放", .05, 8, .05], ["opacity", "不透明度", 0, 1, .05]];
  const grid = el("div", {className: "stEffectFields"});
  for (const [key, label, min, max, step] of fields) {
    const input = el("input", {type: "number", min, max, step, value: effect[key], ariaLabel: label});
    stBindEffectNumber(input, effect, key, min, max);
    grid.append(stField(label, input));
  }
  for (const [key, label] of [["front", "放在人物前面"], ["loop", "循环技能"]]) {
    const input = el("input", {type: "checkbox", checked: effect[key]});
    input.addEventListener("change", () => { effect[key] = input.checked; renderEffects(); stLayout(); }); grid.append(stField(label, input));
  }
  const src = stSelect("stSceneSource", [["official", "官方原版"], ...(T.effectMeta.get(effect.path)?.mods || []).map(m => [m.project, `${m.name} ${m.version}`])]); src.value = effect.source;
  src.addEventListener("change", () => stTask(async () => { effect.source = src.value; renderEffects(); await stLoadEffectImage(effect); }));
  const blend = stSelect("stSceneBlend", [["normal", "普通"], ["add", "发光（加色）"]]); blend.value = effect.blend || "normal";
  blend.addEventListener("change", () => { effect.blend = blend.value; stDraw(); });
  grid.append(stField("素材版本", src), stField("混合", blend)); $("stEffectEditor").append(grid);
}
function stMoveEffect(index, direction) {
  const effect = T.scene.effects[index]; if (!effect) return false;
  let other = index + direction;
  while (other >= 0 && other < T.scene.effects.length && T.scene.effects[other].front !== effect.front) other += direction;
  if (other < 0 || other >= T.scene.effects.length) return false;
  [T.scene.effects[index], T.scene.effects[other]] = [T.scene.effects[other], T.scene.effects[index]];
  T.effectPick = other; renderEffects(); stDraw(); return true;
}
function stBindEffectNumber(input, effect, key, min, max) {
  const update = commit => {
    // A number input can be empty while a minus sign or decimal is being entered. Preserve that in-progress text.
    const value = input.value.trim() ? Number(input.value) : NaN;
    if (Number.isFinite(value)) {
      effect[key] = Math.max(min, Math.min(max, value));
      if (key === "start") effect[key] = Math.trunc(effect[key]);
      stLayout();
    }
    if (commit) input.value = effect[key];
  };
  input.addEventListener("input", () => update(false));
  input.addEventListener("change", () => update(true));
}

function renderWardrobe() {
  $("stWardrobe").replaceChildren(...(T.wardrobe.length ? T.wardrobe.slice().reverse().map(o => {
    const role = T.roles.find(r => r.role === o.role), edits = o.customization?.pixels?.length || 0, dyes = Object.keys(o.customization?.dyes || {}).length;
    const item = el("li", {}, el("b", {textContent: o.name}), el("span", {className: "small muted", textContent: ` ${role?.label || o.role} · ${o.saved}`}),
      edits || dyes || o.scene?.effects?.length ? el("div", {className: "small muted", textContent: `${dyes} 部位调色 · ${edits} 像素修改 · ${o.scene?.effects?.length || 0} 技能图层`}) : null,
      el("div", {className: "row"}, stButton("穿上", async () => { T.overlay = o.overlay || ""; await setRole(o.role, o.outfit, o.customization, o.scene); }),
        stButton("删", () => stConfirmOutfitDelete(o, item))));
    return item;
  }) : [el("li", {className: "muted small", textContent: "还没有保存的搭配"})]));
}
function stConfirmOutfitDelete(outfit, item) {
  if (item.querySelector(".stDeleteConfirm")) return;
  const note = el("p", {className: "small", textContent: `删除衣橱里的“${outfit.name}”？`});
  const status = el("span", {className: "small muted", role: "status"});
  const panel = el("div", {className: "stDeleteConfirm"}, note);
  const confirm = stButton("确认删除", async () => {
    confirm.disabled = true; cancel.disabled = true; status.textContent = "正在删除…";
    try {
      await stPost("/api/studio/wardrobe/delete", {id: outfit.id});
      T.wardrobe = (await api("/api/studio/wardrobe")).outfits;
      if (stHere()) { renderWardrobe(); toast(`已删除“${outfit.name}”`); }
    } catch (error) {
      status.textContent = `删除失败：${error.message}`; confirm.disabled = false; cancel.disabled = false;
    }
  });
  const cancel = stButton("取消", () => panel.remove());
  panel.append(el("div", {className: "row"}, confirm, cancel, status)); item.append(panel); cancel.focus();
}
async function saveOutfit() {
  if (T.stroke) throw new Error("请先结束当前笔画。");
  const name = $("stSaveName").value.trim(); if (!name) throw new Error("先给这套起个名字。");
  stRememberPlayback();
  await stPost("/api/studio/wardrobe/save", {...stPayload(), name, scene: stCopy(T.scene)});
  T.wardrobe = (await api("/api/studio/wardrobe")).outfits;
  if (stHere()) { renderWardrobe(); toast(`已保存“${name}”`); $("stSaveName").value = ""; }
}
const slotSummary = outfit => SLOTS.filter(([s]) => outfit[s]).map(([s, label]) => `${label}:${T.names[outfit[s]] || outfit[s]}`).join("，");
function renderCurrent() {
  if (!$("stCurrentText")) return;
  const c = T.current[T.role];
  $("stCurrentText").textContent = c ? `当前穿戴（${c.saved}）：${slotSummary(c.outfit) || "空"}` : "还没设当前穿戴：先在左边选出游戏里实际穿的几件，再点“设为当前穿戴”。";
  const target = slotSummary(Object.fromEntries(Object.entries(T.outfit).filter(([k]) => k !== "weapon")));
  $("stExportPlan").textContent = c ? `目标：${target || "空"}${T.overlay ? "，叠加 " + ($("stOverlay").selectedOptions[0]?.textContent || T.overlay) : ""}` : "先设当前穿戴。";
}
async function setCurrent() {
  const role = T.role, r = await stPost("/api/studio/current", {role, outfit: stCopy(T.outfit)}); T.current[role] = r;
  if (stHere()) { renderCurrent(); toast("已设为当前穿戴"); }
}
async function wearCurrent() {
  const c = T.current[T.role]; if (!c) throw new Error("还没设当前穿戴。");
  T.overlay = ""; $("stOverlay").value = ""; await setRole(T.role, c.outfit, {}, {effects: []});
}
async function exportOutfit() {
  if (T.stroke) throw new Error("请先结束当前笔画。");
  const c = T.current[T.role]; if (!c) throw new Error("先设当前穿戴。");
  const weapon = T.customization.dyes?.weapon;
  if (weapon && (weapon.hue || (weapon.saturation ?? 1) !== 1 || weapon.lightness || weapon.colors?.length)) throw new Error("武器调色仅供预览。请在调色区重置武器部位，再导出衣装补丁。");
  const name = $("stExportName").value.trim() || "outfit", b = $("stExport"); b.disabled = true; toast("导出中…");
  try {
    const r = await stPost("/api/studio/export", {role: T.role, current: stCopy(c.outfit), target: stCopy(T.outfit), overlay: T.overlay, customization: stCopy(T.customization), name});
    T.exports = await api("/api/studio/exports");
    if (stHere()) { renderExports(); toast(`已导出 ${r.npk}，${Math.round(r.size / 1024)} KB，模拟画面和目标${r.check.worst_frame_share ? "最多差 " + (r.check.worst_frame_share * 100).toFixed(1) + "%" : "完全一致"}`); }
  } finally { if (b.isConnected) b.disabled = false; }
}
function renderExports() {
  if (!$("stExports")) return;
  const mine = T.exports.filter(e => e.role === T.role);
  $("stExports").replaceChildren(...(mine.length ? mine.map(e => {
    const folder = e.folder.split("/").pop(), href = kind => `/api/studio/export_file?${new URLSearchParams({folder, kind})}`, ok = !e.check.worst_frame_share;
    return el("li", {}, el("b", {textContent: e.name}), el("span", {className: "muted", textContent: ` ${e.created.slice(5, 16)} · ${Math.round(e.size / 1024)} KB`}),
      el("div", {className: "muted", textContent: `载体 ${e.carrier.tag}（z ${e.carrier.z}），置空 ${e.blanked.length} 个；` + (ok ? "模拟和目标一致" : `模拟最多差 ${(e.check.worst_frame_share * 100).toFixed(1)}%`)}),
      el("div", {className: "row"}, el("a", {className: "button", href: href("npk"), textContent: "下载 NPK"}), el("a", {className: "button", href: href("preview"), target: "_blank", textContent: "预览图"}),
        stButton("文件夹", () => stPost("/api/studio/reveal", {folder}))));
  }) : [el("li", {className: "muted", textContent: "这个职业还没导出过"})]));
}

window.addEventListener("resize", () => { if (T.plan && stHere()) stLayout(); });
window.addEventListener("hashchange", () => { stCleanup(); });
document.addEventListener("keydown", e => {
  if (!stHere()) return;
  if (e.target.matches("input, textarea, select, button")) return;
  if (e.key === "Escape" && T.stroke) { e.preventDefault(); stCancelStroke(); stStatus("已取消当前笔画。"); return; }
  if (T.stroke) return;
  const key = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && (key === "z" || key === "y")) {
    e.preventDefault(); stTask(key === "y" || e.shiftKey ? stRedoPixel : stUndoPixel); return;
  }
  if (e.key === " ") { e.preventDefault(); stPlay(!T.playing); }
  if (e.key === "ArrowLeft") { e.preventDefault(); stPlay(false); stStep(-1); }
  if (e.key === "ArrowRight") { e.preventDefault(); stPlay(false); stStep(1); }
});
