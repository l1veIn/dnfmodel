"use strict";
// The game's own skill effects, class by class: original next to every project's version, or "暂无改版". Uses helpers from dash.js.
const G = {cls: null, skills: [], folder: null, skill: null, item: 0, k: 0, playing: true, timer: null, images: new Map(), filter: "all", query: ""};

// Animated IMGs come as one atlas; stills (portraits) one frame at a time, since a shared picture IMG can hold 78 large frames.
function gameImage(it, src, stamp, onload) {
  return it.still ? gameLoad(`/api/game/frame?${new URLSearchParams({path: it.path, src, k: G.k, v: stamp})}`, onload)
                  : gameLoad(`/api/game/atlas?${new URLSearchParams({path: it.path, src, v: stamp})}`, onload);
}

function gameLoad(url, onload) {
  if (!G.images.has(url)) { const img = new Image(); img.decoding = "async"; img.onload = onload; img.src = url; G.images.set(url, img); }
  return G.images.get(url);
}

async function gamePage(cls, folder) {
  $("crumb").textContent = "/ DNF 资源";
  document.title = "DNF 资源 · 补丁工作台";
  const classes = await api("/api/game/classes");
  cls = cls || G.cls || "gunner";
  if (!$("gameSide") || G.cls !== cls) {
    G.cls = cls;
    G.skills = (await api(`/api/game/skills?${new URLSearchParams({cls})}`)).skills;
    const select = el("select", {id: "gameClass", ariaLabel: "职业"}, ...classes.map(c => el("option", {value: c.cls, textContent: `${c.cls}${c.labels.length ? "：" + c.labels.join("、") : ""}（${c.imgs}）`})));
    select.value = cls;
    select.addEventListener("change", () => { location.hash = `#/game/${enc(select.value)}`; });
    const search = el("input", {type: "search", id: "gameSearch", placeholder: "搜技能名或目录名", value: G.query});
    search.addEventListener("input", () => { G.query = search.value.trim().toLowerCase(); renderSkillList(); });
    const filter = el("select", {id: "gameFilter", ariaLabel: "筛选"}, ...[["all", "全部"], ["mod", "有改版"], ["named", "有中文名"], ["unnamed", "没有中文名"]].map(([v, t]) => el("option", {value: v, textContent: t})));
    filter.value = G.filter;
    filter.addEventListener("change", () => { G.filter = filter.value; renderSkillList(); });
    $("page").className = "page wide";
    $("page").replaceChildren(el("div", {className: "gamewrap"},
      el("aside", {className: "gside", id: "gameSide"}, select, el("div", {className: "row"}, search, filter), el("div", {id: "skillCount", className: "small muted"}), el("ul", {id: "skillList"})),
      el("section", {className: "gmain", id: "gameMain"}, el("p", {className: "muted", textContent: "左边选一个技能目录。一个目录就是游戏里一个技能（或一组道具）的全部特效 IMG。"}))));
  }
  renderSkillList();
  if (folder) await openSkill(folder);
}

function skillTitle(s) { return s.name || s.folder; }

function renderSkillList() {
  const q = G.query, list = G.skills.filter(s => {
    if (G.filter === "mod" && !s.mods.length) return false;
    if (G.filter === "named" && !s.name) return false;
    if (G.filter === "unnamed" && s.name) return false;
    return !q || s.folder.toLowerCase().includes(q) || (s.name || "").toLowerCase().includes(q) || (s.transfer || "").toLowerCase().includes(q);
  });
  $("skillCount").textContent = `${list.length} / ${G.skills.length} 个目录，${G.skills.filter(s => s.mods.length).length} 个有改版`;
  $("skillList").replaceChildren(...list.map(s => {
    const tag = s.mods.length ? el("span", {className: "tag pass", textContent: "已改"}) : el("span", {className: `tag${s.special ? " fixed" : ""}`, textContent: s.special ? "立绘" : `${s.imgs}`});
    const name = el("span", {className: `name${s.name && !s.checked ? " guess" : ""}`, textContent: (s.transfer ? `${s.transfer} · ` : "") + skillTitle(s) + (s.name && !s.checked ? "（未核实）" : "")});
    const b = el("button", {type: "button", title: s.folder}, name, tag, el("span", {className: "code", textContent: s.name ? s.folder : `${s.imgs} 个 IMG`}));
    b.setAttribute("aria-current", String(s.folder === G.folder));
    b.addEventListener("click", () => { location.hash = `#/game/${enc(G.cls)}/${enc(s.folder)}`; });
    return el("li", {}, b);
  }));
}

async function openSkill(folder) {
  G.folder = folder; G.item = 0; G.k = 0;
  renderSkillList();
  $("skillList").querySelector('[aria-current="true"]')?.scrollIntoView({block: "nearest"});
  $("gameMain").replaceChildren(el("p", {className: "muted", textContent: "读取中…"}));
  if (folder === "@buffvideo") { G.skill = null; return renderVideos(); }
  G.skill = await api(`/api/game/skill?${new URLSearchParams({cls: G.cls, folder})}`);
  G.k = G.skill.items[0]?.start || 0;
  renderSkill();
}

function renderSkill() {
  const s = G.skills.find(x => x.folder === G.folder), sk = G.skill;
  const name = el("input", {type: "text", value: s.name, placeholder: "中文技能名"});
  const transfer = el("input", {type: "text", value: s.transfer, placeholder: "转职，比如 女机械"});
  const checked = el("input", {type: "checkbox", checked: s.checked});
  const status = el("span", {className: "small muted"});
  const save = button("保存名称", async () => {
    try {
      const r = await api("/api/game/name", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({cls: G.cls, folder: G.folder, name: name.value, transfer: transfer.value, checked: checked.checked})});
      Object.assign(s, {name: r.name, transfer: r.transfer, checked: r.checked, source: r.source});
      status.textContent = "已保存"; renderSkillList(); $("skillTitle").textContent = skillTitle(s);
    } catch (error) { status.textContent = `没保存上：${error.message}`; }
  });
  const modsText = s.mods.length ? s.mods.map(m => `${m.name} ${m.version}（${m.imgs}/${s.imgs} 个 IMG）`).join("；") : "没有项目改过这个技能";
  const imgs = el("div", {className: "imgs", id: "imgChips"}, ...sk.items.map((it, n) => {
    const b = el("button", {type: "button", className: it.mods.length ? "mod" : "", textContent: `${it.label} · ${it.frames}`, title: it.path});
    b.setAttribute("aria-current", String(n === G.item));
    b.addEventListener("click", () => { G.item = n; G.k = it.start || 0; renderSkill(); });
    return b;
  }));
  const fps = el("input", {type: "range", min: 2, max: 30, step: 1, value: 10, id: "gfps"});
  const fpsText = el("span", {className: "small muted", id: "gfpsText"});
  const back = el("select", {id: "gback"}, ...[["#22282a", "深色"], ["#56617a", "灰蓝"], ["#000000", "黑"], ["#c2c0ac", "浅色"]].map(([v, t]) => el("option", {value: v, textContent: t})));
  const play = button("暂停", () => gameSetPlaying(!G.playing)); play.id = "gplay";
  fps.addEventListener("input", () => gameSetPlaying(G.playing));
  back.addEventListener("change", gameDraw);
  $("gameMain").replaceChildren(
    el("div", {className: "row"}, el("h2", {id: "skillTitle", textContent: skillTitle(s)}), el("span", {className: "muted", textContent: `sprite/character/${G.cls}/effect/${s.folder === "(根目录)" ? "" : s.folder + "/"} · ${s.imgs} 个 IMG`})),
    s.special ? el("div", {className: "small muted", textContent: "按文件名归到这个职业目录（男女都列出）。觉醒特写是放觉醒技能时弹出的职业特写（COLG 索引：使用觉醒时的职业特写）；人物立绘包括创建角色立绘、转职立绘、二次觉醒特写和 PK 场特写（后三种都是一张 IMG 里每个转职一帧、所有职业共用），以及冒险团的小头像动画。加 buff 时的变身外观在时装的 neck 部件 T 图层里，不是单独的立绘。"})
      : el("div", {className: "namebar"}, name, transfer, el("label", {className: "field"}, checked, "已核实"), save, status,
      el("span", {className: "small muted", textContent: s.source ? `来源：${s.source}` : "游戏数据里没有中文名，这里填的名字存在 kb/curated/skill_names.json"})),
    el("div", {className: s.mods.length ? "" : "muted", textContent: `改版：${modsText}`}),
    imgs,
    el("div", {className: "controls"}, play, button("上一帧", () => { gameSetPlaying(false); gameGo(G.k - 1); }), button("下一帧", () => { gameSetPlaying(false); gameGo(G.k + 1); }),
      el("label", {className: "field"}, "速度 ", fps, fpsText), el("label", {className: "field"}, "背景 ", back)),
    el("div", {className: "small muted", id: "ginfo"}),
    el("div", {className: "gstage", id: "gstage"}),
    el("p", {className: "small muted", textContent: "特效按普通叠加显示；游戏里很多光效是发光（加亮）叠加、速度也由技能脚本决定，这里只看形状和颜色。"}));
  const it = sk.items[G.item];
  if (it.still && it.frames > 1) {
    const pick = el("select", {id: "gframe", ariaLabel: "帧"}, ...Array.from({length: it.frames}, (_, k) => el("option", {value: k, textContent: `#${k}${it.labels[k] ? " " + it.labels[k] : ""}`})));
    pick.value = G.k;
    pick.addEventListener("change", () => gameGo(Number(pick.value)));
    $("gameMain").querySelector(".controls").append(el("label", {className: "field"}, "帧 ", pick));
  }
  gameLayout();
  gameSetPlaying(!it.still);
}

function gameSources() {
  const it = G.skill.items[G.item];
  const projects = new Map();
  for (const s of G.skills.find(x => x.folder === G.folder).mods) projects.set(s.project, s);
  const cols = [{label: "原版", src: "official", stamp: "o"}];
  for (const p of projects.values()) {
    const m = it.mods.find(x => x.project === p.project);
    cols.push(m ? {label: `${m.name} ${m.version}`, src: m.project, stamp: m.stamp} : {label: `${p.name}`, empty: "这个 IMG 没改，游戏里是原版"});
  }
  if (cols.length === 1) cols.push({label: "改版", empty: "暂无改版"});
  return cols;
}

function gameLayout() {
  const it = G.skill.items[G.item], [x0, y0, x1, y1] = it.box, w = x1 - x0, h = y1 - y0;
  const cols = gameSources();
  const room = Math.max(300, $("gameMain").clientWidth - 48), tall = Math.max(220, window.innerHeight - 380);
  const fit = Math.min((room - 14 * (cols.length - 1)) / cols.length / w, tall / h);
  G.zoom = fit >= 1 ? Math.min(6, Math.floor(fit)) : fit;
  const W = Math.max(40, Math.round(w * G.zoom)), H = Math.max(40, Math.round(h * G.zoom));
  $("gstage").replaceChildren(...cols.map(c => {
    if (c.empty) { const d = el("div", {className: "empty", textContent: c.empty}); d.style.width = `${W}px`; d.style.height = `${H}px`; return el("figure", {}, el("figcaption", {textContent: c.label}), d); }
    const canvas = el("canvas", {width: W, height: H});
    canvas.dataset.src = c.src; canvas.dataset.stamp = c.stamp;
    gameImage(it, c.src, c.stamp, gameDraw);
    return el("figure", {}, el("figcaption", {textContent: c.label}), canvas);
  }));
}

function gameDraw() {
  if (!G.skill || !$("gstage")) return;
  const it = G.skill.items[G.item], g = it.atlas, k = G.k;
  for (const canvas of $("gstage").querySelectorAll("canvas")) {
    const img = gameImage(it, canvas.dataset.src, canvas.dataset.stamp, gameDraw), ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = G.zoom < 1;
    ctx.fillStyle = $("gback")?.value || "#22282a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (img.complete && img.naturalWidth) {
      if (it.still) ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      else ctx.drawImage(img, (k % g.cols) * g.cw, Math.floor(k / g.cols) * g.ch, g.cw, g.ch, 0, 0, canvas.width, canvas.height);
    }
  }
  if ($("gframe")) $("gframe").value = k;
  $("ginfo").textContent = `${it.label}：第 ${k + 1} / ${it.frames} 帧${it.labels?.[k] ? "，" + it.labels[k] : ""}（${it.path}）`;
}

function gameGo(k) {
  const n = Math.max(1, G.skill.items[G.item].frames);
  G.k = (k + n) % n;
  gameDraw();
}

function gameSetPlaying(on) {
  G.playing = on; clearTimeout(G.timer);
  if ($("gplay")) $("gplay").textContent = on ? "暂停" : "播放";
  if ($("gfpsText")) $("gfpsText").textContent = `${$("gfps").value} 帧/秒`;
  if (!on) return;
  const tick = () => { G.timer = setTimeout(() => { if (!G.playing || !$("gstage")) return; gameGo(G.k + 1); tick(); }, 1000 / Number($("gfps").value)); };
  tick();
}

window.addEventListener("resize", () => { if (G.skill && $("gstage")) { gameLayout(); gameDraw(); } });
document.addEventListener("keydown", e => {
  if (!$("gstage") || e.target.matches("input, textarea, select")) return;
  if (e.key === " ") { e.preventDefault(); gameSetPlaying(!G.playing); }
  if (e.key === "ArrowLeft") { gameSetPlaying(false); gameGo(G.k - 1); }
  if (e.key === "ArrowRight") { gameSetPlaying(false); gameGo(G.k + 1); }
});


// Buff and rage videos live in the game's Video folder, not ImagePacks2. They are Neople-encrypted Bink 2, so they cannot be
// previewed; the page lists them and says whether each file is still the official one (sha256 against a recorded baseline).
async function renderVideos() {
  const v = await api(`/api/game/videos?${new URLSearchParams({cls: G.cls})}`);
  const STATE = {official: ["ok", "官方原版"], replaced: ["warn", "已被替换"], missing: ["bad", "文件不见了"]};
  const rows = v.rows.map(r => el("tr", {},
    el("td", {textContent: r.kind}),
    el("td", {}, el("b", {textContent: r.name || "—"})),
    el("td", {className: "small", textContent: r.file}),
    el("td", {textContent: `${Math.round(r.size / 1024)} KB`}),
    el("td", {}, el("span", {className: `badge ${STATE[r.status][0]}`, textContent: STATE[r.status][1]}))));
  $("gameMain").replaceChildren(
    el("div", {className: "row"}, el("h2", {textContent: "加 buff 和觉醒视频"}), el("span", {className: "muted", textContent: v.root})),
    el("p", {className: "small muted", textContent: "放 buff 时的人物立绘是视频，不在 ImagePacks2 里：Video\Character\Cutscene_buf（按转职），Cutscene_buf_add（时装专属），Cutscene_rage（觉醒）。文件是 Neople 加密的 Bink 2，暂时无法预览；替换方法是用同名文件覆盖，游戏更新后可能被复原。状态按 2026-11-09 记录的官方文件哈希判断。"}),
    el("div", {className: "tablewrap"}, el("table", {}, el("thead", {}, el("tr", {}, ...["类型", "转职", "文件", "大小", "状态"].map(h => el("th", {textContent: h})))), el("tbody", {}, ...rows))));
}
