"""Repair sheets: frames whose arm or tail the first pass got wrong. Adds them to pose_sheets.json. Run from the project root, after make_sheets.py.

fix_a: the raised arm stopped short, so the rod's grip gap shows. fix_b: the tail grew on her front side in 97-100, and the hand missed the rod in the rest.
"""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("write_motions", HERE / "write_motions.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
COMMON = module.COMMON

REACH = "Her arm must reach all the way to each magenta dot, stretching as far as the sprite's arm does: this is the most important thing in this image. "
REPAIRS = {
    "fix_a": {
        "frames": [22, 23, 25, 27, 89, 90, 121, 122],
        "motion": REACH + "Cell 1: she leans right, and the near arm reaches straight up and back with the elbow high, the closed fist high above and behind her head at the upper left, well above the top of her head. Cell 2: the same lean with the elbow out to the left and the closed fist at the left of her forehead, level with the top of her head. "
                  "Cell 3: a flying lunge, both arms straight to the right at shoulder height with a closed fist at the end, both legs kicked back to the left. Cell 4: the same as cell 2. "
                  "Cell 5: her torso arches, the near arm straight up with the closed fist high above her head at the upper left, the skirt swung to the right, both legs down together. Cell 6: in the air, her torso bent forward, the closed fist beside her head at the left, the skirt at the right, both knees bent under her. "
                  "Cell 7: both arms straight up overhead with the closed fist high above her head, her head tilted down, standing on one straight leg, the skirt flared to the right. Cell 8: arching in the air with the closed fists behind her head at the left, her hips at the right and one knee bent forward with the shoe at the lower left.",
        "ref_cells": [0, 1, 3, 4, 5, 6],
    },
    "fix_b": {
        "frames": [97, 98, 99, 100, 115, 119, 109, 110],
        "motion": REACH + "In cells 1 to 4 her body faces right at three-quarters, so her back, her long hair and her whale tail are all on the LEFT side of the skirt. The tail must never appear on the right side of her or in front of her skirt or apron in these cells. "
                  "Cells 1 and 2: legs apart with the free foot lifting at the lower right, the near arm reaching out to the left at waist height with a closed fist, and the far hand a closed fist in front of her belly on the dot. Cells 3 and 4: standing on one straight leg with the other leg out to the lower right, the near elbow up and back at the left with the closed fist at shoulder height, the skirt tilted. "
                  "Cell 5: upright with one closed fist beside her face at the right and the skirt round and full. Cell 6: leaning forward on one straight leg, both closed fists together in front of her at the right at chest height, the skirt flared to the left. "
                  "Cell 7: standing feet apart facing right, the arms crossing in front of her with one closed fist out to the lower right at chest height and the other raised in front of her face. Cell 8: facing left as in Image 2, both arms raised above her head to the right with closed fists, one foot lifted behind her.",
        "ref_cells": [0, 1, 2, 3, 6],
    },
}
REPAIRS.update(json.loads((HERE / "repairs_feet.json").read_text("utf-8")))
path = HERE / "pose_sheets.json"
sheets = json.loads(path.read_text("utf-8"))
zooms = json.loads((HERE / "drawn_zooms.json").read_text("utf-8"))
for name, entry in REPAIRS.items():
    replace = {str(frame): k for k, frame in enumerate(entry["frames"])}
    replace.update(entry.get("also", {}))
    sheets[name] = {"frames": entry["frames"], "cols": 4, "size": "16:9", "ref_cells": entry["ref_cells"], "mark_grips": True, "motion": COMMON + entry["motion"], "replace": replace}
    for key in ("pad_x", "pad_y", "micro"):
        if key in entry:
            sheets[name][key] = entry[key]
    if name in zooms:
        sheets[name]["zoom"] = zooms[name]
path.write_text(json.dumps(sheets, ensure_ascii=False, indent=1), "utf-8")
print(list(REPAIRS), {n: sheets[n]["replace"] for n in REPAIRS})
