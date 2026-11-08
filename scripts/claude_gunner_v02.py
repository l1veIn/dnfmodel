"""Rework of the kept video clips for v02: split clips, equal size within a clip, no frozen runs.

Usage (ComfyUI venv python): claude_gunner_v02.py split | sizes | unfreeze | match
"""
from __future__ import annotations

import json
import shutil
import sys

import av
import numpy as np
from PIL import Image
from scipy import ndimage

from claude_gunner import OUT, RUN, figure_mask, native_world
from claude_gunner_gen import clips
from claude_gunner_process import best_shift
from fatfish_final_process import matte, placed_mask

CLIPS = OUT / "clips"
SPLITS = {"clip_021_025": [(22, 25)]}
STEP = 3


def selection(ident):
    return json.loads((CLIPS / ident / "selection.json").read_text("utf-8"))


def store(ident, report):
    (CLIPS / ident / "selection.json").write_text(json.dumps(report, indent=1), "utf-8")


def split():
    for ident, keeps in SPLITS.items():
        report = selection(ident)
        for start, end in keeps:
            name = f"clip_{start:03d}_{end:03d}"
            (CLIPS / name / "hd").mkdir(parents=True, exist_ok=True)
            rows = [r for r in report["frames"] if start <= r["slot"] <= end]
            for row in rows:
                shutil.copy2(CLIPS / ident / f"hd/{row['slot']:04d}.png", CLIPS / name / f"hd/{row['slot']:04d}.png")
            store(name, dict(report, clip=name, source_clip=ident, frames=rows))
        shutil.rmtree(CLIPS / ident)
    stale = [p for p in CLIPS.iterdir() if p.name not in {c["id"] for c in clips()}]
    for path in stale:
        print("removing stale", path.name)
        shutil.rmtree(path)
    (OUT / "borrow.json").write_text("{}", "utf-8")


def refit(row, ident, window, scale):
    alpha = Image.open(CLIPS / ident / f"hd/{row['slot']:04d}.png").getchannel("A")
    offset = row.get("offset_before_ground", row["offset"])
    target = np.roll(np.roll(figure_mask(row["slot"]), -row["track"][1], 0), -row["track"][0], 1)
    placed = placed_mask(alpha, window, scale, offset[0], offset[1])
    _, dx, dy = best_shift(placed, target, 8, 1)
    return [offset[0] + dx, offset[1] + dy]


def sizes():
    """A figure does not change size inside one action: the scale differences were fitting noise."""
    for clip in clips():
        ident = clip["id"]
        report = selection(ident)
        if "sheet" in report:
            continue
        scales = [r["scale"] for r in report["frames"]]
        common = float(np.median(scales))
        if max(scales) - min(scales) < 0.005:
            continue
        for row in report["frames"]:
            row.pop("offset_before_ground", None)
            if abs(row["scale"] - common) >= 0.005:
                row["offset"] = refit(row, ident, report["window"], common)
                row["scale"] = round(common, 3)
        print(ident, scales, "->", round(common, 3))
        store(ident, report)


def match(most=1.03, goal=0.99):
    """Video clips drawn taller than the rest pop in size at the cut. Bring upright ones down to the sheets' height against the sprite."""
    for clip in clips():
        ident = clip["id"]
        report = selection(ident)
        if "sheet" in report:
            continue
        ratios = []
        for row in report["frames"]:
            box = Image.open(OUT / f"native_frames/{row['slot']:04d}.png").getchannel("A").getbbox()
            native = native_world(row["slot"]).getbbox()
            ratios.append((box[3] - box[1]) / (native[3] - native[1]))
        typical = float(np.median(ratios))
        if typical <= most or max(ratios) - min(ratios) > 0.1:
            continue
        scale = round(report["frames"][0]["scale"] * goal / typical, 3)
        for row in report["frames"]:
            row["offset"] = refit(row, ident, report["window"], scale)
            row.pop("offset_before_ground", None)
            row["scale"] = scale
        print(ident, "height", round(typical, 3), "scale ->", scale)
        store(ident, report)


def unfreeze():
    """A repeated video frame freezes her; the neighboring frames hold the pose while hair and cloth keep moving."""
    for clip in clips():
        ident = clip["id"]
        report = selection(ident)
        if "sheet" in report:
            continue
        rows = report["frames"]
        picks = [r["video_frame"] for r in rows]
        if len(set(picks)) == len(picks):
            continue
        folder = RUN / "jobs" / report.get("source_clip", ident) / f"attempt_{report['attempt']:02d}"
        job = json.loads((folder / "job.json").read_text("utf-8"))
        with av.open(job["stages"][0]["videos"][0]) as video:
            frames = [f.to_image() for f in video.decode(video=0)]
        new = list(picks)
        i = 0
        while i < len(new):
            j = i
            while j + 1 < len(new) and picks[j + 1] == picks[i]:
                j += 1
            if j > i:
                ceiling = picks[j + 1] - 1 if j + 1 < len(picks) else len(frames) - 1
                floor = new[i - 1] + 1 if i else 12
                span = (j - i) * STEP
                first = int(np.clip(picks[i] - span // 2, floor, max(floor, ceiling - span)))
                for k in range(i, j + 1):
                    new[k] = min(first + (k - i) * STEP, ceiling)
            i = j + 1
        for row, pick, old in zip(rows, new, picks):
            if pick != old:
                matte(frames[pick]).save(CLIPS / ident / f"hd/{row['slot']:04d}.png")
                row["video_frame"] = pick
        print(ident, picks, "->", new)
        store(ident, report)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"split": split, "sizes": sizes, "unfreeze": unfreeze, "match": match}[sys.argv[1]]()
