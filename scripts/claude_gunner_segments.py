"""Draft action clips for the 143 gunner frames from silhouette continuity, and a labelled contact sheet for checking them."""
from __future__ import annotations

import json
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from claude_gunner import FRAMES, MATERIALS, RUN, figure_mask, native_world

CUT = 0.42
FONT = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)


def continuity():
    masks = [figure_mask(i) for i in range(FRAMES)]
    values = []
    for a, b in zip(masks, masks[1:]):
        best = 0.0
        for dx in range(-12, 13, 3):
            moved = np.roll(b, dx, 1)
            best = max(best, (a & moved).sum() / max((a | moved).sum(), 1))
        values.append(float(best))
    return values


def segments(values):
    cuts = [0] + [i + 1 for i, v in enumerate(values) if v < CUT] + [FRAMES]
    return [(a, b - 1) for a, b in zip(cuts, cuts[1:])]


def sheet(values, clips, per_row=16, cell=(112, 140)):
    w, h = cell
    rows = (FRAMES + per_row - 1) // per_row
    board = Image.new("RGB", (per_row * w, rows * h), (86, 97, 122))
    draw = ImageDraw.Draw(board)
    starts = {a for a, _ in clips}
    for i in range(FRAMES):
        x, y = (i % per_row) * w, (i // per_row) * h
        image = native_world(i)
        box = image.getbbox()
        center = (box[0] + box[2]) // 2
        crop = image.crop((center - w // 2, 345 - h + 8, center + w // 2, 345 + 8))
        board.paste(crop, (x, y), crop)
        color = "yellow" if i in starts else "white"
        draw.text((x + 2, y + 1), str(i), fill=color, font=FONT)
        if i in starts:
            draw.line((x, y, x, y + h), fill=(255, 220, 0), width=2)
    return board


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    values = continuity()
    clips = segments(values)
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "segments_auto.json").write_text(json.dumps(dict(cut=CUT, continuity=[round(v, 3) for v in values], clips=clips), indent=1), "utf-8")
    print(len(clips), clips)
    sheet(values, clips).save(MATERIALS / "reference_composite/contact_all.png")
