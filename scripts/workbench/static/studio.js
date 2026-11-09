"use strict";
// The fitting room: pick a class, dress each slot from the Avatar Studio catalog (or a whole set), add a weapon avatar, lay one of our
// patches on top, and play it in the game's layer order. Outfits save to design/wardrobe.json. Helpers ($, el, api, enc, button, toast) are in dash.js.
const SLOTS = [["skin", "皮肤"], ["hair", "头部"], ["cap", "帽子"], ["face", "脸部"], ["neck", "胸部"], ["coat", "上衣"], ["belt", "腰带"], ["pants", "下装"], ["shoes", "鞋子"], ["weapon", "武器"]];
const WEAPON_CN = {revolver: "左轮", automatic: "自动手枪", hcannon: "手炮", musket: "步枪", bowgun: "手弩", weapon: "其他"};
const T = {roles: [], role: null, info: null, outfit: {}, names: {}, overlay: "", plan: null, k: 0, start: 0, end: 0, playing: true, timer: null,
           images: new Map(), pick: "coat", weaponKind: "", tab: "items", query: "", wardrobe: [], current: {}, exports: []};

async function studioPage() {
  $("crumb").textContent = "/ 试衣间";
  document.title = "试衣间 · 补丁工作台";
  $("page").className = "page wide";
  if (!T.roles.length) T.roles = await api("/api/studio/roles");
  const w = await api("/api/studio/wardrobe");
  T.wardrobe = w.outfits; T.current = w.current || {};
  T.exports = await api("/api/studio/exports");
  const roleSel = el("select", {id: "stRole", ariaLabel: "职业"}, ...T.roles.map(r => el("option", {value: r.role, textContent: `${r.label}（${r.frames || "?"} 帧）`})));
  roleSel.addEventListener("change", () => setRole(roleSel.value, {}));
  $("page").replaceChildren(el("div", {className: "studio"},
    el("aside", {className: "stLeft"},
      el("div", {className: "row"}, roleSel, el("select", {id: "stOverlay", ariaLabel: "叠加补丁"})),
      el("ul", {id: "stSlots"}),
      el("div", {className: "stCurrent"}, el("div", {id: "stCurrentText", className: "small"}),
        el("div", {className: "row"}, button("把这套设为当前穿戴", setCurrent), button("穿上当前穿戴", wearCurrent))),
      el("div", {className: "stPicker"},
        el("div", {className: "row"}, el("b", {id: "stPickTitle"}), el("span", {className: "spacer"}),
          el("button", {type: "button", id: "stTabItems", textContent: "单件"}), el("button", {type: "button", id: "stTabSets", textContent: "套装"})),
        el("div", {className: "row"}, el("select", {id: "stWeaponKind", hidden: true}), el("input", {type: "search", id: "stQuery", placeholder: "搜名字、物品 ID 或代码"})),
        el("ul", {id: "stResults"}))),
    el("section", {className: "stMain"},
      el("div", {className: "row"}, el("h2", {id: "stTitle", textContent: "试衣间"}), el("span", {id: "stSub", className: "muted small"})),
      el("div", {className: "controls"},
        button("暂停", () => stPlay(!T.playing)), button("上一帧", () => { stPlay(false); stGo(T.k - 1); }), button("下一帧", () => { stPlay(false); stGo(T.k + 1); }),
        el("label", {className: "field"}, "动作 ", el("select", {id: "stAction"})),
        el("label", {className: "field"}, "帧 ", el("input", {type: "number", id: "stStart", min: 0, style: "width:64px"}), "–", el("input", {type: "number", id: "stEnd", min: 0, style: "width:64px"})),
        el("label", {className: "field"}, "速度 ", el("input", {type: "range", id: "stFps", min: 2, max: 30, value: 10})),
        el("label", {className: "field"}, "背景 ", el("select", {id: "stBack"}, ...[["#56617a", "灰蓝"], ["#22282a", "深色"], ["#c2c0ac", "浅色"]].map(([v, t]) => el("option", {value: v, textContent: t}))))),
      el("div", {id: "stStage"}, el("canvas", {id: "stCanvas", width: 10, height: 10})),
      el("div", {id: "stInfo", className: "small muted"})),
    el("aside", {className: "stRight"},
      el("section", {className: "card"}, el("h3", {textContent: "衣橱"}),
        el("div", {className: "row"}, el("input", {type: "text", id: "stSaveName", placeholder: "给这套起个名字"}), button("保存", saveOutfit)),
        el("ul", {id: "stWardrobe", className: "plain"})),
      el("section", {className: "card"}, el("h3", {textContent: "按当前穿戴导出补丁"}),
        el("p", {className: "small muted", textContent: "把左边这套（连同叠加的补丁）压成一张图，写进你游戏里当前穿着的那几件时装，其余几件和身体置空；武器保持原样。得到的小 NPK 只影响这几件。导出后会用它模拟游戏画面，和目标逐帧比对。"}),
        el("div", {id: "stExportPlan", className: "small"}),
        el("div", {className: "row"}, el("input", {type: "text", id: "stExportName", placeholder: "补丁名字（英文或拼音更好）"}), button("导出", exportOutfit)),
        el("ul", {id: "stExports", className: "plain small"})),
      el("section", {className: "card grow"}, el("h3", {textContent: "图层（从后到前）"}), el("ol", {id: "stLayers", className: "plain small"})))));
  $("stTabItems").addEventListener("click", () => { T.tab = "items"; renderPicker(); });
  $("stTabSets").addEventListener("click", () => { T.tab = "sets"; renderPicker(); });
  let typing;
  $("stQuery").addEventListener("input", () => { clearTimeout(typing); typing = setTimeout(() => { T.query = $("stQuery").value.trim(); renderPicker(); }, 250); });
  $("stWeaponKind").addEventListener("change", () => { T.weaponKind = $("stWeaponKind").value; renderPicker(); });
  $("stOverlay").addEventListener("change", () => { T.overlay = $("stOverlay").value; refresh(); });
  $("stAction").addEventListener("change", () => { const [a, b] = $("stAction").value.split("-").map(Number); setRange(a, b); });
  $("stStart").addEventListener("change", () => setRange(Number($("stStart").value), Number($("stEnd").value)));
  $("stEnd").addEventListener("change", () => setRange(Number($("stStart").value), Number($("stEnd").value)));
  $("stFps").addEventListener("input", () => stPlay(T.playing));
  $("stBack").addEventListener("change", stDraw);
  renderWardrobe();
  await setRole(T.role || "gunner_at", T.role ? T.outfit : null);
}

async function setRole(role, outfit) {
  T.role = role; $("stRole").value = role;
  T.info = await api(`/api/studio/role?${new URLSearchParams({role})}`);
  T.outfit = outfit || {...T.info.default};
  T.weaponKind = T.info.role.weapons.find(w => w !== "weapon") || T.info.role.weapons[0] || "";
  $("stOverlay").replaceChildren(...T.info.overlays.map(o => el("option", {value: o.id, textContent: o.label})));
  T.overlay = T.info.overlays.some(o => o.id === T.overlay) ? T.overlay : "";
  $("stOverlay").value = T.overlay;
  $("stWeaponKind").replaceChildren(...T.info.role.weapons.map(w => el("option", {value: w, textContent: WEAPON_CN[w] || w})));
  $("stWeaponKind").value = T.weaponKind;
  const n = T.info.role.frames || 1;
  $("stAction").replaceChildren(el("option", {value: `0-${n - 1}`, textContent: `全部 ${n} 帧`}), ...T.info.actions.map(a => el("option", {value: `${a.start}-${a.end}`, textContent: `${a.name}（${a.start + 1}–${a.end + 1}）`})));
  setRange(0, Math.min(n - 1, T.info.actions[0] ? T.info.actions[0].end : n - 1), true);
  $("stAction").value = T.info.actions[0] ? `${T.info.actions[0].start}-${T.info.actions[0].end}` : `0-${n - 1}`;
  await refresh();
  renderPicker(); renderCurrent(); renderExports();
}

function setRange(a, b, quiet) {
  const n = T.info.role.frames || 1;
  T.start = Math.max(0, Math.min(n - 1, a || 0)); T.end = Math.max(T.start, Math.min(n - 1, isNaN(b) ? n - 1 : b));
  $("stStart").value = T.start; $("stEnd").value = T.end;
  T.k = T.start;
  if (!quiet) { stDraw(); stPlay(true); }
}

async function refresh() {
  T.plan = await api("/api/studio/compose", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({role: T.role, outfit: T.outfit, overlay: T.overlay})});
  for (const l of T.plan.layers) if (l.item_id) T.names[l.item_id] = l.name;
  renderSlots(); renderLayers(); stLayout(); stPlay(true);
  if ($("stCurrentText")) renderCurrent();
  const patched = T.plan.layers.filter(l => l.patched).length;
  $("stSub").textContent = `${T.info.role.label} · ${T.plan.layers.length} 个图层` + (T.overlay ? `，${patched} 个来自补丁` : "") + (T.plan.hidden.length ? `，被隐藏：${T.plan.hidden.join("、")}` : "") + (T.plan.missing.length ? `，${T.plan.missing.length} 个 IMG 在本地找不到` : "");
}

function stAtlas() {
  const url = `/api/studio/atlas?${new URLSearchParams({role: T.role, outfit: JSON.stringify(T.outfit), overlay: T.overlay, v: T.plan.key})}`;
  if (!T.images.has(url)) { const img = new Image(); img.decoding = "async"; img.onload = stDraw; img.src = url; T.images.set(url, img); }
  return T.images.get(url);
}

function stLayout() {
  const [x0, y0, x1, y1] = T.plan.box, w = x1 - x0, h = y1 - y0;
  const room = Math.max(240, $("stStage").clientWidth - 8), tall = Math.max(240, window.innerHeight - 250);
  const fit = Math.min(room / w, tall / h);
  T.zoom = fit >= 1 ? Math.min(6, Math.floor(fit)) : fit;
  const c = $("stCanvas"); c.width = Math.round(w * T.zoom); c.height = Math.round(h * T.zoom);
  stAtlas(); stDraw();
}

function stDraw() {
  if (!T.plan || !$("stCanvas")) return;
  const g = T.plan.atlas, img = stAtlas(), c = $("stCanvas"), ctx = c.getContext("2d"), k = T.k;
  ctx.imageSmoothingEnabled = T.zoom < 1;
  ctx.fillStyle = $("stBack").value; ctx.fillRect(0, 0, c.width, c.height);
  if (img.complete && img.naturalWidth) ctx.drawImage(img, (k % g.cols) * g.cw, Math.floor(k / g.cols) * g.ch, g.cw, g.ch, 0, 0, c.width, c.height);
  else { ctx.fillStyle = "#ccc"; ctx.font = "14px sans-serif"; ctx.fillText("合成中…", 12, 24); }
  $("stInfo").textContent = `第 ${k + 1} / ${T.plan.frames} 帧（工具编号 ${k}）`;
}

function stGo(k) {
  const span = T.end - T.start + 1;
  T.k = T.start + ((k - T.start) % span + span) % span;
  stDraw();
}

function stPlay(on) {
  T.playing = on; clearTimeout(T.timer);
  const b = $("page").querySelector(".stMain .controls button"); if (b) b.textContent = on ? "暂停" : "播放";
  if (!on) return;
  const tick = () => { T.timer = setTimeout(() => { if (!T.playing || !$("stCanvas")) return; stGo(T.k + 1); tick(); }, 1000 / Number($("stFps").value)); };
  tick();
}

function renderSlots() {
  $("stSlots").replaceChildren(...SLOTS.map(([slot, label]) => {
    const id = T.outfit[slot], hidden = T.plan.hidden.includes(slot);
    const name = id ? (T.names[id] || id) : slot === "skin" ? "默认皮肤" : "（空）";
    const li = el("li", {className: slot === T.pick ? "on" : ""},
      el("span", {className: "slotname", textContent: label}),
      el("span", {className: `itemname${hidden ? " muted" : ""}`, title: id || "", textContent: name + (hidden ? "（被隐藏）" : "")}));
    li.addEventListener("click", () => { T.pick = slot; T.query = ""; $("stQuery").value = ""; T.tab = "items"; renderSlots(); renderPicker(); });
    if (id) {
      const x = el("button", {type: "button", className: "x", title: "脱下", textContent: "×"});
      x.addEventListener("click", e => { e.stopPropagation(); delete T.outfit[slot]; refresh(); });
      li.append(x);
    }
    return li;
  }));
}

async function renderPicker() {
  const slot = T.pick, label = SLOTS.find(s => s[0] === slot)[1];
  $("stPickTitle").textContent = T.tab === "sets" ? "套装" : `换${label}`;
  $("stTabItems").setAttribute("aria-pressed", String(T.tab === "items"));
  $("stTabSets").setAttribute("aria-pressed", String(T.tab === "sets"));
  $("stWeaponKind").hidden = !(slot === "weapon" && T.tab === "items");
  $("stResults").replaceChildren(el("li", {className: "muted small", textContent: "读取中…"}));
  if (T.tab === "sets") {
    const sets = await api(`/api/studio/sets?${new URLSearchParams({role: T.role, q: T.query})}`);
    $("stResults").replaceChildren(...(sets.length ? sets.map(s => {
      const li = el("li", {}, el("b", {textContent: s.name}), el("div", {className: "small muted", textContent: s.members.map(m => m.name).join("、")}));
      li.addEventListener("click", () => {
        for (const m of s.members) { const key = SLOTS.some(x => x[0] === m.slot) ? m.slot : "weapon"; T.outfit[key] = m.item_id; T.names[m.item_id] = m.name; }
        refresh();
      });
      return li;
    }) : [el("li", {className: "muted small", textContent: "没有找到套装"})]));
    return;
  }
  const kind = slot === "weapon" ? T.weaponKind : slot;
  const r = await api(`/api/studio/items?${new URLSearchParams({role: T.role, slot: kind, q: T.query})}`);
  $("stResults").replaceChildren(...(r.items.length ? r.items.map(i => {
    const li = el("li", {className: T.outfit[slot] === i.item_id ? "on" : ""}, el("span", {textContent: i.name}),
      el("span", {className: "small muted", textContent: ` ${i.code ?? ""}${i.hide.length ? " · 会隐藏 " + i.hide.join("") : ""}`}));
    li.title = `物品 ID ${i.item_id}`;
    li.addEventListener("click", () => { T.outfit[slot] = i.item_id; T.names[i.item_id] = i.name; refresh(); renderPicker(); });
    return li;
  }) : [el("li", {className: "muted small", textContent: "没有找到"})]), ...(r.more ? [el("li", {className: "muted small", textContent: "只显示前 60 个，换个关键词缩小范围"})] : []));
}

function renderLayers() {
  $("stLayers").replaceChildren(...T.plan.layers.map(l => el("li", {className: l.source ? "" : "bad", title: l.path},
    el("span", {className: "z", textContent: l.z}), ` ${l.tag} ${l.name}`, l.patched ? el("span", {className: "badge info", textContent: "补丁"}) : null, l.source ? null : el("span", {className: "badge bad", textContent: "缺"}))));
}

function renderWardrobe() {
  const mine = T.wardrobe.slice().reverse();
  $("stWardrobe").replaceChildren(...(mine.length ? mine.map(o => {
    const role = T.roles.find(r => r.role === o.role);
    const li = el("li", {}, el("b", {textContent: o.name}), el("span", {className: "small muted", textContent: ` ${role ? role.label : o.role} · ${o.saved}`}));
    const load = button("穿上", async () => { T.overlay = o.overlay || ""; await setRole(o.role, {...o.outfit}); });
    const del = button("删", async () => { if (!confirm(`删除“${o.name}”？`)) return; await api("/api/studio/wardrobe/delete", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: o.id})}); T.wardrobe = (await api("/api/studio/wardrobe")).outfits; renderWardrobe(); });
    li.append(el("div", {className: "row"}, load, del));
    return li;
  }) : [el("li", {className: "muted small", textContent: "还没有保存的搭配"})]));
}

async function saveOutfit() {
  const name = $("stSaveName").value.trim();
  if (!name) { toast("先给这套起个名字"); return; }
  try {
    await api("/api/studio/wardrobe/save", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name, role: T.role, outfit: T.outfit, overlay: T.overlay})});
    T.wardrobe = (await api("/api/studio/wardrobe")).outfits; renderWardrobe(); toast(`已保存“${name}”`); $("stSaveName").value = "";
  } catch (error) { toast(`没保存上：${error.message}`); }
}

window.addEventListener("resize", () => { if (T.plan && $("stCanvas")) stLayout(); });
document.addEventListener("keydown", e => {
  if (!$("stCanvas") || e.target.matches("input, textarea, select")) return;
  if (e.key === " ") { e.preventDefault(); stPlay(!T.playing); }
  if (e.key === "ArrowLeft") { stPlay(false); stGo(T.k - 1); }
  if (e.key === "ArrowRight") { stPlay(false); stGo(T.k + 1); }
});

const slotSummary = outfit => SLOTS.filter(([s]) => outfit[s]).map(([s, label]) => `${label}:${T.names[outfit[s]] || outfit[s]}`).join("，");

function renderCurrent() {
  const c = T.current[T.role];
  $("stCurrentText").textContent = c ? `当前穿戴（${c.saved}）：${slotSummary(c.outfit) || "空"}` : "还没设当前穿戴：在游戏里穿的是什么，就在左边穿成什么，再点“设为当前穿戴”。";
  const target = slotSummary(Object.fromEntries(Object.entries(T.outfit).filter(([k]) => k !== "weapon")));
  $("stExportPlan").textContent = c ? `目标：${target || "空"}${T.overlay ? "，叠加 " + $("stOverlay").selectedOptions[0].textContent : ""}` : "先设当前穿戴。";
}

async function setCurrent() {
  try {
    const r = await api("/api/studio/current", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({role: T.role, outfit: T.outfit})});
    T.current[T.role] = r; renderCurrent(); toast("已设为当前穿戴");
  } catch (error) { toast(`没设上：${error.message}`); }
}

async function wearCurrent() {
  const c = T.current[T.role];
  if (!c) { toast("还没设当前穿戴"); return; }
  T.overlay = ""; $("stOverlay").value = ""; T.outfit = {...c.outfit}; await refresh(); renderCurrent();
}

async function exportOutfit() {
  const c = T.current[T.role];
  if (!c) { toast("先设当前穿戴"); return; }
  const name = $("stExportName").value.trim() || "outfit";
  toast("导出中…");
  try {
    const r = await api("/api/studio/export", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({role: T.role, current: c.outfit, target: T.outfit, overlay: T.overlay, name})});
    T.exports = await api("/api/studio/exports"); renderExports();
    toast(`已导出 ${r.npk}，${Math.round(r.size / 1024)} KB，模拟画面和目标${r.check.worst_frame_share ? "最多差 " + (r.check.worst_frame_share * 100).toFixed(1) + "%" : "完全一致"}`);
  } catch (error) { toast(`导出失败：${error.message}`); }
}

function renderExports() {
  const mine = T.exports.filter(e => e.role === T.role);
  $("stExports").replaceChildren(...(mine.length ? mine.map(e => {
    const folder = e.folder.split("/").pop();
    const href = kind => `/api/studio/export_file?${new URLSearchParams({folder, kind})}`;
    const ok = !e.check.worst_frame_share;
    return el("li", {},
      el("b", {textContent: e.name}), el("span", {className: "muted", textContent: ` ${e.created.slice(5, 16)} · ${Math.round(e.size / 1024)} KB`}),
      el("div", {className: "muted", textContent: `载体 ${e.carrier.tag}（z ${e.carrier.z}），置空 ${e.blanked.length} 个；` + (ok ? "模拟和目标一致" : `模拟最多差 ${(e.check.worst_frame_share * 100).toFixed(1)}%`)}),
      el("div", {className: "row"}, el("a", {className: "button", href: href("npk"), textContent: "下载 NPK"}), el("a", {className: "button", href: href("preview"), target: "_blank", textContent: "预览图"}),
        button("文件夹", async () => { try { await api("/api/studio/reveal", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({folder})}); } catch (error) { toast(error.message); } })));
  }) : [el("li", {className: "muted", textContent: "这个职业还没导出过"})]));
}

