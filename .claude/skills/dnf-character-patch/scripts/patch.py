"""DNF whole-figure character patch tool. Run with the ComfyUI venv python, which has av and scipy.

  patch.py survey <class> <equipment>                 what the game has for this class
  patch.py init <id> <class> <equipment> <prefix> [--weapon=kind] [--stem=NPK_STEM]
  patch.py <id> composites                            source frames and contact sheet, then write clips.json
  patch.py <id> measure | master-refs | master-draw <name> | master-edit <name> <from> | small <names...>
  patch.py <id> sheet-refs <sheet> | sheet-draw <sheet> [--version=N] | sheet-cut <sheet> [--version=N]
  patch.py <id> sheets-draw [--budget=dollars] | sheets-cut | resize | cost
  patch.py <id> video-gen [clip ids] [--attempt=N] | video-pick <clip ids> [--attempt=N]
  patch.py <id> split <clip id> <ranges...> | unfreeze | match-sizes
  patch.py <id> check | final [clip ids]
  patch.py <id> board <file.png> <frames> [cols] | hands <file.png> [frames] | grips <file.png> <frames> | anim <file.gif> <frames> | stats | sizes | repeats | moving <frames> | colors
  patch.py <id> review-page [--port=8798]             local page: review each action, verdicts go to design/<id>/review.json
  patch.py <id> build | install
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def survey(cls, equipment):
    from kit.config import GAME, PARTS
    from dnf_resources import read_npk

    pack = f"sprite_character_{cls}_{equipment}"
    skin = read_npk(GAME / f"{pack}_avatar_skin.NPK")
    counts = Counter(r["frame_count"] for r in skin)
    print("skin", len(skin), "rigs by frame count", dict(counts), "main rig", counts.most_common(1)[0][0], skin[0]["path"])
    for part in PARTS:
        rows = read_npk(GAME / f"{pack}_avatar_{part}.NPK")
        base = [r["path"].rsplit("/", 1)[1][:-4] for r in rows if re.search(r"0000[a-z]\d?\.img$", r["path"])]
        print(f"{part:<6} {len(rows):>5} {dict(Counter(r['frame_count'] for r in rows))} base layers {base[:9]}")
    for path in sorted(GAME.glob(f"{pack}_weapon_*.NPK")):
        rows = read_npk(path)
        print("weapon", path.name.split("weapon_")[1][:-4], len(rows), [r["path"].rsplit("/", 1)[1][:-4] for r in rows[:4]])
    print("growtype", [p.name.replace(pack + "_", "")[:-4] for p in sorted(GAME.glob(f"{pack}_growtype*.NPK"))])


def real_order(cls, equipment, layers):
    """Back-to-front order of the base layers from the resource library (kb/kb.sqlite, see kb/README.md), which has the game's z per layer.
    The contact-sheet guess put the female slayer's white tights (pants d, z 1150) under her skin. Returns the guess unchanged when a layer has no z."""
    import sqlite3
    from kit.config import ROOT

    db_path = ROOT / "kb/kb.sqlite"
    if not db_path.exists():
        print("kb/kb.sqlite missing: composite_order is a guess; run scripts/dnf_kb.py scan and import")
        return layers
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    row = db.execute("select name from profession where cls=? and eq=?", (cls, equipment)).fetchone()
    if not row:
        print(f"no community layer data for {cls}/{equipment}: composite_order is a guess, check it on the contact sheet")
        return layers
    z = {}
    for layer in layers:
        part, name = layer.split("/")
        if part == "skin":
            z[layer] = 0
            continue
        letter = name[-1]
        hit = db.execute("select z from avatar_layer where profession=? and part=? and code=0 and layer=?", (row[0], part, letter)).fetchone() \
            or db.execute("select z from avatar_layer where profession=? and part=? and layer=? group by z order by count(*) desc", (row[0], part, letter)).fetchone()
        if hit:
            z[layer] = hit[0]
    missing = [layer for layer in layers if layer not in z]
    if missing:
        print("no z for", missing, ": composite_order is a guess, check it on the contact sheet")
        return layers
    ordered = sorted(layers, key=lambda layer: z[layer])
    print("composite_order from kb (z):", ", ".join(f"{layer} {z[layer]}" for layer in ordered))
    return ordered


def init(ident, cls, equipment, prefix, weapon=None, stem=None):
    """A first patch.json from the class's base layers. Check the contact sheet: layer order is a guess until then."""
    from kit.config import GAME, ROOT
    from dnf_resources import read_npk

    pack = f"sprite_character_{cls}_{equipment}"
    layers = {}
    for part in ("hair", "coat", "pants", "shoes", "face", "cap"):
        rows = read_npk(GAME / f"{pack}_avatar_{part}.NPK")
        layers[part] = [r["path"].rsplit("/", 1)[1][:-4] for r in rows if re.fullmatch(rf"{prefix}_{part}0000[a-z]\.img", r["path"].rsplit("/", 1)[1])]
    frames = Counter(r["frame_count"] for r in read_npk(GAME / f"{pack}_avatar_skin.NPK")).most_common(1)[0][0]
    body = f"skin/{prefix}_body0000"

    def named(part, *letters):
        return [f"{part}/{n}" for n in layers[part] if n[-1] in letters]

    # No cap: a class's base cap can be anything (the female slayer's is a pumpkin head), and it would hide the head in every reference.
    order = named("pants", "d") + named("hair", "d") + named("hair", "b") + [body] + named("shoes", "b") + named("shoes", "a") + named("pants", "a") + \
        named("coat", "d") + named("coat", "c") + named("coat", "b") + named("coat", "a") + named("face", "c", "b") + named("hair", "a")
    order = real_order(cls, equipment, order)
    data = {
        "title": "TODO 职业 · 角色", "version": 1, "class": cls, "equipment": equipment, "frames": frames,
        "materials": f"{ident}_source", "out": f"{ident}_v01", "master": "master_a_0.png", "npk_stem": stem or f"A_{ident}",
        "body": body, "composite_order": order, "figure_layers": [body] + named("pants", "a") + named("shoes", "a", "b") + named("coat", "a", "b", "c"),
        "cover_layers": named("coat", "a", "b", "c", "d") + named("pants", "a") + named("hair", "a"),
        "standing_frames": [0, 3], "height_ratio": 0.98, "graft_hands": True,
        "character": {"name": "TODO", "reference_image": "TODO path", "identity": "TODO one paragraph: hair, face, costume, colors. Used in every sheet and video prompt.",
                      "hands_rule": "Her hands are empty: no weapon of any kind."},
        "license_note": "TODO 形象来源和授权情况",
    }
    if weapon:
        rows = read_npk(GAME / f"{pack}_weapon_{weapon}.NPK")
        # Some layers are older and shorter than the body rig (the mage's rod a and b have 155 frames against 174), and would run out of frames.
        rows = [r for r in rows if r["frame_count"] >= frames] or rows
        names = [r["path"].rsplit("/", 1)[1][:-4] for r in rows]
        base = sorted({re.sub(r"[a-z]\d?$", "", n) for n in names})[0]
        # An "x" layer holds swing effects, not the weapon.
        data["weapon"] = {"kind": weapon, "label": weapon, "layers": [n for n in names if re.sub(r"[a-z]\d?$", "", n) == base and n[-1] != "x"]}
        data["hand_detect"] = "visible_skin" if weapon in ("rev", "auto", "hcan") else "arm_end"
        if data["hand_detect"] == "arm_end":
            # Long weapons usually mean gloves: the skin shows no hand, and the sprite's hand pixels would paint someone else's color on her.
            data.update(grip_fallback=True, grip_gap=True, graft_hands=False)
    folder = ROOT / "design" / ident
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "patch.json"
    if target.exists():
        raise SystemExit(f"{target} exists; edit it instead")
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    print(target)


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    flags = {a[2:].split("=")[0]: a.split("=", 1)[1] if "=" in a else True for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]
    if args[0] == "survey":
        return survey(args[1], args[2])
    if args[0] == "init":
        return init(*args[1:5], weapon=flags.get("weapon"), stem=flags.get("stem"))
    os.environ["PATCH_ID"] = args[0]
    action, rest = args[1], args[2:]
    version, attempt = int(flags.get("version", 1)), int(flags.get("attempt", 1))
    if action in ("composites", "measure"):
        from kit import source
        if action == "measure":
            return source.measure()
        source.export_composites()
        return source.draft_segments()
    if action in ("master-refs", "master-draw", "master-edit", "small", "sheet-refs", "sheet-draw", "sheet-cut", "sheets-draw", "sheets-cut", "resize", "cost"):
        from kit import sheets
        if action == "sheets-draw":
            return sheets.draw_all(float(flags["budget"]) if "budget" in flags else None)
        if action in ("sheets-cut", "resize", "cost"):
            return {"sheets-cut": sheets.cut_all, "resize": sheets.resize, "cost": sheets.cost}[action]()
        return {"master-refs": lambda: sheets.master_refs(), "master-draw": lambda: sheets.master_draw(rest[0]), "master-edit": lambda: sheets.master_edit(rest[0], rest[1]), "small": lambda: sheets.small(rest),
                "sheet-refs": lambda: sheets.refs(rest[0]), "sheet-draw": lambda: sheets.draw(rest[0], version), "sheet-cut": lambda: sheets.cut(rest[0], version)}[action]()
    if action == "video-gen":
        from kit import video
        return video.generate(rest, attempt)
    if action in ("video-pick", "split", "unfreeze", "match-sizes", "final"):
        from kit import process
        if action == "video-pick":
            for name in rest:
                process.process_clip(name, attempt)
            return None
        return {"split": lambda: process.split(rest[0], *rest[1:]), "unfreeze": process.unfreeze, "match-sizes": process.match_sizes, "final": lambda: process.final(rest)}[action]()
    if action in ("board", "hands", "grips", "anim", "stats", "sizes", "repeats", "moving", "check", "colors"):
        from kit import review
        if action == "sizes":
            return review.sizes()
        if action == "repeats":
            return review.repeats()
        if action == "moving":
            return review.moving(rest[0])
        if action == "grips":
            return review.grips(rest[0], rest[1])
        if action == "anim":
            return review.anim(rest[0], rest[1])
        if action == "colors":
            return review.colors()
        if action == "board":
            return review.board(rest[0], rest[1], int(rest[2]) if len(rest) > 2 else 8)
        if action == "hands":
            return review.hands_board(rest[0], rest[1] if len(rest) > 1 else None)
        return review.stats() if action == "stats" else review.check()
    if action == "review-page":
        from kit import review_page
        return review_page.serve(int(flags.get("port", 8798)))
    if action in ("build", "install"):
        from kit import release
        if action == "install":
            return release.install()
        release.build()
        release.preview()
        return release.release()
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
