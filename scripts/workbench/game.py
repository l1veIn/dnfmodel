"""Browse the game's own skill effects, class by class, and see which projects changed each one. Read from the resource library.

A "skill" here is an effect folder: sprite/character/<class>/effect/<folder>/. The game does not tell us skill names (Script.pvf is
encrypted), so Chinese names live in kb/curated/skill_names.json, seeded from what we know and edited from the page.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

import progress
import render

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "kb" / "kb.sqlite"
NAMES = ROOT / "kb" / "curated" / "skill_names.json"
ROOT_FOLDER = "(根目录)"
lock = threading.Lock()
_cache = {}


def db():
    return sqlite3.connect(f"file:{KB}?mode=ro", uri=True)


def names():
    return json.loads(NAMES.read_text("utf-8")) if NAMES.exists() else {"classes": {}}


def save_name(payload):
    cls, folder = payload.get("cls"), payload.get("folder")
    fields = {k: payload.get(k, "") for k in ("name", "transfer", "note")}
    if not re.fullmatch(r"[a-z0-9_]+", cls or "") or not isinstance(folder, str) or not folder or len(folder) > 120:
        raise ValueError("bad folder")
    if any(not isinstance(v, str) or len(v) > 200 for v in fields.values()):
        raise ValueError("bad text")
    if folder not in {f["folder"] for f in skills(cls)["skills"]}:
        raise ValueError("unknown folder")
    with lock:
        data = names()
        entry = data.setdefault("classes", {}).setdefault(cls, {}).setdefault(folder, {})
        entry.update({k: v.strip() for k, v in fields.items()}, checked=bool(payload.get("checked")), source="用户在工作台填写", edited=time.strftime("%Y-%m-%d %H:%M"))
        NAMES.parent.mkdir(parents=True, exist_ok=True)
        tmp = NAMES.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(NAMES)
    return entry


def mods():
    """{img path: [(project id, project name, version label, npk path)]} over every project's newest build. Kept for 20 seconds:
    every atlas request needs it, and listing the builds walks output/."""
    hit = _cache.get("mods")
    if hit and time.monotonic() - hit[0] < 20:
        return hit[1]
    out = _mods()
    _cache["mods"] = (time.monotonic(), out)
    return out


def _mods():
    out = {}
    for p in progress.registry():
        built = progress.versions(p)
        if not built:
            continue
        v = built[0]
        npk = ROOT / v["path"]
        for path in progress.npk_paths(npk):
            out.setdefault(path, []).append(dict(project=p["id"], name=p["name"], version=v["label"], npk=str(npk), archived=p.get("archived", False)))
    return out


def classes():
    """Class folders that have effects, with the professions (genders) that use each one."""
    con = db()
    rows = con.execute("select substr(path, 18, instr(substr(path, 18), '/') - 1) as cls, count(*) from img "
                       "where path like 'sprite/character/%/effect/%' and npk in (select id from npk where lower(name) like 'sprite%') group by cls order by cls").fetchall()
    prof = {}
    for name, label, cls in con.execute("select name, label, cls from profession"):
        prof.setdefault(cls, []).append(label)
    con.close()
    return [dict(cls=c, imgs=n, labels=prof.get(c, [])) for c, n in rows if c not in ("common", "character")]


def skills(cls):
    """Every effect folder of a class, with IMG counts, names and which projects changed it."""
    key = ("skills", cls, KB.stat().st_mtime)
    if key not in _cache:
        con = db()
        rows = con.execute("select path, frames from img where path like ? and npk in (select id from npk where lower(name) like 'sprite%')",
                           (f"sprite/character/{cls}/effect/%",)).fetchall()
        con.close()
        folders = {}
        for path, frames in rows:
            rest = path[len(f"sprite/character/{cls}/effect/"):]
            folder = rest.split("/", 1)[0] if "/" in rest else ROOT_FOLDER
            f = folders.setdefault(folder, dict(folder=folder, imgs=0, frames=0, paths=[]))
            f["imgs"] += 1
            f["frames"] += frames or 0
            f["paths"].append(path)
        _cache[key] = folders
    folders = _cache[key]
    changed = mods()
    labels = names().get("classes", {}).get(cls, {})
    out = []
    for folder, f in sorted(folders.items()):
        touched = {}
        for path in f["paths"]:
            for m in changed.get(path, []):
                touched.setdefault(m["project"], dict(m, imgs=0))["imgs"] += 1
        meta = labels.get(folder, {})
        out.append(dict(folder=folder, imgs=f["imgs"], frames=f["frames"], name=meta.get("name", ""), transfer=meta.get("transfer", ""),
                        checked=meta.get("checked", False), source=meta.get("source", ""), note=meta.get("note", ""),
                        mods=[dict(project=m["project"], name=m["name"], version=m["version"], imgs=m["imgs"], archived=m["archived"]) for m in touched.values()]))
    return dict(cls=cls, skills=out)


def skill(cls, folder):
    """The IMGs of one effect folder, each with its box, atlas grid and the projects that replaced it."""
    folders = _cache.get(("skills", cls, KB.stat().st_mtime)) or (skills(cls) and _cache[("skills", cls, KB.stat().st_mtime)])
    f = folders.get(folder)
    if f is None:
        raise KeyError(folder)
    changed = mods()
    screen = folder == "cutin"
    items = []
    for path in sorted(f["paths"]):
        official = render.official_npk(path)
        versions = changed.get(path, [])
        box, count, _ = render.unit_box([official] + [m["npk"] for m in versions], path, screen)
        items.append(dict(path=path, label=path.rsplit("/", 1)[1][:-4], frames=count, box=box, screen=screen,
                          atlas=render.layout(box[2] - box[0], box[3] - box[1], count, screen),
                          mods=[dict(project=m["project"], name=m["name"], version=m["version"], stamp=int(Path(m["npk"]).stat().st_mtime)) for m in versions]))
    return dict(cls=cls, folder=folder, items=items)


def atlas(path, source):
    """Atlas of an IMG from the official NPK or from a project's newest build. The box is recomputed the same way skill() does."""
    official = render.official_npk(path)
    if official is None:
        raise KeyError(path)
    versions = mods().get(path, [])
    screen = "/effect/cutin/" in path
    box, count, _ = render.unit_box([official] + [m["npk"] for m in versions], path, screen)
    if source == "official":
        npk = official
    else:
        m = next((m for m in versions if m["project"] == source), None)
        if m is None:
            raise KeyError(source)
        npk = m["npk"]
    return render.img_atlas(npk, path, tuple(box), count, screen)
