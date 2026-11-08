"""Review sheets for v06: native above, new below, per clip, plus a numeric pose table."""
from __future__ import annotations

import json
import sys

import numpy as np
from PIL import Image, ImageDraw

from fatfish_final import OUT, clips, native_world
from fatfish_final_process import figure_mask


def sheet(indices, path, zoom=2, cols=10, size=(140, 130)):
    width, height = size
    rows = (len(indices) + cols - 1) // cols
    board = Image.new("RGB", (cols * width * zoom, rows * 2 * height * zoom), (112, 124, 140))
    draw = ImageDraw.Draw(board)
    for k, i in enumerate(indices):
        native = native_world(i)
        box = native.getbbox()
        cx = (box[0] + box[2]) // 2 - 8
        crop = (cx - width // 2, 395 - height, cx + width // 2, 395)
        x, y = (k % cols) * width * zoom, (k // cols) * 2 * height * zoom
        new = Image.open(OUT / f"native_frames/{i:04d}.png").convert("RGBA")
        for row, image in enumerate((native, new)):
            big = image.crop(crop).resize((width * zoom, height * zoom), Image.NEAREST)
            board.paste(big, (x, y + row * height * zoom), big)
        draw.text((x + 3, y + 2), str(i), fill="yellow")
    board.save(path)


def table():
    rows = []
    for clip in clips():
        covers = []
        for i in range(clip["start"], clip["end"] + 1):
            alpha = np.asarray(Image.open(OUT / f"native_frames/{i:04d}.png").getchannel("A")) > 128
            target = figure_mask(i)
            covers.append((alpha & target).sum() / max(target.sum(), 1))
        worst = int(np.argmin(covers)) + clip["start"]
        rows.append((clip["name"], clip["start"], clip["end"], float(np.mean(covers)), worst, float(min(covers))))
        print(f"{clip['name']:<12} {clip['start']:>3}-{clip['end']:<3} figure-cover {np.mean(covers):.3f} worst {worst}:{min(covers):.3f}")
    print("overall", round(float(np.mean([r[3] for r in rows])), 3))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    table()
    (OUT / "qa").mkdir(parents=True, exist_ok=True)
    for clip in clips():
        frames = list(range(clip["start"], clip["end"] + 1))
        sheet(frames, OUT / f"qa/{clip['start']:03d}_{clip['end']:03d}.png", cols=min(10, len(frames)))
