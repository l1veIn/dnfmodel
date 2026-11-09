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

import categories
import progress
import render

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "kb" / "kb.sqlite"
NAMES = ROOT / "kb" / "curated" / "skill_names.json"
ROOT_FOLDER = "(根目录)"
PORTRAITS = ROOT / "kb" / "curated" / "portraits.json"
# Pseudo folders listed first for every class: illustrations that live outside the class folder (categories.py).
SPECIAL = {"@buffart": ("buffart", "觉醒特写"), "@portrait": ("portrait", "人物立绘")}
VIDEO_FOLDER = "@buffvideo"
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


def professions(cls):
    con = db()
    names = [r[0] for r in con.execute("select name from profession where cls=?", (cls,))]
    con.close()
    return names


def special_paths(cls, key):
    return [p for p in categories.portrait_paths(professions(cls)) if categories.classify(p) == key]


def display(path):
    """(box covers the whole screen, atlas is scaled down, frames are separate stills) for an IMG."""
    kind = categories.classify(path)
    still = kind in ("buffart", "portrait") and "/adventurer2020/" not in path
    return kind == "cutin", kind == "cutin" or still, still


def frame_labels(path):
    data = json.loads(PORTRAITS.read_text("utf-8")) if PORTRAITS.exists() else {}
    return {int(k): v for k, v in data.get(path, {}).items()}


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


def index_names(cls):
    """Names for effect folders from the COLG ImagePacks2 index (kb table npk_note): folder -> name, transfer, source."""
    con = db()
    if not con.execute("select name from sqlite_master where name='npk_note'").fetchone():
        return {}
    out = {}
    prefix = f"sprite_character_{cls}_effect"
    for npk, note, transfer, heading in con.execute("select npk, note, transfer, heading from npk_note where npk like ? and note <> '' order by line", (f"{prefix}%",)):
        folder = npk[len(prefix) + 1:-4] if npk != f"{prefix}.npk" else ROOT_FOLDER
        entry = out.setdefault(folder, dict(name=note, transfer=transfer or "", checked=False, source=f"COLG ImagePacks2 索引（2026-09-21）{'，' + heading if heading else ''}"))
        if note not in entry["name"].split("；"):
            entry["name"] += f"；{note}"  # one pack can serve several skills (the index lists it twice)
    con.close()
    return out


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
    folders = dict(_cache[key])
    for special, (kind, label) in SPECIAL.items():
        paths = special_paths(cls, kind)
        if paths:
            folders[special] = dict(folder=special, imgs=len(paths), frames=0, paths=paths, label=label)
    vids = videos(cls)["rows"]
    if vids:
        folders[VIDEO_FOLDER] = dict(folder=VIDEO_FOLDER, imgs=len(vids), frames=0, paths=[], label="加 buff 和觉醒视频")
    changed = mods()
    labels = names().get("classes", {}).get(cls, {})
    index = index_names(cls)
    out = []
    for folder, f in sorted(folders.items(), key=lambda kv: (not kv[0].startswith("@"), kv[0])):
        touched = {}
        for path in f["paths"]:
            for m in changed.get(path, []):
                touched.setdefault(m["project"], dict(m, imgs=0))["imgs"] += 1
        meta = labels.get(folder, {})
        if meta.get("source") != "用户在工作台填写" and folder in index:
            meta = index[folder]  # the community index beats our own guesses, but never what the user typed
        if "label" in f:
            meta = dict(name=f["label"], checked=True, source="游戏界面文件（sprite/interface），按文件名归到职业")
        out.append(dict(folder=folder, special=folder.startswith("@"), imgs=f["imgs"], frames=f["frames"], name=meta.get("name", ""), transfer=meta.get("transfer", ""),
                        checked=meta.get("checked", False), source=meta.get("source", ""), note=meta.get("note", ""),
                        mods=[dict(project=m["project"], name=m["name"], version=m["version"], imgs=m["imgs"], archived=m["archived"]) for m in touched.values()]))
    return dict(cls=cls, skills=out)


def skill(cls, folder):
    """The IMGs of one effect folder, each with its box, atlas grid and the projects that replaced it."""
    if folder in SPECIAL:
        paths = special_paths(cls, SPECIAL[folder][0])
    else:
        folders = _cache.get(("skills", cls, KB.stat().st_mtime)) or (skills(cls) and _cache[("skills", cls, KB.stat().st_mtime)])
        if folder not in folders:
            raise KeyError(folder)
        paths = folders[folder]["paths"]
    changed = mods()
    mine = set(professions(cls))
    items = []
    for path in sorted(paths):
        official = render.official_npk(path)
        versions = changed.get(path, [])
        whole, scaled, still = display(path)
        box, count, _ = render.unit_box([official] + [m["npk"] for m in versions], path, whole)
        labels = frame_labels(path)
        start = min((k for k, v in labels.items() if v.get("profession") in mine), default=0)
        items.append(dict(path=path, label=path.rsplit("/", 1)[1][:-4], frames=count, box=box, screen=whole, still=still, start=start,
                          labels={k: v["label"] + ("" if v.get("checked") else "（推断）") for k, v in labels.items()},
                          atlas=render.layout(box[2] - box[0], box[3] - box[1], count, scaled),
                          mods=[dict(project=m["project"], name=m["name"], version=m["version"], stamp=int(Path(m["npk"]).stat().st_mtime)) for m in versions]))
    return dict(cls=cls, folder=folder, items=items)


def atlas(path, source):
    """Atlas of an IMG from the official NPK or from a project's newest build. The box is recomputed the same way skill() does."""
    official = render.official_npk(path)
    if official is None:
        raise KeyError(path)
    versions = mods().get(path, [])
    whole, scaled, _ = display(path)
    box, count, _ = render.unit_box([official] + [m["npk"] for m in versions], path, whole)
    if source == "official":
        npk = official
    else:
        m = next((m for m in versions if m["project"] == source), None)
        if m is None:
            raise KeyError(source)
        npk = m["npk"]
    return render.img_atlas(npk, path, tuple(box), count, scaled)


def frame(path, source, k):
    """One frame of a still IMG (portraits), cropped to the same box as its atlas would be. Stills are browsed one at a time."""
    official = render.official_npk(path)
    if official is None:
        raise KeyError(path)
    versions = mods().get(path, [])
    whole, _, _ = display(path)
    box, count, _ = render.unit_box([official] + [m["npk"] for m in versions], path, whole)
    if not 0 <= k < count:
        raise KeyError(k)
    npk = official if source == "official" else next((m["npk"] for m in versions if m["project"] == source), None)
    if npk is None:
        raise KeyError(source)
    key = f"frame|{render.token(npk)}|{path}|{tuple(box)}|{k}"
    return render.cached(key, lambda: render.webp(render.frame(npk, path, k, tuple(box))))


# ---------------------------------------------------------------- buff and rage videos (Video/Character, outside ImagePacks2)

VIDEOS = ROOT / "kb" / "curated" / "buff_videos.json"
VIDEO_ROOT = render.GAME.parent / "Video" / "Character"
# The two-digit prefix of buff and rage videos is the class and gender, as in the COLG list (03 is the male fighter's "figher").
VIDEO_PROFESSION = {"01": "swordman", "02": "swordman_at", "03": "fighter_at", "04": "fighter", "05": "gunner", "06": "gunner_at", "07": "mage_at",
                    "08": "mage", "09": "priest", "10": "priest_at", "11": "thief", "12": "knight", "14": "demoniclancer", "15": "gunblader", "16": "archer"}


def _video_hash(path):
    import hashlib
    st = path.stat()
    key = ("vhash", str(path), st.st_size, st.st_mtime)
    if key not in _cache:
        _cache[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _cache[key]


def videos(cls=None):
    """Buff, costume-buff and rage videos, with their status against the official baseline. Each is Neople-encrypted Bink 2,
    so there is no preview; replacing one means overwriting the file in the game's Video folder (and again after updates)."""
    data = json.loads(VIDEOS.read_text("utf-8")) if VIDEOS.exists() else {"files": []}
    mine = set(professions(cls)) if cls else None
    rows = []
    for f in data["files"]:
        prefix = f["file"][:2] if f["folder"] == "Cutscene_buf" else f["file"].split("_rage")[0][:2] if f["folder"] == "Cutscene_rage" else None
        prof = VIDEO_PROFESSION.get(prefix or "")
        if mine is not None and f["folder"] != "Cutscene_buf_add" and prof not in mine:
            continue
        if mine is not None and f["folder"] == "Cutscene_buf_add":
            continue  # costume buff videos are not tied to one class folder; listed in the "all" view
        path = VIDEO_ROOT / f["folder"] / f["file"]
        if not path.exists():
            status = "missing"
        else:
            status = "official" if path.stat().st_size == f["size"] and _video_hash(path) == f["sha256"] else "replaced"
        kind = {"Cutscene_buf": "加 buff", "Cutscene_buf_add": "时装专属加 buff", "Cutscene_rage": "觉醒（rage）"}[f["folder"]]
        plain = False
        if path.exists():
            with path.open("rb") as stream:
                plain = stream.read(3) in (b"BIK", b"KB2")
        rows.append(dict(folder=f["folder"], file=f["file"], name=f["name"], kind=kind, profession=prof, size=f["size"], baseline=data.get("baseline_date"), status=status, plain=plain))
    return dict(root=str(VIDEO_ROOT), rows=rows)


def video_preview(folder, file):
    """An animated WebP of a buff video, only for plain Bink files (the game's own are Neople-encrypted). Cached in kb/cache.

    Community buff patches ship plain Bink 1 with alpha (BIKi, e.g. 470x668, 19 frames at 15 fps) and the game plays them."""
    import subprocess
    import tempfile
    if folder not in ("Cutscene_buf", "Cutscene_buf_add", "Cutscene_rage") or "/" in file or "\\" in file or not file.endswith(".bk2"):
        raise KeyError(file)
    path = VIDEO_ROOT / folder / file
    if not path.exists():
        raise KeyError(file)
    with path.open("rb") as stream:
        head = stream.read(4)
    if head[:3] not in (b"BIK", b"KB2"):
        raise ValueError("encrypted")

    def build():
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "preview.webp"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf", "format=rgba", "-loop", "0", "-lossless", "1", str(out)], check=True, timeout=120)
            return out.read_bytes()
    return render.cached(f"video|{render.token(str(path))}", build)

