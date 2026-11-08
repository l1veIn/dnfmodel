"""clip_scales.json from per-sheet size factors, measured by figure area against the idle and walk baseline.

Heights mislead here: an arm the model drew lower than the sprite's makes the sheet scale up. Goals are height ratios against the drawn scale,
so this must read a fresh cut with no clip_scales applied: run sheets-cut and final with the file absent, then this, then resize and final.
Repair sheets are measured from those frames; the factors of the other sheets were measured the same way on the first pass.
"""
import json, os, sys
os.environ["PATCH_ID"] = "fatfish_whale_maid"
sys.path.insert(0, ".claude/skills/dnf-character-patch/scripts")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
from PIL import Image
from kit.config import P
from kit.source import native_world

# Restoring her hair and feet to the source composites changed the source heights these sheets are fitted to, so four factors were measured again with sizes.
FACTOR = {"run": 1.149, "fall": 0.87, "summon_a": 0.93, "summon_b": 0.94, "kick": 0.91, "jump_c": 0.843, "lala_b": 0.94, "combo_b": 1.07, "hit": 1.016}
sheets = json.loads((P.run / "pose_sheets.json").read_text("utf-8"))


def area(image):
    return float((np.asarray(image.getchannel("A")) > 128).sum())


def new(i):
    return Image.open(P.out / f"native_frames/{i:04d}.png").convert("RGBA")


def linear(frames):
    return float(np.sqrt(np.median([area(new(i)) / area(native_world(i)) for i in frames])))


clips = P.clips()
base = linear([i for c in clips if c["sheet"] in ("idle", "walk") for i in range(c["start"], c["end"] + 1)])
owner = {}
for name, sheet in sheets.items():
    if "replace" in sheet:
        size = linear(sheet["frames"]) / base
        FACTOR[name] = round(1 / size, 3)
        print(name, "linear size", round(size, 3), "factor", FACTOR[name])
        owner.update({int(i): name for i in sheet["replace"]})
goals = {}
for clip in clips:
    frames = list(range(clip["start"], clip["end"] + 1))
    source = {owner.get(i, clip["sheet"]) for i in frames}
    assert len(source) == 1, f"{clip['id']} mixes sheets {source}: split it"
    # Frames 130 and 131 reuse 128 and 129, so this clip's own frames are the three lying down, which came out 16% small.
    factor = {"clip_130_134": 1.2}.get(clip["id"]) or FACTOR.get(source.pop())
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
print(len(goals), "clips scaled")
