"use strict";
// Buff portraits are short transparent animations. Play registered source frames inside the workbench;
// their encoded files and in-game checks have independent states.
const BUFF = {players: new Set()};
const buffRoute = (project, asset) => `#/p/${encodeURIComponent(project)}/buff/${encodeURIComponent(asset)}`;

function buffDisposeAll() {
  for (const player of BUFF.players) player.dispose();
  BUFF.players.clear();
}

function buffPlaybackFrame(elapsedMs, fps, frames, loop) {
  const n = Math.max(1, Math.trunc(frames)), k = Math.max(0, Math.floor(elapsedMs * fps / 1000));
  return {frame: loop ? k % n : Math.min(k, n - 1), ended: !loop && k >= n};
}

function buffClampFrame(frame, frames) { return Math.max(0, Math.min(Math.max(1, frames) - 1, Math.trunc(frame) || 0)); }
function buffMetadata(asset) {
  if (!(asset.frames > 0 && asset.width > 0 && asset.height > 0 && asset.fps > 0)) return "素材尚未就绪";
  return `${asset.frames} 帧 · ${asset.width}×${asset.height} · ${asset.fps} 帧/秒 · ${Number(asset.duration_seconds || asset.frames / asset.fps).toFixed(2)} 秒`;
}
function buffWarningText(warning) {
  const known = {
    "Generated cell aspect ratio differs from target; cells are uniformly fitted with transparent padding, never stretched": "原始动作表比例与目标不同，已等比例缩放并留透明边。",
    "Frame 11: soft alpha edge is 1px from the source cell boundary; boundary alpha is at most 5/255, not an opaque clipping edge": "第 11 帧原表的软透明边缘靠边，人物主体没有硬裁切。",
    "Frame 17: soft alpha edge is 1px from the source cell boundary; boundary alpha is at most 3/255, not an opaque clipping edge": "第 17 帧原表的软透明边缘靠边，人物主体没有硬裁切。"
  };
  return Object.hasOwn(known, warning) ? known[warning] : warning;
}

function buffBadges(asset) {
  return el("div", {className: "badges"},
    el("span", {className: `badge ${asset.status === "encoded" ? "ok" : asset.status === "unavailable" ? "bad" : "warn"}`, textContent: asset.status_label || (asset.status === "encoded" ? "已编码" : asset.status === "unavailable" ? "资源缺失" : "草稿已准备")}),
    el("span", {className: `badge ${asset.ingame_verified ? "ok" : "warn"}`, textContent: asset.ingame_verified ? "实机已通过" : "待实机验证"}),
    el("span", {className: "badge", textContent: asset.installed ? "已安装" : "未安装"}));
}

function buffDownloadLinks(asset, compact = false) {
  const names = compact ? [["bink", "下载 Bink"], ["mov", "下载透明 MOV"]]
    : [["bink", "下载 Bink 成片"], ["mov", "下载透明 MOV"], ["animation", "下载动画预览"], ["manifest", "帧清单"], ["encoding_report", "编码检查报告"]];
  return el("div", {className: "actions buffDownloads"}, ...names.filter(([kind]) => asset.files?.[kind]).map(([kind, label]) => el("a", {className: "button", href: asset.files[kind], download: "", textContent: label})),
    !asset.files?.bink ? el("span", {className: "small muted", textContent: "Bink 尚未就绪"}) : null);
}

function buffSourceSheet(asset, compact = false) {
  if (!asset.files?.sheet) return null;
  return el("details", {className: "buffSheet"}, el("summary", {textContent: "动画帧表"}),
    el("p", {className: "small muted", textContent: `${asset.frames} 帧总览，用于检查构图、人物一致性和动画衔接。`}),
    el("img", {src: asset.files.sheet, alt: `${asset.name} 动画帧表`, loading: "lazy", className: compact ? "compact" : ""}),
    el("div", {className: "actions"}, el("a", {className: "button", href: asset.files.sheet, download: "", textContent: "下载帧表"})));
}

function buffSourceArt(asset) {
  if (!asset.files?.source) return null;
  return el("details", {className: "box buffSheet"}, el("summary", {textContent: "主视觉原图"}),
    el("p", {className: "small muted", textContent: "查看主视觉的构图、神态、手势和服装细节。"}),
    el("img", {src: asset.files.source, alt: `${asset.name} 主视觉原图`, loading: "lazy"}),
    el("div", {className: "actions"}, el("a", {className: "button", href: asset.files.source, download: "", textContent: "下载主视觉"})));
}

function buffPlayer(asset, compact = false) {
  const n = Math.max(1, Number(asset.frames) || 1), fps = Math.max(1, Number(asset.fps) || 15);
  const width = Math.max(1, Number(asset.width) || 470), height = Math.max(1, Number(asset.height) || 668);
  const state = {frame: 0, playing: false, preparing: false, loop: false, disposed: false, timer: null, request: 0,
    source: "source", offset: 0, started: 0, images: new Map(), pending: new Map(), background: "#22282a"};
  const canvas = el("canvas", {width, height, tabIndex: 0, ariaLabel: `${asset.name} 逐帧预览`});
  const stage = el("div", {className: "buffStage"}, canvas);
  const play = el("button", {type: "button", textContent: "播放", ariaLabel: "播放 buff 动画"});
  const previous = el("button", {type: "button", textContent: "上一帧"}), next = el("button", {type: "button", textContent: "下一帧"});
  const progress = el("input", {type: "range", min: 0, max: n - 1, step: 1, value: 0, ariaLabel: "buff 帧进度"});
  const count = el("output", {className: "small", textContent: `第 1 / ${n} 帧`});
  const loop = el("input", {type: "checkbox", checked: false, ariaLabel: "重复播放 buff 动画"});
  const background = el("select", {ariaLabel: "buff 预览背景"},
    ...[["#22282a", "深色背景"], ["#c2c0ac", "浅色背景"], ["checker", "透明网格"]].map(([value, textContent]) => el("option", {value, textContent})));
  const source = el("select", {ariaLabel: "buff 预览来源"}, el("option", {value: "source", textContent: "透明 PNG 源帧"}),
    asset.encoded_frame_url ? el("option", {value: "encoded", textContent: "Bink 编码回读"}) : null);
  const status = el("div", {className: "small muted buffPlayerStatus", role: "status", ariaLive: "polite"});
  const root = el("div", {className: `buffPlayer${compact ? " compact" : ""}`}, stage,
    el("div", {className: "controls"}, play, previous, next, background, source,
      el("label", {className: "field"}, loop, "重复播放")),
    el("div", {className: "buffProgress"}, progress, count), status);
  const context = canvas.getContext("2d");

  function live() { return !state.disposed; }
  function message(text, bad = false) { if (!live()) return; status.textContent = text; status.classList.toggle("bad", bad); }
  function updateControls() {
    play.disabled = state.preparing;
    play.textContent = state.preparing ? "准备帧…" : state.playing ? "暂停" : "播放";
    play.setAttribute("aria-label", state.playing ? "暂停 buff 动画" : "播放 buff 动画");
    progress.value = state.frame; count.textContent = `第 ${state.frame + 1} / ${n} 帧 · ${fps} 帧/秒`;
  }
  function paintBackground() {
    if (state.background !== "checker") { context.fillStyle = state.background; context.fillRect(0, 0, width, height); return; }
    const cell = 20;
    for (let y = 0; y < height; y += cell) for (let x = 0; x < width; x += cell) {
      context.fillStyle = ((x / cell + y / cell) % 2) ? "#4c5159" : "#34383f"; context.fillRect(x, y, cell, cell);
    }
  }
  function frameKey(frame, selected = state.source) { return `${selected}:${frame}`; }
  function draw() {
    if (!live()) return;
    paintBackground();
    const image = state.images.get(frameKey(state.frame));
    if (image) context.drawImage(image, 0, 0, width, height);
    updateControls();
  }
  async function load(frame, selected = state.source) {
    const key = frameKey(frame, selected);
    if (state.images.has(key)) return state.images.get(key);
    if (state.pending.has(key)) return state.pending.get(key);
    const template = selected === "encoded" ? asset.encoded_frame_url : asset.frame_url;
    if (!template) throw new Error("没有可读取的逐帧预览。");
    const request = (async () => {
      const image = new Image(); image.decoding = "async"; image.src = template.replace("{k}", String(frame));
      try { await image.decode(); }
      catch { throw new Error(`第 ${frame + 1} 帧读取失败，请重试或刷新。`); }
      if (live()) state.images.set(key, image);
      return image;
    })();
    state.pending.set(key, request);
    try { return await request; } finally { state.pending.delete(key); }
  }
  function pause() {
    state.playing = false; clearTimeout(state.timer); state.timer = null; updateControls();
  }
  async function seek(frame) {
    pause(); const request = ++state.request; state.preparing = false; state.frame = buffClampFrame(frame, n); draw();
    message("读取当前帧…");
    try {
      await load(state.frame);
      if (live() && request === state.request) { draw(); message("已暂停，可逐帧检查。"); }
    } catch (error) { if (live() && request === state.request) message(error.message, true); }
  }
  async function preload(selected, request) {
    let frame = 0;
    const worker = async () => {
      while (frame < n && live() && request === state.request) { const k = frame++; await load(k, selected); }
    };
    await Promise.all(Array.from({length: Math.min(4, n)}, worker));
  }
  function tick() {
    if (!live() || !state.playing) return;
    const now = performance.now(), result = buffPlaybackFrame(state.offset + now - state.started, fps, n, state.loop);
    state.frame = result.frame; draw();
    if (result.ended) { pause(); message("本次播放结束。末帧已保留，可逐帧检查或重新播放。"); return; }
    state.timer = setTimeout(tick, Math.max(8, Math.min(40, 500 / fps)));
  }
  async function start() {
    if (state.playing) { pause(); message("已暂停。"); return; }
    if (state.preparing) return;
    const request = ++state.request; state.preparing = true; updateControls(); message(`准备 ${n} 帧…`);
    try {
      await preload(state.source, request);
      if (!live() || request !== state.request) return;
      state.preparing = false;
      if (state.frame >= n - 1) state.frame = 0;
      state.offset = state.frame * 1000 / fps; state.started = performance.now(); state.playing = true;
      message(state.loop ? "重复播放：末帧会跳回首帧，衔接尚未验收。" : "播放一次。"); tick();
    } catch (error) {
      if (live() && request === state.request) { state.preparing = false; pause(); message(error.message, true); }
    }
  }
  const controller = {dispose() {
    state.disposed = true; state.request++; clearTimeout(state.timer); state.images.clear(); state.pending.clear();
  }};
  BUFF.players.add(controller);
  play.addEventListener("click", start);
  previous.addEventListener("click", () => seek(state.frame - 1)); next.addEventListener("click", () => seek(state.frame + 1));
  progress.addEventListener("input", () => seek(Number(progress.value)));
  loop.addEventListener("change", () => { state.loop = loop.checked; if (state.playing) message(state.loop ? "重复播放：末帧会跳回首帧，衔接尚未验收。" : "当前播放结束后暂停。"); });
  background.addEventListener("change", () => { state.background = background.value; draw(); });
  source.addEventListener("change", () => { state.source = source.value; seek(state.frame); });
  canvas.addEventListener("keydown", event => {
    if (event.key === " ") { event.preventDefault(); start(); }
    if (event.key === "ArrowLeft") { event.preventDefault(); seek(state.frame - 1); }
    if (event.key === "ArrowRight") { event.preventDefault(); seek(state.frame + 1); }
  });
  draw(); seek(0);
  return root;
}

function buffProjectSection(project) {
  const assets = project.buff_assets || [];
  if (!assets.length) return [];
  return [el("h2", {textContent: "buff 立绘"}),
    el("p", {className: "small muted", textContent: "在工作台内检查动画。官方 buff 视频已加密，当前无法读取原版画面作逐帧对照。"}),
    el("div", {className: "buffCards"}, ...assets.map(asset => el("section", {className: "box buffAsset"},
      el("div", {className: "row"}, el("h3", {textContent: asset.name}), asset.version ? el("span", {className: "badge", textContent: asset.version}) : null),
      buffBadges(asset),
      el("p", {className: "small muted", textContent: buffMetadata(asset)}),
      asset.status === "unavailable" ? el("p", {className: "bad", textContent: "资源尚未就绪，暂不能播放。"}) : buffPlayer(asset, true),
      buffDownloadLinks(asset, true),
      el("div", {className: "actions"}, el("a", {className: "button primary", href: buffRoute(project.id, asset.id), textContent: "逐帧审核和详情"})),
      buffSourceSheet(asset, true))))];
}

async function buffPage(projectId, assetId, generation) {
  const [project, asset] = await Promise.all([
    api(`/api/projects/${enc(projectId)}`), api(`/api/projects/${enc(projectId)}/buff/${enc(assetId)}`)]);
  if (generation !== dashboardRoute) return;
  $("crumb").textContent = `/ ${project.name} / buff 立绘`;
  document.title = `${asset.name} · ${project.name} · 补丁工作台`;
  $("page").className = "page buffDetail";
  const info = el("section", {className: "box buffAssetInfo"}, el("h2", {textContent: "资产状态"}), buffBadges(asset),
    el("dl", {className: "kv"}, el("dt", {textContent: "版本"}), el("dd", {textContent: asset.version || "—"}),
      el("dt", {textContent: "画布"}), el("dd", {textContent: `${asset.width}×${asset.height}，透明背景`}),
      el("dt", {textContent: "动画"}), el("dd", {textContent: buffMetadata(asset)}),
      el("dt", {textContent: "编码"}), el("dd", {textContent: asset.encoding_status_label || (asset.status === "encoded" ? "已编码，待实机" : "尚未编码")})),
    el("p", {className: "small muted", textContent: "官方 buff 视频已加密，尚不能显示原版逐帧对照。这里播放本项目的透明源帧；有编码回读帧时可在播放器中切换。"}),
    el("p", {className: "small muted", textContent: "默认播放一次。开启重复后会从末帧回到首帧，循环衔接尚未验收。"}),
    buffDownloadLinks(asset));
  if (asset.warnings?.length) info.append(el("ul", {className: "buffWarnings"}, ...asset.warnings.map(warning => el("li", {textContent: buffWarningText(warning)}))));
  if (asset.license_note) info.append(el("p", {className: "small muted", textContent: asset.license_note}));
  if (asset.targets?.length) info.append(el("details", {}, el("summary", {textContent: `计划替换的 buff 文件（${asset.targets.length}）`}),
    el("ul", {className: "plain small buffTargets"}, ...asset.targets.map(target => el("li", {textContent: typeof target === "string" ? target : target.file || target.path || target.name || "—"})))));
  const player = asset.status === "unavailable" ? el("div", {className: "empty buffUnavailable", textContent: "资源尚未就绪，暂不能播放。"}) : buffPlayer(asset);
  const sheet = buffSourceSheet(asset);
  const sourceArt = buffSourceArt(asset);
  const contact = asset.files?.contact ? el("details", {className: "box buffSheet"}, el("summary", {textContent: "切帧检查表"}), el("img", {src: asset.files.contact, alt: `${asset.name} 切帧检查表`, loading: "lazy"})) : null;
  $("page").replaceChildren(el("div", {className: "actions"}, el("a", {className: "button", href: `#/p/${enc(projectId)}`, textContent: `返回${project.name}`})),
    el("h1", {textContent: asset.title || asset.name}), el("div", {className: "buffDetailGrid"}, player, info),
    ...(sourceArt ? [sourceArt] : []), ...(sheet ? [el("section", {className: "box"}, sheet)] : []), ...(contact ? [contact] : []));
}
