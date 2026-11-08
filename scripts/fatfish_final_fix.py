"""Final v06 pass over processed clips: ground the legs, borrow frames for wrong poses, render with one palette.

Usage (ComfyUI venv python): python fatfish_final_fix.py
Input is OUT/clips/*/selection.json as left by fatfish_final_process, whichever attempt each clip kept.
"""
from __future__ import annotations

import json
import shutil
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

from fatfish_final import OUT, clips
from fatfish_final_process import LOOPING, collect_palette, figure_mask, render_clip

REACH = 14
BAND = 0.2
MARGIN = 6
# slot -> slot whose native pose is nearly the same; applied after rendering.
BORROW_PATH = OUT / "borrow.json"


def ident(clip):
    return f"clip_{clip['start']:03d}_{clip['end']:03d}"


def leg_shift(alpha, target):
    """Vertical shift that puts her soles on the sprite's soles.

    Comparing leg shapes is unreliable because the sprite's boots are far wider than her legs, so
    this compares lowest pixels directly. Only columns under the sprite's lower body count, which
    keeps a tail or hair trailing behind her from being taken for a foot. A correction beyond
    REACH means the columns held no foot at all, so the frame is left alone.
    """
    rows = np.nonzero(target.any(1))[0]
    bottom, height = int(rows.max()), int(rows.max() - rows.min() + 1)
    band = target[bottom - int(height * BAND):bottom + 1]
    columns = np.nonzero(band.any(0))[0]
    left, right = int(columns.min()) - MARGIN, int(columns.max()) + MARGIN + 1
    found = np.nonzero(alpha[:, left:right].any(1))[0]
    if not len(found):
        return 0
    dy = bottom - int(found.max())
    return dy if abs(dy) <= REACH else 0


def ground_all(names, palette):
    moved = {}
    for name in names:
        render_clip(name, palette)
        path = OUT / "clips" / name / "selection.json"
        report = json.loads(path.read_text("utf-8"))
        raw = []
        for row in report["frames"]:
            alpha = np.asarray(Image.open(OUT / f"native_frames/{row['slot']:04d}.png").getchannel("A")) > 128
            raw.append(leg_shift(alpha, figure_mask(row["slot"])))
        # The correction should change slowly; a lone spike is a tail tip taken for a foot.
        calm = ndimage.median_filter(np.array(raw), size=min(3, len(raw) | 1), mode="nearest")
        # The native combat run floats both feet off the ground; hers is a real run, so its soles have no match.
        if name == "clip_018_021":
            calm = np.zeros_like(calm)
        for row, dy in zip(report["frames"], calm):
            dy = int(dy)
            row["offset_before_ground"] = row.get("offset_before_ground", row["offset"])
            row["offset"] = [row["offset"][0], row["offset"][1] + dy]
            if dy:
                moved[row["slot"]] = dy
        path.write_text(json.dumps(report, indent=1), "utf-8")
        render_clip(name, palette)
    return moved


def main():
    names = [ident(c) for c in clips()]
    # Grounding must start from the fitted offset so reruns do not accumulate.
    for name in names:
        path = OUT / "clips" / name / "selection.json"
        report = json.loads(path.read_text("utf-8"))
        for row in report["frames"]:
            if "offset_before_ground" in row:
                row["offset"] = row["offset_before_ground"]
        # A looping action never changes her size, so a fitted scale outlier would pop on every cycle.
        if int(name.split("_")[1]) in LOOPING:
            steady = float(np.median([row["scale"] for row in report["frames"]]))
            for row in report["frames"]:
                row["scale"] = steady
        path.write_text(json.dumps(report, indent=1), "utf-8")
    palette = collect_palette(names)
    moved = ground_all(names, palette)
    print("grounded", len(moved), "frames; largest", max(moved.values(), key=abs, default=0), json.dumps(moved))
    borrow = json.loads(BORROW_PATH.read_text("utf-8")) if BORROW_PATH.exists() else {}
    for slot, source in borrow.items():
        shutil.copy2(OUT / f"native_frames/{int(source):04d}.png", OUT / f"native_frames/{int(slot):04d}.png")
        print("borrowed", slot, "<-", source)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
