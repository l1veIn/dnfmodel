"""Where each patch project stands, read from the files: versions, stages, review, install state and cost. Nothing here writes.

Projects are listed in design/projects.json. Everything else is derived, so the page never disagrees with the disk.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import issues

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "design"
OUTPUT = ROOT / "output"
DOCS = ROOT / "docs"
GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
REGISTRY = DESIGN / "projects.json"
# Dollars per image, measured from account balance differences (same table as the kit's sheets.py); an estimate, not a bill.
SHEET_COST = {"16:9": 0.22, "3:2": 0.29, "1:1": 0.39}
MASTER_COST = 0.24
VERSION = re.compile(r"_v(\d+)\.npk$", re.I)
_cache = {}


def registry():
    return json.loads(REGISTRY.read_text("utf-8"))["projects"]


def project(pid):
    for p in registry():
        if p["id"] == pid:
            return p
    raise KeyError(pid)


def _cached(key, path, compute):
    """Recompute only when the file changed."""
    stat = path.stat()
    token = (stat.st_size, stat.st_mtime)
    hit = _cache.get(key)
    if hit and hit[0] == token:
        return hit[1]
    value = compute()
    _cache[key] = (token, value)
    return value


def _find_ci(folder, name):
    """A file in folder whose name matches ignoring case (output folders and docs differ in case)."""
    if not folder.exists():
        return None
    low = name.lower()
    return next((p for p in folder.iterdir() if p.name.lower() == low), None)


def versions(p):
    """Every built NPK of the project, newest first. A copy in a retired or backup folder only counts when no other copy exists."""
    found = {}
    for path in list(OUTPUT.glob("*.NPK")) + list(OUTPUT.glob("*/*.NPK")) + list(OUTPUT.glob("*/*.npk")):
        if not any(path.name.lower().startswith(stem.lower()) for stem in p["npk"]):
            continue
        backup = any(w in path.parent.name.lower() for w in ("retired", "before"))
        old = found.get(path.name)
        if old and (old["backup"] <= backup):
            continue
        found[path.name] = dict(path=path, backup=backup)
    rows = []
    for name, item in found.items():
        path = item["path"]
        stat = path.stat()
        out = path.parent if path.parent != OUTPUT else None
        m = VERSION.search(name)
        label = name[:-4]
        for stem in p["npk"]:
            if label.lower().startswith(stem.lower()):
                label = label[len(stem):].strip("_") or label
        zip_path = _find_ci(OUTPUT, f"{out.name}.zip") if out else None
        doc = _find_ci(DOCS, f"{out.name}.md") if out else None
        preview = out / "preview" / "index.html" if out and (out / "preview" / "index.html").exists() else None
        game = GAME / name
        installed = None
        if game.exists():
            installed = "same" if game.stat().st_size == stat.st_size else "different"
        rows.append(dict(name=name, label=label, number=int(m.group(1)) if m else 0, size=stat.st_size, built=time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                         mtime=stat.st_mtime, path=str(path.relative_to(ROOT)), out=out.name if out else None, zip=str(zip_path.relative_to(ROOT)) if zip_path else None,
                         zip_size=zip_path.stat().st_size if zip_path else None, doc=doc.name if doc else None,
                         preview=str(preview.relative_to(OUTPUT)).replace("\\", "/") if preview else None, installed=installed, backup=item["backup"]))
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows


def game_patches():
    """Our A_*.NPK files in the game folder right now."""
    return sorted(p.name for p in GAME.glob("*.NPK") if not p.name.lower().startswith("sprite"))


def _design(design):
    path = DESIGN / design / "patch.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def _out(design, data):
    return OUTPUT / data.get("out", f"{design}_v{data['version']}")


def cost(design):
    data = _design(design)
    if not data:
        return dict(images=0, usd=0.0)
    journal_path = _out(design, data) / "parts" / "journal.json"
    if not journal_path.exists():
        return dict(images=0, usd=0.0)
    journal = json.loads(journal_path.read_text("utf-8"))
    usd = sum(MASTER_COST if e.get("resolution") == "1k" else SHEET_COST.get(e.get("size"), 0.39) for e in journal.values() if not e.get("exit"))
    return dict(images=len(journal), usd=round(usd, 2))


def gates(design):
    path = DESIGN / design / "workbench" / "gates.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def stages(design, built):
    """The skill's steps, each done, active or waiting, with a short reason. Built is the project's version list."""
    data = _design(design)
    if not data:
        return []
    run, out = DESIGN / design, _out(design, data)
    composites = ROOT / "materials" / data["materials"] / "reference_composite"
    raw = out / "parts" / "raw"
    sheets = json.loads((run / "pose_sheets.json").read_text("utf-8")) if (run / "pose_sheets.json").exists() else {}
    drawn = [name for name in sheets if raw.exists() and (any(raw.glob(f"poses_{name}_v*_0.png")) or sheets[name].get("hold"))]
    frames = len(list((out / "native_frames").glob("*.png"))) if (out / "native_frames").exists() else 0
    clips = json.loads((run / "clips.json").read_text("utf-8"))["clips"] if (run / "clips.json").exists() else []
    actions = list(dict.fromkeys(c.get("action", c["name"]) for c in clips))
    state = issues.replay(design)
    passed = sum(1 for a in actions if state["units"].get(f"character/{a}", {}).get("verdict") == "pass")
    mine = [i for i in state["issues"] if i["asset"] == "character"]
    open_, fixed = sum(1 for i in mine if i["status"] == "open"), sum(1 for i in mine if i["status"] == "fixed")
    npk = f"{data['npk_stem']}_v{data['version']:02d}.NPK"
    this = next((v for v in built if v["name"] == npk), None)
    newest = built[0] if built else None
    ingame = [g for g in gates(design) if g.get("gate") == "ingame"]
    newest_gate = next((g for g in reversed(gates(design)) if newest and g.get("version") == newest["name"]), None)
    rows = [
        ("摸底", True, f"{data['class']}/{data['equipment']}，主骨架 {data['frames']} 帧"),
        ("拆原版", (composites / "contact_all.png").exists() and bool(clips), f"{len(clips)} 段，{len(actions)} 个动作" if clips else "还没写 clips.json"),
        ("母版", (raw / data.get("master", "")).exists() if data.get("master") else False, data.get("master") or "未定稿"),
        ("动作表", bool(sheets) and len(drawn) == len(sheets), f"{len(drawn)} / {len(sheets)} 张" if sheets else "还没有表"),
        ("合成", frames >= data["frames"], f"{frames} / {data['frames']} 帧"),
        ("用户审核", bool(actions) and passed == len(actions) and not open_ and not fixed,
         f"通过 {passed} / {len(actions)} 个动作" + (f"，待修 {open_}" if open_ else "") + (f"，待复核 {fixed}" if fixed else "")),
        ("打包", this is not None or newest is not None,
         (f"最新 {newest['label']}，{newest['built']}" if newest else "还没打包") + ("" if this or not newest else f"（人物配置是 v{data['version']:02d}，还没按它打包）")),
        ("安装", bool(newest and newest["installed"] == "same"), ("游戏里是 " + ", ".join(v["label"] for v in built if v["installed"]) if any(v["installed"] for v in built) else "游戏目录里没有这个项目的补丁")),
        ("实机验证", bool(newest_gate and newest_gate["gate"] == "ingame"),
         (f"{newest['label']} {'实机通过' if newest_gate['gate'] == 'ingame' else '实机有问题'}（{newest_gate['t'][:10]}）" if newest_gate
          else f"{newest['label']} 还没实机验证" + (f"；上次验证的是 {ingame[-1]['version']}" if ingame else "") if newest else "还没打包")),
    ]
    out_rows, active_set = [], False
    for name, done, detail in rows:
        status = "done" if done else ("active" if not active_set else "todo")
        if not done and not active_set:
            active_set = True
        out_rows.append(dict(name=name, status=status, detail=detail))
    return out_rows


def cover(p):
    """The current design's master picture, if there is one."""
    data = _design(p["current"]) if p.get("current") else None
    if data and data.get("master"):
        path = _out(p["current"], data) / "parts" / "raw" / data["master"]
        if path.exists():
            return path
    return None


def review_counts(p):
    total = dict(open=0, fixed=0, verified=0)
    for design in p["designs"]:
        for i in issues.replay(design)["issues"]:
            if i["status"] in total:
                total[i["status"]] += 1
    return total


def summary(p):
    built = versions(p)
    newest = built[0] if built else None
    installed = [v for v in built if v["installed"]]
    st = stages(p["current"], built) if p.get("current") else []
    active = next((s for s in st if s["status"] == "active"), None)
    spent = sum(cost(d)["usd"] for d in p["designs"]) + sum(c["usd"] for c in p.get("costs", []))
    return dict(id=p["id"], name=p["name"], cls=p["class"], character=p["character"], summary=p.get("summary", ""), archived=p.get("archived", False),
                versions=len(built), newest=newest and dict(label=newest["label"], name=newest["name"], built=newest["built"], size=newest["size"]),
                installed=[dict(label=v["label"], state=v["installed"]) for v in installed], stage=active["name"] if active else ("完成" if st else None),
                stages=st, issues=review_counts(p), usd=round(spent, 2), cover=bool(cover(p)), current=p.get("current"))


def detail(p):
    built = versions(p)
    designs = []
    for d in p["designs"]:
        data = _design(d)
        if not data:
            continue
        extra = DESIGN / d / "workbench" / "assets.json"
        designs.append(dict(id=d, title=data.get("title"), version=data["version"], out=data.get("out"), npk_stem=data["npk_stem"], cost=cost(d),
                            assets=["character"] + ([a["id"] for a in json.loads(extra.read_text("utf-8"))["assets"]] if extra.exists() else []),
                            license=data.get("license_note", ""), issues=review_counts(dict(designs=[d]))))
    return dict(summary(p), versions=built, designs=designs, costs=p.get("costs", []), game=game_patches(),
                gates=gates(p["current"]) if p.get("current") else [])
