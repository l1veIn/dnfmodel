"""Same sheet, same prompt, cheaper models: draws once per model, cuts with the production code, and scores against the 2.6 baseline."""
from __future__ import annotations

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gunner_props import CLI, FAMILIES, SHEET, SIDE, STYLE, WORK, boxes_from_gaps, collect, cut_key, fit, layout, master_path, sheet_ref  # noqa: E402

OUT = WORK / "model_test"
FAMILY = "tempester"
MODELS = ["gpt-image-2", "gpt-image-2-eco", "gemini-nano-banana-2.1"]
BASELINE = WORK / "raw" / f"{FAMILY}_sheet00_v1_0.png"


def paint(model, prompt, refs):
    name = model.replace(".", "_")
    if list(OUT.glob(f"{name}_0.*")):
        return model, "already drawn", 0
    started = time.time()
    command = [sys.executable, str(CLI), "image", "--model", model, "--prompt", prompt, "--n", "1", "--size", "1:1", "--resolution", "1k", "--quality", "high", "--out", str(OUT), "--name", name, "--timeout", "600"]
    for ref in refs:
        command += ["--image", str(ref)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    return model, result.returncode if result.returncode == 0 else result.stderr[-240:], round(time.time() - started)


def score(path, sheet):
    art_full = cut_key(path)
    ratio = art_full.width / SIDE
    found = boxes_from_gaps(art_full, sheet)
    frames, scores = [], []
    for k, d in enumerate(sheet["items"]):
        cx, cy, w, h = d["place"]
        box = found[k] if found else tuple(int(v * ratio) for v in (cx, cy, cx + w, cy + h))
        frame, value = fit(art_full.crop(box), d["pic"])
        frames.append(frame)
        scores.append(value)
    return frames, scores, found is not None, art_full.size


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spec = FAMILIES[FAMILY]
    draw, _ = collect(FAMILY)
    sheet = layout(draw)[0]
    ref = sheet_ref(FAMILY, 0, sheet)
    prompt = SHEET.format(extra="", item=spec["item"], count=len(sheet["items"]), cols=sheet["cols"], rows=sheet["rows"])
    with ThreadPoolExecutor(3) as pool:
        for result in pool.map(lambda m: paint(m, prompt, [STYLE, master_path(FAMILY), ref]), MODELS):
            print(result, flush=True)
    candidates = [("2.6 baseline", BASELINE)] + [(m, next(OUT.glob(f"{m.replace('.', '_')}_0.*"), OUT / "none")) for m in MODELS]
    rows = []
    for label, path in candidates:
        if not path.exists():
            print(label, "no image")
            continue
        frames, scores, separable, size = score(path, sheet)
        rows.append((label, frames, Image.open(path).convert("RGB")))
        print(f"{label}: size {size} separable {separable} mean {np.mean(scores):.3f} worst {min(scores):.3f}")
    show = [0, 3, 5, 7, 9, 12]
    cell = 150
    sheet_out = Image.new("RGB", (cell * (len(show) + 1) + 310, (cell + 18) * (len(rows) + 1)), (70, 78, 98))
    pen = ImageDraw.Draw(sheet_out)
    pen.text((4, 2), "official", fill=(255, 225, 120))
    for c, k in enumerate(show):
        pic = sheet["items"][k]["pic"]
        sheet_out.paste(pic, (c * cell + (cell - pic.width) // 2, 18 + (cell - pic.height) // 2), pic)
    for r, (label, frames, raw) in enumerate(rows, 1):
        y = r * (cell + 18)
        pen.text((4, y + 2), label, fill=(255, 225, 120))
        for c, k in enumerate(show):
            pic = frames[k]
            sheet_out.paste(pic, (c * cell + (cell - pic.width) // 2, y + 18 + (cell - pic.height) // 2), pic)
        sheet_out.paste(raw.resize((cell, cell)), (len(show) * cell + 2, y + 18))
    sheet_out.save(OUT / "compare.png")
    print(OUT / "compare.png")


if __name__ == "__main__":
    main()
