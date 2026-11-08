"""gpt-image-2 against the hard cases: large frames at 2K, logos on a design image, a dense sheet of tiny objects."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gunner_props import CLI, FAMILIES, MASTER, SHEET, SIDE, STYLE, WORK, boxes_from_gaps, collect, cut_key, fit, layout, master_path, sheet_ref  # noqa: E402

OUT = WORK / "model_test2"
# Plain descriptions of what the fictional game props look like.
NEUTRAL = {
    "ordnance": "a set of tiny collectible gadgets from a 2D fantasy action game, only about 20 pixels wide in the game: small capsules, canisters and round pods. Each is one or two big shapes: a cream ceramic shell, a near-black band or cap, and one glowing clay orange dot.",
    "flamer": "a fictional science-fiction heat projector prop from a 2D fantasy action game: a handle and nozzle at one end, a perforated tube at the other, and a capsule-shaped tank slung underneath. The tank is smooth cream ceramic with a clay orange spark emblem on its side, the tube is near-black with cream ends, and small glowing clay orange seams mark the lines.",
}
MODEL = "gpt-image-2"
SAMPLE = ROOT / "output/gunner_props_sample"


def jobs():
    items = {}
    draw, _ = collect("walker")
    walker = layout(draw)[0]
    items["walker_2k"] = dict(prompt=SHEET.format(extra="", item=FAMILIES["walker"]["item"], count=len(walker["items"]), cols=walker["cols"], rows=walker["rows"]), refs=[STYLE, master_path("walker"), sheet_ref("walker", 0, walker)], resolution="2k")
    draw, _ = collect("ordnance")
    small = layout(draw)[0]
    items["ordnance_1k"] = dict(prompt=SHEET.format(extra="", item=NEUTRAL["ordnance"], count=len(small["items"]), cols=small["cols"], rows=small["rows"]), refs=[STYLE, master_path("ordnance"), sheet_ref("ordnance", 0, small)], resolution="1k")
    items["bomb_logo"] = dict(prompt=MASTER.format(extra="", item=FAMILIES["bomb"]["item"]), refs=[STYLE, SAMPLE / "bomb_ref.png"], resolution="1k")
    items["flamer_logo"] = dict(prompt=MASTER.format(extra="", item=NEUTRAL["flamer"]), refs=[STYLE, WORK / "refs/flamer_master_ref.png"], resolution="1k")
    return items


def paint(name, job):
    if list(OUT.glob(f"{name}_0.*")):
        return name, "already drawn", 0
    started = time.time()
    command = [sys.executable, str(CLI), "image", "--model", MODEL, "--prompt", job["prompt"], "--n", "1", "--size", "1:1", "--resolution", job["resolution"], "--quality", "high", "--out", str(OUT), "--name", name, "--timeout", "600"]
    for ref in job["refs"]:
        command += ["--image", str(ref)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    return name, result.returncode if result.returncode == 0 else result.stderr[-240:], round(time.time() - started)


def on_magenta(path):
    """Production cut reads flat magenta; this model returns real transparency."""
    image = Image.open(path).convert("RGBA")
    a = np.asarray(image, np.float32)
    alpha = a[..., 3:4] / 255
    page = a[..., :3] * alpha + np.array([255, 0, 255], np.float32) * (1 - alpha)
    target = path.with_name(path.stem + "_key.png")
    Image.fromarray(page.astype(np.uint8), "RGB").save(target)
    return target, float((a[..., 3] < 10).mean()), image.size


def scored(path, family, number=0):
    draw, _ = collect(family)
    sheet = layout(draw)[number]
    sheet_ref(family, number, sheet)
    art_full = cut_key(path)
    found = boxes_from_gaps(art_full, sheet)
    ratio = art_full.width / SIDE
    frames, scores = [], []
    for k, d in enumerate(sheet["items"]):
        cx, cy, w, h = d["place"]
        box = found[k] if found else tuple(int(v * ratio) for v in (cx, cy, cx + w, cy + h))
        frame, value = fit(art_full.crop(box), d["pic"])
        frames.append(frame)
        scores.append(value)
    return sheet, frames, scores, found is not None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    work = jobs()
    with ThreadPoolExecutor(4) as pool:
        for result in pool.map(lambda kv: paint(*kv), work.items()):
            print(result, flush=True)
    summary = {}
    panels = []
    for name, family, base in (("walker_2k", "walker", WORK / "raw/walker_sheet00_v1_0.png"), ("ordnance_1k", "ordnance", WORK / "raw/ordnance_sheet00_v1_0.png")):
        path = next(OUT.glob(f"{name}_0.*"), None)
        if path is None:
            print(name, "no image")
            continue
        key, clear, size = on_magenta(path)
        sheet, frames, scores, separable = scored(key, family)
        _, old_frames, old_scores, old_sep = scored(base, family)
        summary[name] = dict(size=size, transparent=round(clear, 3), separable=separable, mean=round(float(np.mean(scores)), 3), worst=round(min(scores), 3), baseline_mean=round(float(np.mean(old_scores)), 3), baseline_worst=round(min(old_scores), 3))
        print(name, summary[name], flush=True)
        panels.append((name, sheet, frames, old_frames))
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
    board = Image.new("RGB", (1500, 2100), (70, 78, 98))
    pen = ImageDraw.Draw(board)
    y = 4
    for name, sheet, frames, old_frames in panels:
        count = 6 if name == "walker_2k" else 18
        step = max(1, len(frames) // count)
        picks = list(range(0, len(frames), step))[:count]
        zoom = 1 if name == "walker_2k" else 3
        for label, row in (("官方", [d["pic"] for d in sheet["items"]]), ("2.6 native", old_frames), ("gpt-image-2", frames)):
            pen.text((4, y), f"{name} {label}", fill=(255, 225, 120), font=font)
            y += 22
            x = 4
            height = 0
            for k in picks:
                pic = row[k]
                big = pic.resize((pic.width * zoom, pic.height * zoom), Image.NEAREST) if zoom > 1 else pic
                if x + big.width > 1490:
                    break
                board.paste(big, (x, y), big)
                x += big.width + 6
                height = max(height, big.height)
            y += height + 8
    for name, base in (("bomb_logo", WORK.parent / "gunner_props_sample/raw/bomb_v1_0.png"), ("flamer_logo", WORK / "raw/flamer_master_v1_0.png")):
        path = next(OUT.glob(f"{name}_0.*"), None)
        if path is None:
            continue
        key, _, _ = on_magenta(path)
        pen.text((4, y), f"{name}: 左 2.6 native，右 gpt-image-2", fill=(255, 225, 120), font=font)
        y += 22
        board.paste(Image.open(base).convert("RGB").resize((360, 360)), (4, y))
        board.paste(Image.open(key).convert("RGB").resize((360, 360)), (374, y))
        y += 370
    board = board.crop((0, 0, 1500, y))
    board.save(OUT / "compare.png")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    print(OUT / "compare.png", board.size)


if __name__ == "__main__":
    main()
