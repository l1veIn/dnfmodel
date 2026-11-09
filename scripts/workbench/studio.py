"""The fitting room: dress any class in any costume pieces and weapon from the Avatar Studio catalog, and see it move in the game's
own layer order, optionally with one of our patches (or what is installed in the game folder) on top.

Data comes from the resource library (kb/kb.sqlite tables as_item / as_layer / as_set, imported by scripts/dnf_kb.py) and the game's
NPKs. Saved outfits live in design/wardrobe.json (versioned). Nothing here writes to the game folder.
"""
from __future__ import annotations

import hashlib
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
META = ROOT / "kb" / "sources" / "avatar_studio" / "meta.json"
WARDROBE = ROOT / "design" / "wardrobe.json"
AVATAR_SLOTS = ("skin", "hair", "cap", "face", "neck", "coat", "belt", "pants", "shoes")
SLOT_CN = {"skin": "皮肤", "hair": "头部", "cap": "帽子", "face": "脸部", "neck": "胸部", "coat": "上衣", "belt": "腰带", "pants": "下装", "shoes": "鞋子", "weapon": "武器"}
EXTRA_LABELS = {"creator_mage": "缔造者", "demonic_swordman": "黑暗武士", "imperialknight": "帝国骑士"}
CODE = re.compile(r"_([a-z]+?)(\d{4,5})([a-z]?)\.img$")
lock = threading.Lock()
_cache = {}


def db():
    return sqlite3.connect(f"file:{KB}?mode=ro", uri=True)


def _memo(key, build):
    stamp = KB.stat().st_mtime
    hit = _cache.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    value = build()
    _cache[key] = (stamp, value)
    return value


# ---------------------------------------------------------------- roles, items, sets


def roles():
    def build():
        con = db()
        labels = dict(con.execute("select name, label from profession"))
        rows = []
        for (prof,) in con.execute("select distinct profession from as_item order by profession"):
            fam = family(prof, con)
            skin = default_skin(fam)
            frames = con.execute("select frames from img where path=? limit 1", (skin,)).fetchone() if skin else None
            weapons = [r[0] for r in con.execute("select distinct i.slot from as_item i where i.profession=? and i.slot not in (%s)" % ",".join("?" * len(AVATAR_SLOTS)),
                                                 (prof, *AVATAR_SLOTS))]
            rows.append(dict(role=prof, label=labels.get(prof) or EXTRA_LABELS.get(prof, prof), family=fam, skin=skin, frames=frames[0] if frames else None, weapons=sorted(weapons)))
        con.close()
        return rows
    return _memo("roles", build)


def family(prof, con=None):
    own = con or db()
    row = own.execute("select family from as_layer where profession=? and slot='coat' group by family order by count(*) desc limit 1", (prof,)).fetchone()
    if con is None:
        own.close()
    return row[0] if row else None


def default_skin(fam):
    if not META.exists() or not fam:
        return None
    for f in json.loads(META.read_text("utf-8"))["visual_families"]:
        if f["visual_family_key"] == fam:
            return "sprite/" + f["default_skin_img"].replace("\\", "/").lower()
    return None


def role(prof):
    r = next((x for x in roles() if x["role"] == prof), None)
    if r is None:
        raise KeyError(prof)
    return r


def _code(path):
    m = CODE.search(path)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (None, None, None)


def items(prof, slot, query="", offset=0, limit=60):
    """Costume pieces (or weapon avatars of one weapon kind) of a role, searchable by name, item id or IMG code; named items first."""
    fam = role(prof)["family"]
    con = db()
    sql = ("select i.item_id, i.name, i.hide, i.dye1, i.layers, min(l.path) from as_item i join as_layer l on l.item_id=i.item_id and l.profession=i.profession "
           "where i.profession=? and i.slot=? and l.family=?")
    args = [prof, slot, fam]
    if query:
        sql += " and (i.name like ? or i.item_id like ? or l.path like ?)"
        args += [f"%{query}%", f"{query}%", f"%{query}%"]
    sql += " group by i.item_id order by (i.name like '未知%'), i.name, i.item_id limit ? offset ?"
    rows = con.execute(sql, args + [limit + 1, offset]).fetchall()
    con.close()
    out = []
    for item_id, name, hide, dye, layer_count, path in rows[:limit]:
        _, code, _ = _code(path or "")
        out.append(dict(item_id=item_id, name=name, code=code, hide=json.loads(hide or "[]"), dye=bool(dye), layers=layer_count))
    return dict(items=out, more=len(rows) > limit, offset=offset)


def sets(prof, query="", limit=40):
    con = db()
    rows = con.execute("select set_id, name, source, member_ids, member_names from as_set where profession=? and name like ? group by name order by name limit ?",
                       (prof, f"%{query}%", limit)).fetchall()
    con.close()
    out = []
    for s, n, src, ids, names in rows:
        members = item_info(prof, json.loads(ids))
        out.append(dict(set_id=s, name=n, source=src, members=[dict(item_id=i, name=m["name"], slot=m["slot"]) for i, m in members.items()]))
    return out


def item_info(prof, item_ids):
    con = db()
    out = {}
    for item_id in item_ids:
        row = con.execute("select name, slot, hide from as_item where profession=? and item_id=?", (prof, item_id)).fetchone()
        if row:
            out[item_id] = dict(item_id=item_id, name=row[0], slot=row[1], hide=json.loads(row[2] or "[]"))
    con.close()
    return out


def default_outfit(prof):
    """The class's base pieces: the item of each slot whose IMGs are code 0000 (the skin is the family's default body)."""
    def build():
        fam = role(prof)["family"]
        con = db()
        out = {}
        for slot in AVATAR_SLOTS[1:]:
            for item_id, path in con.execute("select item_id, path from as_layer where profession=? and family=? and slot=? and path like ?",
                                             (prof, fam, slot, f"%{slot}0000_.img")):
                kind, code, _ = _code(path)
                if code == 0 and kind == slot:
                    out[slot] = item_id
                    break
        con.close()
        return out
    return _memo(("default", prof), build)


# ---------------------------------------------------------------- overlays: our patches


def overlays(prof):
    """What can be laid over the official pieces: the game folder's installed patches, or one project's newest build."""
    out = [dict(id="", label="官方原版")]
    installed = progress.game_patches()
    if installed:
        out.append(dict(id="installed", label=f"游戏目录里装着的补丁（{len(installed)} 个）"))
    for p in progress.registry():
        if p.get("profession") == prof:
            built = progress.versions(p)
            if built:
                out.append(dict(id=p["id"], label=f"{p['name']} {built[0]['label']}"))
    return out


def overlay_npks(overlay):
    if not overlay:
        return []
    if isinstance(overlay, list):  # explicit NPK paths, e.g. a freshly exported outfit patch on top of the installed ones
        return [str(x) for x in overlay]
    if overlay == "installed":
        return [str(render.GAME / n) for n in progress.game_patches()]
    built = progress.versions(progress.project(overlay))
    return [str(ROOT / built[0]["path"])] if built else []


def actions(prof):
    """Frame ranges by action, from a project of this class that has clips.json (frame numbers are the rig's slots)."""
    for p in progress.registry():
        if p.get("profession") == prof and p.get("current"):
            path = ROOT / "design" / p["current"] / "clips.json"
            if path.exists():
                groups = {}
                for c in json.loads(path.read_text("utf-8"))["clips"]:
                    name = c.get("action", c["name"])
                    a = groups.setdefault(name, [c["start"], c["end"]])
                    a[0], a[1] = min(a[0], c["start"]), max(a[1], c["end"])
                return [dict(name=n, start=a[0], end=a[1]) for n, a in sorted(groups.items(), key=lambda kv: kv[1][0])]
    return []


# ---------------------------------------------------------------- composing an outfit


def plan(prof, outfit, overlay=""):
    """The layers to draw for an outfit, back to front, each with the NPK it comes from. outfit: {slot: item_id}; slot 'weapon' holds a weapon avatar."""
    r = role(prof)
    fam = r["family"]
    chosen = {k: v for k, v in outfit.items() if v}
    info = item_info(prof, chosen.values())
    hidden = set()
    for item in info.values():
        for tag in item["hide"]:
            m = re.match(r"\[(\w+) avatar\]", tag)
            if m:
                hidden.add(m.group(1))
    con = db()
    layers = []
    for slot, item_id in chosen.items():
        if slot in hidden:
            continue
        for path, z, tag, palette, seq in con.execute("select path, z, tag, palette, seq from as_layer where profession=? and item_id=? and family=? order by seq",
                                                      (prof, item_id, fam)):
            layers.append(dict(slot=slot, item_id=item_id, name=info.get(item_id, {}).get("name", ""), path=path, z=z, tag=tag, palette=palette))
    con.close()
    if "skin" not in chosen and r["skin"]:
        layers.append(dict(slot="skin", item_id="", name="默认皮肤", path=r["skin"], z=0, tag="[skin]", palette=0))
    patches = overlay_npks(overlay)
    entries = [(npk, render.npk_entries(npk)) for npk in patches]
    for layer in layers:
        layer["source"] = next((npk for npk, e in entries if layer["path"] in e), None) or render.official_npk(layer["path"])
        layer["patched"] = bool(layer["source"]) and not Path(layer["source"]).name.lower().startswith("sprite")
    layers.sort(key=lambda l: l["z"])
    return dict(layers=layers, hidden=sorted(hidden), frames=r["frames"] or 1, missing=[l["path"] for l in layers if not l["source"]])


def _box(layers, frames):
    boxes = []
    for l in layers:
        if not l["source"]:
            continue
        img = render.load_img(l["source"], l["path"])
        for x, y, w, h, _, _ in render.geometry(img)[:frames]:
            if w > 1 and h > 1:
                boxes.append((x, y, x + w, y + h))
    if not boxes:
        return (0, 0, 8, 8)
    pad = render.PAD
    return (min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad, max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)


def compose(prof, outfit, overlay=""):
    """Plan plus box and atlas grid; the atlas itself is built (and cached on disk) by atlas()."""
    p = plan(prof, outfit, overlay)
    box = _box(p["layers"], p["frames"])
    grid = render.layout(box[2] - box[0], box[3] - box[1], p["frames"])
    key = "|".join(f"{l['path']}:{l['palette']}:{render.token(l['source'])}" for l in p["layers"])
    p.update(box=box, atlas=grid, key=hashlib.sha1(key.encode('utf-8')).hexdigest()[:16], name_key=key,
             broken={l["path"]: render.BROKEN[l["path"]] for l in p["layers"] if l["path"] in render.BROKEN})
    return p


def atlas(prof, outfit, overlay=""):
    p = compose(prof, outfit, overlay)
    box, n = tuple(p["box"]), p["frames"]

    def build():
        frames = []
        for k in range(n):
            canvas = render.Image.new("RGBA", (box[2] - box[0], box[3] - box[1]))
            for l in p["layers"]:
                if l["source"]:
                    canvas.alpha_composite(render.frame(l["source"], l["path"], k, box, l["palette"]))
            frames.append(canvas)
        return render.atlas(frames, p["atlas"])
    return render.cached(f"outfit|{p['name_key']}|{box}|{n}", build)


# ---------------------------------------------------------------- wardrobe


def wardrobe():
    return json.loads(WARDROBE.read_text("utf-8")) if WARDROBE.exists() else {"outfits": []}


def save_outfit(payload):
    name, prof, outfit = payload.get("name", "").strip(), payload.get("role"), payload.get("outfit", {})
    if not name or len(name) > 60 or not isinstance(outfit, dict) or len(outfit) > 12:
        raise ValueError("bad outfit")
    role(prof)
    if any(k not in AVATAR_SLOTS + ("weapon",) or not isinstance(v, str) or len(v) > 40 for k, v in outfit.items()):
        raise ValueError("bad slot")
    note = payload.get("note", "")
    if not isinstance(note, str) or len(note) > 500:
        raise ValueError("bad note")
    with lock:
        data = wardrobe()
        entry = dict(id=f"o{int(time.time() * 1000)}", name=name, role=prof, outfit=outfit, overlay=payload.get("overlay", "") or "", note=note,
                     saved=time.strftime("%Y-%m-%d %H:%M"))
        data["outfits"] = [o for o in data["outfits"] if not (o["name"] == name and o["role"] == prof)] + [entry]
        tmp = WARDROBE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(WARDROBE)
    return entry


def delete_outfit(payload):
    with lock:
        data = wardrobe()
        before = len(data["outfits"])
        data["outfits"] = [o for o in data["outfits"] if o["id"] != payload.get("id")]
        if len(data["outfits"]) == before:
            raise ValueError("unknown outfit")
        WARDROBE.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    return dict(deleted=payload.get("id"))


# ---------------------------------------------------------------- export by what is worn ("当前穿戴")

EXPORTS = ROOT / "output" / "outfits"
WEAPON_FRONT = 1500  # weapon layers above this depth are drawn in front of the body (revolver c 2790, katana a 2050)


def _frames(plan_, box, n):
    out = []
    for k in range(n):
        canvas = render.Image.new("RGBA", (box[2] - box[0], box[3] - box[1]))
        for l in plan_["layers"]:
            if l["source"]:
                canvas.alpha_composite(render.frame(l["source"], l["path"], k, box, l["palette"]))
        out.append(canvas)
    return out


def _slug(text):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return s[:40] or "outfit"


def _write_npk(entries):
    """An NPK with identical payloads stored once (all blank IMGs of one length share their bytes), like the patch kit's builds."""
    import hashlib as _h
    import struct
    from dnf_resources import NAME_KEY, NPK_MAGIC
    unique, payloads = {}, []
    offset = 52 + 264 * len(entries)
    header = bytearray(NPK_MAGIC + struct.pack("<I", len(entries)))
    for name, payload in entries:
        if payload not in unique:
            unique[payload] = offset
            payloads.append(payload)
            offset += len(payload)
        encoded = name.encode("utf-8")
        if len(encoded) >= 256:
            raise ValueError(f"IMG path too long: {name}")
        header.extend(struct.pack("<II", unique[payload], len(payload)))
        header.extend(bytes(a ^ b for a, b in zip(encoded.ljust(256, b"\0"), NAME_KEY)))
    return bytes(header) + _h.sha256(header[:len(header) // 17 * 17]).digest() + b"".join(payloads)


def export_outfit(payload):
    """Write the target look into the IMGs of what is worn now, as one small NPK, and check it against the target.

    current: {slot: item_id} actually worn in game (its weapon is kept as it is). target: {slot: item_id} plus an optional
    overlay (one of our projects). The target, without weapon, is flattened into one picture per rig frame and written into
    the carrier: the worn layer drawn highest while still behind the weapon's front layer. Every other worn layer, the body
    included, gets blank frames. Nothing is installed; the NPK goes to output/outfits/."""
    from dnf_resources import write_v2
    prof, current, target = payload["role"], payload.get("current") or {}, payload.get("target") or {}
    overlay, label = payload.get("overlay", "") or "", (payload.get("name") or "outfit").strip()[:40]
    if not isinstance(current, dict) or not isinstance(target, dict) or not current:
        raise ValueError("current and target outfits are required")
    r = role(prof)
    n = r["frames"]
    cur = plan(prof, current)
    worn = [l for l in cur["layers"] if l["slot"] != "weapon" and l["source"]]
    if not worn:
        raise ValueError("nothing worn to carry the look")
    front = [l["z"] for l in cur["layers"] if l["slot"] == "weapon" and l["z"] > WEAPON_FRONT]
    below = [l for l in worn if not front or l["z"] < min(front)]
    carrier = max(below or worn, key=lambda l: l["z"])
    look = compose(prof, {k: v for k, v in target.items() if k != "weapon"}, overlay)
    box = tuple(look["box"])
    frames = _frames(look, box, n)
    canvas_meta = render.load_img(carrier["source"], carrier["path"]).resolve(0)
    cw, ch = canvas_meta.get("canvas_width", 500), canvas_meta.get("canvas_height", 500)
    images, meta = [], []
    for image in frames:
        bbox = image.getbbox()
        if bbox is None:
            images.append(render.Image.new("RGBA", (1, 1)))
            meta.append(dict(x=0, y=0, canvas_width=cw, canvas_height=ch))
        else:
            images.append(image.crop(bbox))
            meta.append(dict(x=box[0] + bbox[0], y=box[1] + bbox[1], canvas_width=cw, canvas_height=ch))
    entries = {carrier["path"]: write_v2(images, meta)}
    blanks = {}
    for l in worn:
        if l["path"] in entries:
            continue
        count = len(render.load_img(l["source"], l["path"]).frames)
        if count not in blanks:
            blanks[count] = write_v2([render.Image.new("RGBA", (1, 1))] * count,
                                     [dict(x=0, y=0, canvas_width=cw, canvas_height=ch)] + [{"link": 0} for _ in range(count - 1)])
        entries[l["path"]] = blanks[count]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    folder = EXPORTS / f"{stamp}_{_slug(prof + '_' + label)}"
    folder.mkdir(parents=True, exist_ok=True)
    npk_name = f"A_Outfit_{_slug(prof)}_{stamp}.NPK"
    (folder / npk_name).write_bytes(_write_npk(sorted(entries.items())))
    # Check: what the game would draw for the worn outfit with this NPK on top, against the target. The weapon is left out of both.
    worn_only = {k: v for k, v in current.items() if k != "weapon"}
    seen = compose(prof, worn_only, [folder / npk_name])
    check = _frames(seen, box, n)
    import numpy as np
    worst, total = 0.0, 0.0
    for a, b in zip(frames, check):
        pa, pb = np.asarray(a).astype(int), np.asarray(b).astype(int)
        visible = pa[..., 3] > 8
        differing = (np.abs(pa[..., 3] - pb[..., 3]) > 8) | (visible & (np.abs(pa[..., :3] - pb[..., :3]).max(2) > 8))
        share = float(differing.sum()) / max(1, int(visible.sum()))
        worst, total = max(worst, share), total + share
    report = dict(role=prof, name=label, npk=npk_name, created=time.strftime("%Y-%m-%d %H:%M:%S"), frames=n, current=current, target=target, overlay=overlay,
                  carrier=dict(path=carrier["path"], tag=carrier["tag"], z=carrier["z"], item=carrier["name"]),
                  blanked=sorted(p for p in entries if p != carrier["path"]), size=(folder / npk_name).stat().st_size,
                  check=dict(worst_frame_share=round(worst, 4), mean_share=round(total / max(1, n), 4)),
                  weapon_front=front, installed_note="放进 ImagePacks2 后生效；A_Outfit_ 开头按文件名排在 A_Claude_ 等项目补丁之后，同一路径以它为准。")
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    sheet = render.atlas(frames, render.layout(box[2] - box[0], box[3] - box[1], n))
    (folder / "preview.webp").write_bytes(sheet)
    report["folder"] = str(folder.relative_to(ROOT)).replace("\\", "/")
    return report


def exports():
    out = []
    if EXPORTS.exists():
        for f in sorted(EXPORTS.glob("*/report.json"), reverse=True):
            r = json.loads(f.read_text("utf-8"))
            r["folder"] = str(f.parent.relative_to(ROOT)).replace("\\", "/")
            out.append(r)
    return out


def set_current(payload):
    """Remember what is actually worn in game for a class (the export's carrier), in design/wardrobe.json."""
    prof, outfit = payload.get("role"), payload.get("outfit", {})
    role(prof)
    if not isinstance(outfit, dict) or len(outfit) > 12 or any(k not in AVATAR_SLOTS + ("weapon",) or not isinstance(v, str) or len(v) > 40 for k, v in outfit.items()):
        raise ValueError("bad outfit")
    with lock:
        data = wardrobe()
        data.setdefault("current", {})[prof] = dict(outfit=outfit, saved=time.strftime("%Y-%m-%d %H:%M"))
        tmp = WARDROBE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(WARDROBE)
    return data["current"][prof]


def export_file(folder, kind):
    """A file of one export, only from output/outfits/<folder>/."""
    base = (EXPORTS / folder).resolve()
    if EXPORTS.resolve() not in base.parents or not (base / "report.json").exists():
        raise KeyError(folder)
    report = json.loads((base / "report.json").read_text("utf-8"))
    path = base / (report["npk"] if kind == "npk" else "preview.webp")
    if not path.exists():
        raise KeyError(kind)
    return path

