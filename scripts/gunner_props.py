"""Redraw the gunner's skill props and robots in Claude style and merge them into one NPK.

    python scripts/gunner_props.py plan
    python scripts/gunner_props.py masters [family ...]
    python scripts/gunner_props.py sheets [family ...]
    python scripts/gunner_props.py cut [family ...]
    python scripts/gunner_props.py board <family>

Only reads the game folder until `install`. Every paid image is journaled once; a redraw takes a new version number.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from dnf_resources import read_npk, write_v2  # noqa: E402
from kit import art  # noqa: E402
from survey_gunner_effects import GAME, reader  # noqa: E402

art.INK = np.array((24, 18, 16), np.float32)
CFG = json.loads((ROOT / "design/gunner_props/families.json").read_text("utf-8"))
FAMILIES = {**CFG["weapons"], **CFG["robots"]}
WORK = ROOT / "output" / "gunner_props"
JOURNAL = WORK / "journal.json"
LOCK = threading.Lock()
CLI = Path(r"C:\Users\A\Desktop\fatfish_game\.agents\skills\65535\scripts\s65535.py")
MODEL = "gpt-image-2"  # About $0.038 at 1K and 2K alike, see the 2026-11-07 model test. Earlier sheets used gpt-image-2.6-sunburst-native.
STYLE = ROOT / "output/claude_gunner_v02/parts/raw/claude_a_0.png"
KEY = (255, 0, 255)
PACKS = {"ROOT": "sprite_character_gunner_effect", "EQ105": "sprite_character_equipmenteffect_105lv_equipment_character_atlauncher", "TEMPESTERAT": "sprite_monster_gunner_tempesterat"}
SIDE = 2048

COMMON = """Image 1 is only the color and rendering authority{extra}: warm cream white, matte near-black, clay orange and thin gold trim, with clean cel shading and bold dark outlines of even weight. Do not draw any character from it, and no flowers, ribbons or fabric.

Design language: premium future hardware from a calm, thoughtful AI lab. Smooth glazed ceramic armor plates in warm cream white, matte near-black joints and machinery, clean deliberate panel lines, thin gold trim, and glowing seams and energy in clay orange, RGB 217 119 87 to 232 112 48, with a pale cream core. No blue, no green, no purple, no red, no rust, no grime, no military olive.
"""
TAIL = """Keep shapes large and simple, because this will be reduced to game size. No pixel art, no painterly texture, no extra objects. Background: completely flat uniform magenta, RGB 255 0 255, edge to edge, with no shadow, no floor, no glow spilling onto it, no grid lines, no borders, and no text other than what is described."""
MASTER = COMMON + """
Image 2 is a game sprite on a flat magenta background. It decides the object's silhouette, its position and size in the square, and its viewing angle, and nothing about its surface. Redraw the object in exactly the same place, at the same size and the same angle, so that it could be laid over the sprite and match its outline.

The object is {item}

""" + TAIL
SHEET = COMMON + """
Image 2 is a finished design from the same product line. Keep exactly its materials, colors and level of detail on every drawing; where Image 3 shows the same object, keep its emblem too.

Image 3 is a grid of {count} animation frames from a game sprite, {cols} across and {rows} down, on flat magenta with empty magenta between them. Each frame decides only the silhouette, position, size, angle and pose; its colors mean nothing. Redraw every frame as this design, in the same place in the grid, at the same size and the same angle, so that it could be laid over that frame and match its outline. Parts that move or come apart stay exactly where the frame shows them. Soft motion streaks become pale warm gray streaks in the same place. Never fill the empty magenta between frames, and never merge neighboring frames.

The object is {item}

""" + TAIL


def source_key(text):
    pack, stem = text.split("/")
    return PACKS.get(pack, f"sprite_character_gunner_effect_{pack}"), stem


def load_img(pack, stem):
    path = GAME / f"{pack}.NPK"
    for entry in read_npk(path):
        if Path(entry["path"]).stem == stem:
            with path.open("rb") as stream:
                stream.seek(entry["offset"])
                return reader(stream.read(entry["length"]), entry["version"]), entry
    raise KeyError(f"{pack}/{stem}")


def geometry(frame):
    """Both reader classes, one set of names."""
    return dict(x=frame["x"], y=frame["y"], canvas_width=frame.get("cw", frame.get("canvas_width")), canvas_height=frame.get("ch", frame.get("canvas_height")))


def is_flat(pic):
    """A white flash or a single-color silhouette: nothing to redraw."""
    a = np.asarray(pic.convert("RGBA"), np.float32)
    seen = a[..., 3] > 40
    return seen.sum() < 12 or a[..., :3][seen].std(0).max() < 12


def normalized(pic):
    a = np.asarray(pic.convert("RGBA"), np.float32)
    return a[..., 3] > 40, a[..., :3].mean(2)


def same_drawing(a, b):
    """Same outline and shading, ignoring hue: the blue and yellow versions of a weapon, and held frames."""
    if abs(a.width - b.width) > 3 or abs(a.height - b.height) > 3:
        return False
    w, h = max(a.width, b.width), max(a.height, b.height)
    pa, pb = [Image.new("RGBA", (w, h)) for _ in range(2)]
    pa.paste(a, ((w - a.width) // 2, (h - a.height) // 2))
    pb.paste(b, ((w - b.width) // 2, (h - b.height) // 2))
    ma, la = normalized(pa)
    mb, lb = normalized(pb)
    both = ma & mb
    union = (ma | mb).sum()
    if not union or both.sum() / union < 0.93:
        return False
    return np.abs(la[both] - lb[both]).mean() < 26


def collect(family):
    """Every frame of a family, each pointing to the drawing it reuses. Output: (frames to draw, all frame records)."""
    spec = FAMILIES[family]
    draw, records = [], []
    for source in spec["sources"]:
        pack, stem = source_key(source)
        try:
            img, entry = load_img(pack, stem)
        except (KeyError, FileNotFoundError):
            print("  missing", source)
            continue
        for frame in img.frames:
            index = frame["index"]
            record = dict(source=source, pack=pack, img=entry["path"], index=index, version=entry["version"])
            records.append(record)
            if "link" in frame:
                record["link"] = frame["link"]
                continue
            record.update(geometry(frame), w=frame["w"], h=frame["h"])
            pic = img.image(index) if frame["w"] * frame["h"] > 16 else None
            if pic is None:
                record["keep"] = True
                continue
            pic = pic.convert("RGBA")
            if not pic.getbbox() or is_flat(pic):
                record["keep"] = True
                continue
            if f"{source}:{index}" in spec.get("keep_frames", []):
                record["keep"] = True
                continue
            match = next((d for d in draw if same_drawing(pic, d["pic"])), None)
            if match:
                record["same_as"] = match["id"]
                continue
            drawing = dict(id=len(draw), pic=pic, source=source, index=index, w=pic.width, h=pic.height)
            record["drawing"] = drawing["id"]
            draw.append(drawing)
    return draw, records


def capacity(top):
    """How many frames of this size share a sheet while keeping about 2 screen pixels per sprite pixel."""
    for side, limit in ((40, 6), (90, 6), (180, 5), (290, 4), (430, 3)):
        if top <= side:
            return limit
    return 1


def layout(draw):
    """Sheets in animation order; frames of similar size share one zoom."""
    sheets, current = [], []

    # People need more pixels per frame than machines: their faces and hands have to survive.
    person = bool(draw) and any(draw[0]["source"] in spec["sources"] for spec in FAMILIES.values() if spec.get("person"))

    def fits(items):
        top = max(max(d["w"], d["h"]) for d in items)
        low = min(max(d["w"], d["h"]) for d in items)
        limit = (9 if top <= 290 else 4 if top <= 580 else 1) if person else capacity(top) ** 2
        return top / max(low, 1) <= 6 and len(items) <= limit

    for drawing in draw:
        if current and not fits(current + [drawing]):
            sheets.append(current)
            current = []
        current.append(drawing)
    if current:
        sheets.append(current)
    plans = []
    for items in sheets:
        cols = max(1, math.ceil(math.sqrt(len(items))))
        rows = math.ceil(len(items) / cols)
        cell = SIDE // max(cols, rows)
        top = max(max(d["w"], d["h"]) for d in items)
        zoom = min(int(cell * 0.84 / top * 4) / 4, 24)
        plans.append(dict(items=items, cols=cols, rows=rows, cell=cell, zoom=zoom))
    return plans


def journal_add(name, **data):
    with LOCK:
        journal = json.loads(JOURNAL.read_text("utf-8")) if JOURNAL.exists() else {}
        if name in journal and "exit" in journal[name] and journal[name]["exit"] == 0 and not data.get("force"):
            return False
        journal[name] = {**journal.get(name, {}), **data}
        JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), "utf-8")
    return True


def journal_has(name):
    if not JOURNAL.exists():
        return False
    return name in json.loads(JOURNAL.read_text("utf-8"))


PERSON_MODEL = "gpt-image-2.6-sunburst-native"
IDENTITY = json.loads((ROOT / "design/claude_gunner/patch.json").read_text("utf-8"))["character"]["identity"]
PERSON = """Image 1 is the character authority: {identity} Keep her face, her very long straight orange hair, her orange flower hair ornament with the black ribbon, and her dress with its colors. Do not give her the sprite's clothes, hairstyle, goggles or skin exposure.

{what}

The figure is {item}

Design language for the machine: premium future hardware from a calm, thoughtful AI lab. Smooth glazed ceramic plates in warm cream white, matte near-black machinery, thin gold trim, and glowing seams in clay orange. Small red lights become clay orange. No olive, no rust, no grime.

Clean cel shading with bold dark outlines of even weight, large simple shapes, because this will be reduced to game size. No pixel art, no extra objects, no text. Background: completely flat uniform magenta, RGB 255 0 255, edge to edge, with no shadow, no floor and no glow spilling onto it.
"""
PERSON_MASTER = "Image 2 is a game sprite on flat magenta. It decides the silhouette, position, size, angle and pose, and nothing about color or costume. Redraw it in exactly the same place so it could be laid over the sprite and match its outline."
PERSON_SHEET = "Image 2 is the finished design of this figure: keep exactly her look and the machine's look on every drawing. Image 3 is a grid of {count} animation frames from a game sprite, {cols} across and {rows} down, on flat magenta with empty magenta between them. Each frame decides only the silhouette, position, size, angle and pose; its colors and costume mean nothing. Redraw every frame as this design, in the same place in the grid, at the same size and angle, so it could be laid over that frame and match its outline. Never fill the empty magenta between frames, and never merge neighboring frames."


def balance():
    result = subprocess.run([sys.executable, str(CLI), "usage", "--start", "2026-11-07", "--end", "2026-11-07"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in result.stdout.splitlines():
        if "account_balance" in line:
            return float(line.split(":")[1].strip().rstrip(","))
    return None


def paint(name, prompt, refs, resolution="2k", model=None):
    raw = WORK / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    target = raw / f"{name}_0.png"
    if target.exists() or journal_has(name):
        return name, "skipped"
    money = balance()
    if money is not None and money < 2:
        return name, f"stopped, balance {money}"
    journal_add(name, prompt=prompt, refs=[str(r) for r in refs], started=time.time(), resolution=resolution)
    command = [sys.executable, str(CLI), "image", "--model", model or MODEL, "--prompt", prompt, "--n", "1", "--size", "1:1", "--resolution", resolution, "--quality", "high", "--out", str(raw), "--name", name, "--timeout", "900"]
    if model:
        command += ["--background", "opaque"]
    for ref in refs:
        command += ["--image", str(ref)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    journal_add(name, exit=result.returncode, finished=time.time(), error=result.stderr[-300:] if result.returncode else "")
    return name, result.returncode


def plan(names=None):
    total = 0
    summary = {}
    for family in names or FAMILIES:
        draw, records = collect(family)
        sheets = layout(draw)
        frames = sum(1 for r in records if "link" not in r)
        keep = sum(1 for r in records if r.get("keep"))
        same = sum(1 for r in records if "same_as" in r)
        master = 0 if "master" in FAMILIES[family] or "design_from" in FAMILIES[family] else 1
        total += len(sheets) + master
        summary[family] = dict(frames=frames, keep=keep, reuse=same, draw=len(draw), sheets=len(sheets), master=master)
        print(f"{family:14} frames {frames:4} keep {keep:3} reuse {same:3} draw {len(draw):3} sheets {len(sheets):2} grids {[f'{s['cols']}x{s['rows']}@{s['zoom']}' for s in sheets]}")
    print("paid images", total)
    (WORK / "plan.json").parent.mkdir(parents=True, exist_ok=True)
    (WORK / "plan.json").write_text(json.dumps(summary, indent=1), "utf-8")


def key_frame(draw):
    """The design is drawn on the largest clean frame: lots of hard-edged pixels, so not a motion smear."""
    def score(d):
        a = np.asarray(d["pic"], np.float32)
        return (a[..., 3] > 230).sum()
    return max(draw, key=score)


def master_ref(family, draw):
    """Returns a reference with the key frame centered on magenta."""
    pick = key_frame(draw)
    zoom = max(1, min(900 // pick["w"], 900 // pick["h"]))
    big = pick["pic"].resize((pick["w"] * zoom, pick["h"] * zoom), Image.NEAREST)
    board = Image.new("RGB", (1024, 1024), KEY)
    board.paste(big, ((1024 - big.width) // 2, (1024 - big.height) // 2), big)
    path = WORK / "refs" / f"{family}_master_ref.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    board.save(path)
    return path


def masters(names=None):
    jobs = []
    for family in names or FAMILIES:
        spec = FAMILIES[family]
        if "master" in spec or "design_from" in spec:
            continue
        draw, _ = collect(family)
        if not draw:
            continue
        ref = master_ref(family, draw)
        if spec.get("person"):
            jobs.append((f"{family}_master_v1", PERSON.format(identity=IDENTITY, what=PERSON_MASTER, item=spec["item"]), [STYLE, ref], "2k", PERSON_MODEL))
            continue
        jobs.append((f"{family}_master_v1", MASTER.format(extra="", item=spec["item"]), [STYLE, ref], "2k"))
    with ThreadPoolExecutor(4) as pool:
        for result in pool.map(lambda j: paint(*j), jobs):
            print(result, flush=True)


def master_path(family):
    spec = FAMILIES[family]
    if "master" in spec:
        return ROOT / spec["master"]
    if "design_from" in spec:
        return master_path(spec["design_from"])
    return WORK / "raw" / f"{family}_master_v1_0.png"


def sheet_ref(family, number, sheet):
    board = Image.new("RGB", (SIDE, SIDE), KEY)
    cols, rows, cell, zoom = sheet["cols"], sheet["rows"], sheet["cell"], sheet["zoom"]
    origin_x, origin_y = (SIDE - cols * cell) // 2, (SIDE - rows * cell) // 2
    for k, d in enumerate(sheet["items"]):
        w, h = int(d["w"] * zoom), int(d["h"] * zoom)
        big = d["pic"].resize((w, h), Image.NEAREST)
        cx = origin_x + (k % cols) * cell + (cell - w) // 2
        cy = origin_y + (k // cols) * cell + (cell - h) // 2
        board.paste(big, (cx, cy), big)
        d["place"] = (origin_x + (k % cols) * cell, origin_y + (k // cols) * cell, cell, cell)
    path = WORK / "refs" / f"{family}_sheet{number:02d}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    board.save(path)
    return path


def sheets(names=None, workers=4):
    jobs = []
    for family in names or FAMILIES:
        spec = FAMILIES[family]
        draw, _ = collect(family)
        if not draw:
            continue
        for number, sheet in enumerate(layout(draw)):
            ref = sheet_ref(family, number, sheet)
            if spec.get("person"):
                what = PERSON_SHEET.format(count=len(sheet["items"]), cols=sheet["cols"], rows=sheet["rows"])
                jobs.append((f"{family}_sheet{number:02d}_v1", PERSON.format(identity=IDENTITY, what=what, item=spec["item"]), [STYLE, master_path(family), ref], "2k", PERSON_MODEL))
                continue
            prompt = SHEET.format(extra="", item=spec["item"], count=len(sheet["items"]), cols=sheet["cols"], rows=sheet["rows"])
            jobs.append((f"{family}_sheet{number:02d}_v1", prompt, [STYLE, master_path(family), ref], "2k"))
    print("sheets to submit", len(jobs), flush=True)
    with ThreadPoolExecutor(workers) as pool:
        for result in pool.map(lambda j: paint(*j), jobs):
            print(result, flush=True)


def redo(family, number, version, note):
    """One sheet again, with a correction appended to the prompt."""
    spec = FAMILIES[family]
    draw, _ = collect(family)
    sheet = layout(draw)[int(number)]
    ref = sheet_ref(family, int(number), sheet)
    prompt = SHEET.format(extra="", item=spec["item"], count=len(sheet["items"]), cols=sheet["cols"], rows=sheet["rows"]) + " " + note
    print(paint(f"{family}_sheet{int(number):02d}_v{version}", prompt, [STYLE, master_path(family), ref], "2k"))


def cut_key(path):
    source = Image.open(path)
    if source.mode == "RGBA" and (np.asarray(source)[..., 3] < 10).mean() > 0.2:
        # gpt-image-2 returns real transparency, so there is no magenta to remove.
        return source.copy()
    rgb = np.asarray(source.convert("RGB"), np.float32)
    key = np.array(KEY, np.float32)
    alpha = np.clip((np.sqrt(((rgb - key) ** 2).sum(2)) - 70) / 90, 0, 1)
    alpha = np.where(ndimage.binary_opening(alpha > 0.5, iterations=1) | (alpha > 0.95), alpha, 0)
    spill = np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1]
    clean = rgb.copy()
    # Inside a shape, a pink tint on something pale means it was meant to be white: lift green. At the edge, take the magenta out.
    solid = spill > 4
    inner = solid & (alpha >= 0.9)
    edge = solid & (alpha < 0.9)
    clean[..., 1][inner] += spill[inner]
    clean[..., 0][edge] -= spill[edge]
    clean[..., 2][edge] -= spill[edge]
    return Image.fromarray(np.dstack([np.clip(clean, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")


def restyle_trail(pic):
    """Soft motion streaks of the old frame, warm gray, to sit under the new drawing."""
    a = np.asarray(pic.convert("RGBA"), np.float32)
    value = a[..., :3].max(2)
    tone = np.stack([value * 0.92 + 18, value * 0.86 + 14, value * 0.8 + 12], 2)
    return Image.fromarray(np.dstack([np.clip(tone, 0, 255), a[..., 3]]).astype(np.uint8), "RGBA")


def fit(drawn, old, margin=4):
    """The model places each drawing freely inside its cell. Find what it drew, scale that onto the old frame's bounding box, reduce it, then nudge. Returns the frame and its overlap."""
    w, h = old.size
    old_a = np.asarray(old, np.float32)[..., 3]
    mo = old_a > 60
    rows, cols = np.nonzero(mo)
    if not len(rows):
        rows, cols = np.nonzero(old_a > 0)
    ox0, ox1, oy0, oy1 = cols.min(), cols.max() + 1, rows.min(), rows.max() + 1
    # Specks at cell edges must not stretch the box.
    alpha = np.asarray(drawn, np.float32)[..., 3] > 128
    labels, count = ndimage.label(ndimage.binary_dilation(alpha, iterations=6))
    if not count:
        return Image.new("RGBA", old.size), 0.0
    sizes = ndimage.sum(alpha, labels, range(1, count + 1))
    keep = np.isin(labels, [i + 1 for i, v in enumerate(sizes) if v >= max(40, sizes.max() * 0.01)])
    alpha &= keep
    drawn = drawn.copy()
    drawn.putalpha(Image.fromarray((np.asarray(drawn)[..., 3] * keep).astype(np.uint8)))
    nrows, ncols = np.nonzero(alpha)
    box = (int(ncols.min()), int(nrows.min()), int(ncols.max()) + 1, int(nrows.max()) + 1)
    bw, bh = box[2] - box[0], box[3] - box[1]
    sx, sy = (ox1 - ox0) / bw, (oy1 - oy0) / bh
    # Stretch a little to match; a big disagreement means the proportions differ, so keep them and center.
    if max(sx, sy) / min(sx, sy) > 1.18:
        sx = sy = (sx * sy) ** 0.5
    tw, th = max(1, round(bw * sx)), max(1, round(bh * sy))
    color, a = art.downscale(drawn.crop(box), (tw, th), line_keep=0.45)
    small = art.finish(art.sharpen(color, 0.3), a, outline=True, alpha_cut=0.45)
    made = Image.new("RGBA", (w, h))
    made.paste(small, (int((ox0 + ox1 - tw) / 2), int((oy0 + oy1 - th) / 2)))
    mn = np.asarray(made)[..., 3] > 128
    best, shift = -1, (0, 0)
    for dy in range(-margin, margin + 1):
        for dx in range(-margin, margin + 1):
            moved = np.roll(np.roll(mn, dy, 0), dx, 1)
            score = (moved & mo).sum() / max((moved | mo).sum(), 1)
            if score > best:
                best, shift = score, (dx, dy)
    pixels = np.roll(np.roll(np.asarray(made), shift[1], 0), shift[0], 1).copy()
    # A roll wraps what leaves one edge onto the opposite edge; those pixels are not part of the frame.
    if shift[1] > 0:
        pixels[:shift[1]] = 0
    elif shift[1] < 0:
        pixels[shift[1]:] = 0
    if shift[0] > 0:
        pixels[:, :shift[0]] = 0
    elif shift[0] < 0:
        pixels[:, shift[0]:] = 0
    level = float(np.percentile(old_a[old_a > 8], 90)) if (old_a > 8).any() else 255
    if level < 215:
        pixels[..., 3] = (pixels[..., 3] * (level / 255)).astype(np.uint8)
    return Image.fromarray(pixels, "RGBA"), float(best)


def split_runs(present, parts):
    """Cut a line into `parts` pieces at its widest empty gaps. None when there are not enough gaps."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], present.astype(np.int8), [0]))))
    starts, ends = edges[::2], edges[1::2]
    if len(starts) < parts:
        return None
    gaps = sorted(range(len(starts) - 1), key=lambda i: starts[i + 1] - ends[i], reverse=True)[:parts - 1]
    cuts = sorted((ends[i] + starts[i + 1]) // 2 for i in gaps)
    return [0, *[int(c) for c in cuts], len(present)]


def boxes_from_gaps(art_full, sheet):
    """The model keeps the order but not the spacing of the grid, so frames are found by the empty space between them."""
    alpha = np.asarray(art_full)[..., 3] > 128
    labels, count = ndimage.label(alpha)
    if count:
        sizes = ndimage.sum(alpha, labels, range(1, count + 1))
        alpha = np.isin(labels, [i + 1 for i, v in enumerate(sizes) if v >= 24])
    items = len(sheet["items"])
    rows = sheet["rows"]
    row_cuts = split_runs(alpha.any(1), rows)
    if row_cuts is None:
        return None
    boxes = []
    for r in range(rows):
        top, bottom = row_cuts[r], row_cuts[r + 1]
        wanted = min(sheet["cols"], items - r * sheet["cols"])
        col_cuts = split_runs(alpha[top:bottom].any(0), wanted)
        if col_cuts is None:
            return None
        boxes += [(col_cuts[c], top, col_cuts[c + 1], bottom) for c in range(wanted)]
    return boxes


def cut(names=None):
    report = {}
    for family in names or FAMILIES:
        draw, records = collect(family)
        if not draw:
            continue
        done = {}
        scores = []
        folder = WORK / "frames" / family
        folder.mkdir(parents=True, exist_ok=True)
        for number, sheet in enumerate(layout(draw)):
            sheet_ref(family, number, sheet)
            version = 1
            path = WORK / "raw" / f"{family}_sheet{number:02d}_v{version}_0.png"
            while (WORK / "raw" / f"{family}_sheet{number:02d}_v{version + 1}_0.png").exists():
                version += 1
                path = WORK / "raw" / f"{family}_sheet{number:02d}_v{version}_0.png"
            if not path.exists():
                print("  no sheet", path.name)
                continue
            art_full = cut_key(path)
            ratio = art_full.width / SIDE
            found = boxes_from_gaps(art_full, sheet)
            if found is None:
                print("  grid not separable", path.name)
            for k, d in enumerate(sheet["items"]):
                cx, cy, w, h = d["place"]
                box = found[k] if found else tuple(int(v * ratio) for v in (cx, cy, cx + w, cy + h))
                frame, score = fit(art_full.crop(box), d["pic"])
                frame.save(folder / f"{d['id']:04d}.png")
                done[d["id"]] = frame
                scores.append((round(score, 3), d["source"], d["index"], d["id"]))
        scores.sort()
        report[family] = dict(frames=len(done), mean=round(float(np.mean([s[0] for s in scores])), 3) if scores else None, worst=scores[:6])
        print(family, report[family], flush=True)
    (WORK / "cut_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")


def board(family):
    """Old above, new below, every drawn frame."""
    draw, _ = collect(family)
    cols = 12
    cell = max(90, min(150, max(max(d["w"], d["h"]) for d in draw)))
    rows = (len(draw) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell * 2), (70, 78, 98))
    pen = ImageDraw.Draw(sheet)
    for k, d in enumerate(draw):
        x, y = (k % cols) * cell, (k // cols) * cell * 2
        path = WORK / "frames" / family / f"{d['id']:04d}.png"
        for row, pic in enumerate((d["pic"], Image.open(path).convert("RGBA") if path.exists() else None)):
            if pic is None:
                continue
            shown = pic.copy()
            if max(shown.size) > cell - 2:
                shown.thumbnail((cell - 2, cell - 2))
            elif max(shown.size) * 2 <= cell - 2:
                shown = shown.resize((shown.width * 2, shown.height * 2), Image.NEAREST)
            sheet.paste(shown, (x + (cell - shown.width) // 2, y + row * cell + (cell - shown.height) // 2), shown)
        pen.text((x + 1, y), f"{d['id']}", fill=(255, 225, 120))
    path = WORK / "boards" / f"{family}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=88)
    print(path, sheet.size)


if __name__ == "__main__":
    command, rest = sys.argv[1], sys.argv[2:]
    if command == "redo":
        redo(*rest)
        raise SystemExit
    {"plan": plan, "masters": masters, "sheets": sheets, "cut": cut}.get(command, lambda _: None)(rest or None) if command != "board" else [board(f) for f in rest]
