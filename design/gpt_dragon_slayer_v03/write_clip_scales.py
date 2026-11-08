"""clip_scales.json from the per-sheet factors that `sizes` printed on a fresh cut (no clip_scales.json yet). Then run resize and final.

Goal = the clip's current height ratio times its sheet's factor, so this must read a fresh cut. Sheets within about 5% are left alone.
"""
import json, os, sys
os.environ["PATCH_ID"] = "gpt_dragon_slayer_v03"
sys.path.insert(0, ".claude/skills/dnf-character-patch/scripts")
import numpy as np
from PIL import Image
from kit.config import P
from kit.source import native_world

FACTOR = {"air": 1.083, "back_thrust": 0.909, "run": 1.12, "stance": 0.91, "sweep": 1.066, "dash": 1.061, "cleave_a": 1.055}
assert not (P.run / "clip_scales.json").exists(), "needs a fresh cut: delete clip_scales.json, run sheets-cut and final, then sizes"
goals = {}
for clip in P.clips():
    factor = FACTOR.get(clip["sheet"])
    if not factor:
        continue
    folder = P.out / "clips" / clip["id"]
    report = json.loads((folder / "selection.json").read_text("utf-8"))
    ratios = []
    for row in report["frames"]:
        image = Image.open(folder / f"hd/{row['slot']:04d}.png")
        box = image.getchannel("A").getbbox()
        native = native_world(row["slot"]).getbbox()
        ratios.append((box[3] - box[1]) * report["window"][2] * row["scale"] / image.width / (native[3] - native[1]))
    goals[clip["id"]] = round(float(np.median(ratios)) * factor, 3)
(P.run / "clip_scales.json").write_text(json.dumps(goals, indent=1), "utf-8")
print(len(goals), "clips scaled", goals)
