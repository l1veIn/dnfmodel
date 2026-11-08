"""A sheet has one scale, but the model draws some cells at their own size, so a clip can pop against its neighbors. This re-scales named clips
to a height against the sprite and re-places them as sheet-cut does. Re-run after any sheet-cut, then run final. Frames in `measure` are upright ones."""
import json
import os
import sys

os.environ["PATCH_ID"] = "gpt_dragon_slayer"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.claude/skills/dnf-character-patch/scripts"))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from PIL import Image

from kit.art import placed_mask, placement
from kit.config import P
from kit.process import best_shift
from kit.source import figure_mask, native_world

TARGETS = json.loads((P.run / "clip_scales.json").read_text("utf-8"))


def main():
    for ident, goal in TARGETS.items():
        folder = P.out / "clips" / ident
        report = json.loads((folder / "selection.json").read_text("utf-8"))
        window = report["window"]
        old = report["frames"][0]["scale"]
        ratios = []
        for row in report["frames"]:
            image = Image.open(folder / f"hd/{row['slot']:04d}.png")
            box = image.getchannel("A").getbbox()
            native = native_world(row["slot"]).getbbox()
            # The drawing's height in world pixels at the current scale, against the sprite's.
            ratios.append((box[3] - box[1]) * window[2] * old / image.width / (native[3] - native[1]))
        scale = old * goal / float(np.median(ratios))
        for row in report["frames"]:
            image = Image.open(folder / f"hd/{row['slot']:04d}.png")
            alpha = image.getchannel("A")
            box = alpha.getbbox()
            size = int(round(window[2] * scale))
            k = size / image.width
            native = native_world(row["slot"]).getbbox()
            target = figure_mask(row["slot"])
            rows = np.nonzero(target.any(1))[0]
            left0, top0 = placement(window, scale)
            dx = int(round((native[0] + native[2]) / 2 - (left0 + (box[0] + box[2]) / 2 * k)))
            dy = int(rows.max()) + 1 - int(round(top0 + box[3] * k))
            _, sx, _ = best_shift(placed_mask(alpha, window, scale, dx, dy), target, 14, 1)
            row["scale"] = round(scale, 3)
            row["offset"] = [dx + sx, dy]
            row.pop("offset_before_ground", None)
        # One drawing with micro motion: the only movement should be the sway, as in sheet-cut.
        if len({r["video_frame"] for r in report["frames"]}) == 1:
            for row in report["frames"]:
                row["offset"] = list(report["frames"][0]["offset"])
        (folder / "selection.json").write_text(json.dumps(report, indent=1), "utf-8")
        print(ident, "scale", round(old, 3), "->", round(scale, 3))


main()
