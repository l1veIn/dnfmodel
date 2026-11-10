"use strict";
// Dashboard and project pages. Everything shown is read from the files by the server; the only writes are in-game verification marks.
const $ = id => document.getElementById(id);
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids.filter(k => k !== null && k !== undefined)); return e; };
const mb = n => n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
const usd = n => `$${n.toFixed(2)}`;
const enc = encodeURIComponent;

async function api(path, options) {
  const r = await fetch(path, options);
  const body = await r.json().catch(() => ({error: `HTTP ${r.status}`}));
  if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
  return body;
}

function toast(text) {
  $("toast").textContent = text; $("toast").hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { $("toast").hidden = true; }, 4000);
}

function cover(p, big) {
  if (!p.cover) return el("div", {className: "cover none", textContent: "没有母版图"});
  const c = el("div", {className: "cover", role: "img", ariaLabel: `${p.name} 母版`});
  c.style.backgroundImage = `url("/api/projects/${enc(p.id)}/cover.png")`;
  if (big) c.style.backgroundSize = "contain";
  return c;
}

function installBadges(p) {
  const out = [];
  if (p.installed.length) for (const v of p.installed) out.push(el("span", {className: `badge ${v.state === "same" ? "ok" : "warn"}`, textContent: v.state === "same" ? `游戏里：${v.label}` : `游戏里：${v.label}（和本地不同）`}));
  else if (!p.archived) out.push(el("span", {className: "badge", textContent: "未安装"}));
  return out;
}

function issueBadges(i) {
  const out = [];
  if (i.open) out.push(el("span", {className: "badge bad", textContent: `待修 ${i.open}`}));
  if (i.fixed) out.push(el("span", {className: "badge warn", textContent: `待复核 ${i.fixed}`}));
  return out;
}

// ---------------------------------------------------------------- overview

async function overview(generation = dashboardRoute) {
  $("crumb").textContent = "";
  const data = await api("/api/dashboard");
  if (generation !== dashboardRoute) return;
  $("gameLine").textContent = data.game.length ? `游戏目录里的补丁：${data.game.join("、")}` : "游戏目录里没有补丁";
  const card = p => {
    const done = p.stages.filter(s => s.status === "done").length;
    const a = el("a", {className: `pcard${p.archived ? " archived" : ""}`, href: `#/p/${enc(p.id)}`},
      cover(p),
      el("div", {},
        el("h3", {textContent: p.name}),
        el("div", {className: "meta", textContent: `${p.cls} · ${p.character}` + (p.newest ? ` · 最新 ${p.newest.label}（${p.newest.built.slice(5)}）` : "")}),
        el("div", {className: "badges"}, ...installBadges(p), ...issueBadges(p.issues), p.buff_count ? el("span", {className: "badge info", textContent: `${p.buff_count} 个 buff 立绘`}) : null, p.usd ? el("span", {className: "badge", textContent: `花费约 ${usd(p.usd)}`}) : null),
        p.stages.length ? el("div", {className: "steps", title: p.stages.map(s => `${s.name}：${s.detail}`).join("\n")}, ...p.stages.map(s => el("i", {className: s.status}))) : null,
        el("div", {className: "next muted", textContent: p.archived ? "已归档" : p.stage === "完成" ? "全部完成" : p.stage ? `下一步：${p.stage}（${done}/${p.stages.length}）` : ""})));
    return a;
  };
  const live = data.projects.filter(p => !p.archived), old = data.projects.filter(p => p.archived);
  const page = [el("h1", {textContent: "补丁项目"}), el("p", {className: "lead", textContent: `${live.length} 个进行中的项目。进度、版本和安装状态都是从文件里读出来的，点进项目可以导出 NPK、用统一的对照台看原版和新版。`})];
  if (data.others.length) page.push(el("div", {className: "warnline", textContent: `游戏目录里还有不属于任何项目的补丁：${data.others.join("、")}`}));
  page.push(el("div", {className: "cards"}, ...live.map(card)));
  page.push(el("h2", {textContent: "替换范围（各项目最新版和游戏官方对比）"}), coverageMatrix(live));
  if (old.length) page.push(el("h2", {textContent: "已归档"}), el("div", {className: "cards"}, ...old.map(card)));
  page.push(el("p", {className: "small muted", textContent: "新建项目：在对话里告诉 Claude 要把哪个职业换成哪个角色，它会按 skill 建配置并登记到 design/projects.json。"}));
  $("page").replaceChildren(...page);
}

// ---------------------------------------------------------------- coverage: the same categories for every project

const SHARED = {awake: "职业目录合计，男女可能共用", effect: "职业目录合计，男女共用", cutin: "按文件名估计的本性别数量"};

function coverageCell(row, pid, design) {
  const td = el("td", {className: "cov"});
  if (!row.changed) {
    td.append(el("span", {className: "badge", textContent: "未改"}));
    td.title = `当前本地候选未包含${row.total ? `（官方 ${row.total} 个 IMG）` : ""}`;
    return td;
  }
  const full = row.total && row.changed >= row.total * 0.95;
  const text = row.total ? (full ? `全部 ${row.changed}` : `${row.changed} / ${row.total}`) : `${row.changed}`;
  const badge = el(design ? "a" : "span", {className: `badge ${full ? "ok" : "info"}`, textContent: `已改 ${text}`});
  if (design) badge.href = row.key === "portrait" ? portraitLink(pid) : `/review#${new URLSearchParams({p: design, a: row.key === "avatar" ? "character" : row.key})}`;
  td.append(badge);
  td.title = `${row.label}：新版有 ${row.changed} 个 IMG${row.total ? `，官方 ${row.total} 个` : ""}${SHARED[row.key] ? `（官方数量：${SHARED[row.key]}）` : ""}`;
  return td;
}

function coverageMatrix(projects) {
  const keys = [];
  for (const p of projects) for (const r of p.coverage?.rows || []) if (!keys.some(k => k.key === r.key)) keys.push({key: r.key, label: r.label});
  const head = el("tr", {}, el("th", {textContent: "项目"}), el("th", {textContent: "版本"}), ...keys.map(k => el("th", {textContent: k.label})));
  const rows = projects.filter(p => p.coverage).map(p => el("tr", {},
    el("td", {}, el("a", {href: `#/p/${enc(p.id)}`, textContent: p.name})),
    el("td", {textContent: p.coverage.version}),
    ...keys.map(k => { const r = p.coverage.rows.find(x => x.key === k.key); return r ? coverageCell(r, p.id, p.current) : el("td", {textContent: "—"}); })));
  return el("div", {}, el("div", {className: "tablewrap"}, el("table", {className: "matrix"}, el("thead", {}, head), el("tbody", {}, ...rows))),
    el("p", {className: "small muted", textContent: "“已改”点进去就是审核台里同一类的原版和新版对照。数量按 IMG 计；切入图、大招人物帧、技能特效的官方数量是职业目录里的合计，男女可能共用，只作参考。"}));
}

function coverageSection(p) {
  const c = p.coverage;
  if (!c) return [];
  const box = row => {
    const changed = row.changed > 0;
    const link = changed && p.current ? el("a", {className: "button", href: row.key === "portrait" ? portraitLink(p.id) : `/review#${new URLSearchParams({p: p.current, a: row.key === "avatar" ? "character" : row.key})}`, textContent: "看对照"}) : null;
    return el("div", {className: `box cov ${changed ? "changed" : "same"}`},
      el("h3", {textContent: row.label}),
      el("p", {className: changed ? "" : "muted", textContent: changed ? `已改 ${row.changed} 个 IMG` + (row.total ? `（官方 ${row.total} 个）` : "") : "当前本地候选未包含"}),
      changed && SHARED[row.key] && row.total ? el("p", {className: "small muted", textContent: `官方数量是${SHARED[row.key]}`}) : null,
      link ? el("div", {className: "actions"}, link) : null);
  };
  return [el("h2", {textContent: `改了什么（${c.version} 和游戏官方对比）`}), el("div", {className: "grid4"}, ...c.rows.map(box))];
}

const PORTRAIT_CLASS = {claude: "gunner", dragon: "swordman", whale: "mage"};
function portraitLink(pid) { return `#/game/${enc(PORTRAIT_CLASS[pid] || pid)}/${enc("@portrait")}`; }

function addonProjectSection(p) {
  if (!(p.addons || []).length) return [];
  return [el("h2", {textContent: "共享界面附加包"}), ...p.addons.map(a => el("div", {className: "box"},
    el("h3", {textContent: a.label}),
    el("p", {textContent: `${a.status} · 本项目 ${a.paths.length} 个界面 IMG`}),
    el("p", {className: "small muted", textContent: "与人物 NPK 一起使用；三个角色的共用图集已合并，不覆盖已通过的人物动作。"}),
    el("div", {className: "actions"},
      el("a", {className: "button", href: `/api/projects/${enc(p.id)}/addon-download?${new URLSearchParams({id: a.id})}`, textContent: `导出附加 NPK（${mb(a.size)}）`}),
      el("a", {className: "button", href: portraitLink(p.id), textContent: "查看人物立绘"}))))];
}

// ---------------------------------------------------------------- project page

async function projectPage(pid, generation = dashboardRoute) {
  const p = await api(`/api/projects/${enc(pid)}`);
  if (generation !== dashboardRoute) return;
  $("crumb").textContent = `/ ${p.name}`;
  document.title = `${p.name} · 补丁工作台`;
  const newest = p.versions[0];
  const current = p.designs.find(d => d.id === p.current);
  const actions = el("div", {className: "actions"});
  if (current) actions.append(el("a", {className: "button primary", href: `/review#${new URLSearchParams({p: current.id})}`, textContent: "对照和审核"}));
  if (newest) {
    actions.append(el("a", {className: "button", href: download(p.id, newest.name, "npk"), textContent: `导出最新 NPK（${newest.label}，${mb(newest.size)}）`}));
    if (newest.zip) actions.append(el("a", {className: "button", href: download(p.id, newest.name, "zip"), textContent: "下载发布包"}));
    actions.append(button("在文件夹中显示", () => reveal(p.id, newest.name, "npk")));
    if (newest.doc) actions.append(button("说明", () => showDoc(p.id, newest.doc)));
  }
  const hero = el("div", {className: "hero"}, cover(p, true), el("div", {},
    el("h1", {textContent: p.name}),
    el("div", {className: "meta muted", textContent: `${p.cls} · ${p.character}` + (p.archived ? " · 已归档" : "")}),
    el("p", {textContent: p.summary}),
    el("div", {className: "badges"}, ...installBadges(p), ...issueBadges(p.issues), p.issues.verified ? el("span", {className: "badge ok", textContent: `已复核 ${p.issues.verified}`}) : null),
    actions));
  const page = [hero];
  const sameName = p.game.filter(n => !p.versions.some(v => v.name === n) && p.versions.some(v => n.split("_v")[0] === v.name.split("_v")[0]));
  if (sameName.length) page.push(el("div", {className: "warnline", textContent: `游戏目录里有这个项目的补丁，但本地 output 里找不到同名文件：${sameName.join("、")}`}));

  page.push(...buffProjectSection(p));
  page.push(...addonProjectSection(p));
  page.push(...coverageSection(p));
  if (p.stages.length) {
    page.push(el("h2", {textContent: "进度"}), el("ol", {className: "stepper"}, ...p.stages.map(s => el("li", {className: s.status},
      el("span", {className: "st", textContent: s.status === "done" ? "完成" : s.status === "active" ? "进行中" : "未开始"}), el("b", {textContent: s.name}), el("span", {textContent: s.detail})))));
  }

  page.push(el("h2", {textContent: `版本（${p.versions.length}）`}));
  if (p.versions.length) {
    const rows = p.versions.map(v => {
      const state = v.installed === "same" ? el("span", {className: "badge ok", textContent: "游戏里"}) : v.installed ? el("span", {className: "badge warn", textContent: "游戏里（内容不同）"}) : null;
      const gate = [...p.gates].reverse().find(g => g.version === v.name);
      const ops = el("div", {className: "row"},
        el("a", {className: "button", href: download(p.id, v.name, "npk"), textContent: "导出 NPK"}),
        v.zip ? el("a", {className: "button", href: download(p.id, v.name, "zip"), textContent: `发布包 ${mb(v.zip_size)}`}) : null,
        v.preview ? el("a", {className: "button", href: `/output/${v.preview}`, target: "_blank", title: "打包时生成的静态页，各版本格式不同；统一对照请用“对照和审核”", textContent: "当时的对照页"}) : null,
        v.doc ? button("说明", () => showDoc(p.id, v.doc)) : null,
        button("文件夹", () => reveal(p.id, v.name, "npk")),
        p.current ? button("记实机结果", () => gateDialog(p, v)) : null);
      return el("tr", {},
        el("td", {}, el("b", {textContent: v.label}), el("div", {className: "small muted", textContent: v.name})),
        el("td", {textContent: v.built}),
        el("td", {textContent: mb(v.size)}),
        el("td", {}, state, gate ? el("span", {className: `badge ${gate.gate === "ingame" ? "ok" : "bad"}`, title: gate.note || "", textContent: gate.gate === "ingame" ? "实机通过" : "实机有问题"}) : null,
          v.backup ? el("span", {className: "badge", textContent: "只在备份目录"}) : null),
        el("td", {}, ops));
    });
    page.push(el("div", {className: "tablewrap"}, el("table", {}, el("thead", {}, el("tr", {}, ...["版本", "构建时间", "大小", "状态", "操作"].map(t => el("th", {textContent: t})))), el("tbody", {}, ...rows))));
  } else page.push(el("p", {className: "muted", textContent: "还没有打包。"}));

  if (p.designs.length) {
    page.push(el("h2", {textContent: "配置和审核"}));
    page.push(el("div", {className: "grid2"}, ...p.designs.map(d => el("div", {className: "box"},
      el("h3", {textContent: `${d.id}${d.id === p.current ? "（当前）" : ""}`}),
      el("dl", {className: "kv"},
        el("dt", {textContent: "配置版本"}), el("dd", {textContent: `v${String(d.version).padStart(2, "0")}，产物目录 ${d.out}`}),
        el("dt", {textContent: "问题"}), el("dd", {textContent: `待修 ${d.issues.open}，待复核 ${d.issues.fixed}，已复核 ${d.issues.verified}`}),
        el("dt", {textContent: "人物生图"}), el("dd", {textContent: d.cost.images ? `${d.cost.images} 次，约 ${usd(d.cost.usd)}` : "没有记录"})),
      el("div", {className: "actions"}, el("a", {className: "button", href: `/review#${new URLSearchParams({p: d.id})}`, textContent: "审核这份配置"}))))));
    const license = p.designs.find(d => d.id === p.current)?.license;
    if (license) page.push(el("h2", {textContent: "形象来源和授权"}), el("p", {className: "box", textContent: license}));
  }

  const costRows = [...p.designs.filter(d => d.cost.images).map(d => [`${d.id} 人物生图（${d.cost.images} 次）`, d.cost.usd]), ...p.costs.map(c => [c.label, c.usd])];
  if (costRows.length) {
    page.push(el("h2", {textContent: `花费（约 ${usd(p.usd)}）`}),
      el("div", {className: "tablewrap"}, el("table", {}, el("tbody", {}, ...costRows.map(([label, n]) => el("tr", {}, el("td", {textContent: label}), el("td", {textContent: usd(n)})))))),
      el("p", {className: "small muted", textContent: "人物生图按 journal 里的次数和实测单价估算；其他条目来自各版本说明。账户是共用的，这不是账单。"}));
  }
  if (p.gates.length) {
    page.push(el("h2", {textContent: "实机记录"}), el("ul", {}, ...[...p.gates].reverse().map(g => el("li", {textContent: `${g.t}  ${g.version}  ${g.gate === "ingame" ? "实机通过" : "实机有问题"}${g.note ? "：" + g.note : ""}`}))));
  }
  $("page").replaceChildren(...page);
}

const download = (pid, name, kind) => `/api/projects/${enc(pid)}/download?${new URLSearchParams({name, kind})}`;

function button(text, onClick) {
  const b = el("button", {type: "button", textContent: text});
  b.addEventListener("click", onClick);
  return b;
}

async function reveal(pid, name, kind) {
  try { const r = await api(`/api/projects/${enc(pid)}/reveal`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name, kind})}); toast(`已在资源管理器中打开：${r.opened}`); }
  catch (error) { toast(`打不开：${error.message}`); }
}

function gateDialog(p, v) {
  const choice = name => el("label", {className: "field"}, el("input", {type: "radio", name: "gate", value: name, checked: name === "ingame"}), name === "ingame" ? "实机通过" : "实机有问题");
  const note = el("textarea", {placeholder: "在哪里看的、哪里不对（有问题时必填）"});
  const status = el("span", {className: "small muted"});
  const save = button("记录", async () => {
    const gate = document.querySelector('input[name="gate"]:checked').value;
    if (gate === "ingame_failed" && !note.value.trim()) { status.textContent = "写一句哪里不对"; return; }
    try {
      await api(`/api/projects/${enc(p.id)}/gate`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({version: v.name, gate, note: note.value.trim()})});
      $("docOverlay").hidden = true; toast("已记录"); route();
    } catch (error) { status.textContent = `没记上：${error.message}`; }
  });
  save.className = "primary";
  $("docTitle").textContent = `记实机结果 · ${v.name}`;
  $("docBody").replaceChildren(el("p", {className: "muted", textContent: "进游戏看过之后在这里记一笔。记录存在当前配置的 workbench/gates.jsonl。"}),
    el("div", {className: "row"}, choice("ingame"), choice("ingame_failed")), note, el("div", {className: "row"}, save, status));
  $("docOverlay").hidden = false;
  note.focus();
}

// ---------------------------------------------------------------- docs (a small Markdown reader: headings, lists, tables, code, bold, links)

function inline(text) {
  const frag = document.createDocumentFragment();
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    frag.append(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("`")) frag.append(el("code", {textContent: t.slice(1, -1)}));
    else if (t.startsWith("**")) frag.append(el("strong", {textContent: t.slice(2, -2)}));
    else frag.append(el("span", {textContent: t.slice(1, t.indexOf("]")), title: t.slice(t.indexOf("(") + 1, -1)}));
    last = m.index + t.length;
  }
  frag.append(text.slice(last));
  return frag;
}

function markdown(src) {
  const lines = src.replace(/\r/g, "").split("\n"), out = [];
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const code = []; i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++; out.push(el("pre", {}, el("code", {textContent: code.join("\n")}))); continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) { out.push(el(`h${h[1].length}`, {}, inline(h[2]))); i++; continue; }
    if (line.trim().startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++]);
      const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const body = rows.filter((r, k) => !(k === 1 && /^[\s|:-]+$/.test(r)));
      out.push(el("div", {className: "tablewrap"}, el("table", {}, el("thead", {}, el("tr", {}, ...cells(body[0]).map(c => el("th", {}, inline(c))))),
        el("tbody", {}, ...body.slice(1).map(r => el("tr", {}, ...cells(r).map(c => el("td", {}, inline(c))))))))); continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line), list = el(ordered ? "ol" : "ul");
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) list.append(el("li", {}, inline(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ""))));
      out.push(list); continue;
    }
    if (!line.trim()) { i++; continue; }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#|```|\s*\||\s*([-*]|\d+\.)\s)/.test(lines[i])) para.push(lines[i++]);
    out.push(el("p", {}, inline(para.join(" "))));
  }
  return out;
}

async function showDoc(pid, name) {
  const r = await fetch(`/api/projects/${enc(pid)}/doc?${new URLSearchParams({name})}`);
  if (!r.ok) { toast("读不到说明"); return; }
  $("docTitle").textContent = name;
  $("docBody").replaceChildren(...markdown(await r.text()));
  $("docOverlay").hidden = false;
}

// ---------------------------------------------------------------- routing

let dashboardRoute = 0;

async function route() {
  const generation = ++dashboardRoute;
  buffDisposeAll();
  const m = location.hash.match(/^#\/p\/([^/]+)/), g = location.hash.match(/^#\/game(?:\/([^/]+))?(?:\/(.+))?/);
  const buff = location.hash.match(/^#\/p\/([^/]+)\/buff\/([^/?]+)\/?$/);
  const st = /^#\/studio/.test(location.hash);
  $("navProjects").classList.toggle("on", !g && !st);
  $("navGame").classList.toggle("on", !!g);
  $("navStudio").classList.toggle("on", st);
  try {
    if (st) { G.skill = null; return await studioPage(); }
    if (g) return await gamePage(g[1] && decodeURIComponent(g[1]), g[2] && decodeURIComponent(g[2]));
    $("page").className = "page";
    G.skill = null; clearTimeout(G.timer);
    if (buff) await buffPage(decodeURIComponent(buff[1]), decodeURIComponent(buff[2]), generation);
    else if (m) await projectPage(decodeURIComponent(m[1]), generation);
    else { document.title = "补丁工作台"; await overview(generation); }
  } catch (error) {
    if (generation !== dashboardRoute) return;
    $("page").replaceChildren(el("h1", {textContent: "读取失败"}), el("p", {className: "muted", textContent: error.message}), el("a", {href: "#/", textContent: "回到项目列表"}));
  }
}

$("refresh").addEventListener("click", route);
$("docClose").addEventListener("click", () => { $("docOverlay").hidden = true; });
$("docOverlay").addEventListener("click", e => { if (e.target === $("docOverlay")) $("docOverlay").hidden = true; });
document.addEventListener("keydown", e => { if (e.key === "Escape") $("docOverlay").hidden = true; });
window.addEventListener("hashchange", route);
route();
