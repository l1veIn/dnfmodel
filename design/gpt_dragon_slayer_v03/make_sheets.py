"""Writes pose_sheets.json, clips.json and reuse.json for v03. Frame numbers start at 0. Run from the project root.

What changed from v02 (see docs/gpt_dragon_slayer_v03.md):
- The source composites were exported again after the streak fix, so every reference cell has both feet.
- Every sheet marks the weapon grips with magenta dots (mark_grips), so the model draws each fist on the hilt.
- No `phase`. Frames the source holds still are one drawing with `micro`, measured with `moving` (only the chest breathes,
  the legs never move). Frames the source repeats exactly come from reuse.json. Every other frame has its own cell.
- The repair sheets of v02 are gone: their frames are back in their own sheets.
Motions live in motions.json, keyed by sheet name, written after reading each sheet's _marked board.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

COMMON = (
    "Copy each cell's facing, body angle, lean and limb positions from Image 2: some cells face left, show her back, lean far over, lie down or are in the air. "
    "Both of her feet are always drawn exactly where the sprite's two boots are, and never dropped: in strides and lunges the gown opens at the slit and lifts with the legs, so each leg and white heel shows at the sprite's leg and boot. "
    "In every pose the wings stay attached at her upper back and turn with her torso, the tail grows from her lower back, and the sleeve drapes hang from her upper arms; in leaps and fast moves they trail behind the motion, and they never cover her forearms or fists. "
    "Seen from behind, her hair falls down her back between the wings, the tail hangs below it, and her arms stay outside the hair. "
)

# Breathing, measured on the source with `moving`: rows of the chest and shoulders lift 1 to 2 game pixels, the head and everything below the waist stay still.
BREATH = {
    1: {"lift": [[0, 0], [0.21, 0], [0.27, -1], [0.38, -1], [0.48, 0], [1, 0]]},
    2: {"lift": [[0, 0], [0.21, 0], [0.27, -1], [0.32, -2], [0.4, -1], [0.48, 0], [1, 0]]},
    3: {"lift": [[0, 0], [0.22, 0], [0.28, -1], [0.34, 0], [1, 0]]},
}
# The user: the source's face does not move in these held frames, so nothing above her chin (about 0.18 of her height) moves either.
MICRO = {
    **{str(f): BREATH[k] for f, k in [(1, 1), (2, 2), (3, 3), (10, 1), (11, 2), (12, 3), (233, 1), (234, 2)]},
    # Battle stance: the shoulders and hair sway left, the head holds.
    "147": {"shear": [[0, 0], [0.23, 0], [0.3, -1], [0.4, 0], [1, 0]]},
    "148": {"shear": [[0, 0], [0.23, 0], [0.3, -2], [0.38, -1], [0.45, 0], [1, 0]]},
    "149": {"shear": [[0, 0], [0.23, 0], [0.3, -1], [0.38, 0], [1, 0]]},
    # Hand at the chest: the head comes along with the breath.
    "186": {"lift": [[0, 0], [0.1, -1], [0.45, -1], [0.52, 0], [1, 0]]},
    "187": {"lift": [[0, -2], [0.3, -2], [0.4, -1], [0.48, -1], [0.53, 0], [1, 0]]},
    "188": {"lift": [[0, -1], [0.45, -1], [0.52, 0], [1, 0]]},
    # Run: these three cells were drawn with shorter legs, so with the head held where the source's is, the feet floated 5 to 7px. Stretch below the waist only.
    "155": {"lift": [[0, 0], [0.45, 0], [1, 5]]},
    "157": {"lift": [[0, 0], [0.45, 0], [1, 6]]},
    "158": {"lift": [[0, 0], [0.45, 0], [1, 5]]},
    # Sheathing: the whole upper body shifts a pixel left, the feet stay.
    "239": {"shear": [[0, -1], [0.6, -1], [0.85, 0], [1, 0]]},
}
# Frames the source repeats (`repeats`, same grip or none): the earlier frame's finished picture.
REUSE = {"7": 6, "8": 6, "171": 169, "189": 91, "216": 191, "217": 195, "218": 196, "219": 197, "220": 198, "221": 199, "235": 233, "173": 169}

# sheet: (cell frames, layout, [(clip label, start, end, action)]); a slot not in the cell frames takes the cell given in HOLD.
SHEETS = {
    # Frames 0-8 moved to idle_hold after the user's review; the idle drawing keeps its cells so it still cuts the same.
    "idle": ([0, 4, 5, 9, 146, 150, 185, 232], {}, [("叉腰站", 9, 12, "叉腰站"),
                                                    ("战斗站姿", 146, 149, "战斗站姿"), ("战斗站姿收", 150, 150, "战斗站姿"), ("胸前举手", 185, 188, "胸前举手"), ("背刀站", 232, 235, "背刀站")]),
    # Not drawn by the model: frame 0's drawing with only the front arm and head edited (idle_hand_edit.py), so the legs never move, as in the source.
    "idle_hold": ([0, 4, 5, 6], {"hold": True}, [("待机", 0, 3, "待机"), ("待机抬手", 4, 8, "待机抬手")]),
    "walk": (list(range(13, 23)), {"cols": 5}, [("走路", 13, 22, "走路")]),
    "reach": (list(range(23, 29)), {"size": "3:2", "cols": 3}, [("探手", 23, 28, "探手")]),
    "dash": (list(range(29, 37)), {}, [("低身突进", 29, 32, "低身突进"), ("低身挥臂", 33, 33, "低身突进"), ("低身回刀", 34, 36, "低身突进")]),
    "air": (list(range(37, 45)), {}, [("跃起", 37, 44, "跃起")]),
    "slash_a": (list(range(45, 53)), {}, [("落步蓄势", 45, 49, "落步上挑"), ("上挑", 50, 52, "落步上挑")]),
    "slash_b": (list(range(53, 61)), {}, [("大步下劈", 53, 60, "大步下劈")]),
    "lunge_a": (list(range(61, 69)), {}, [("低身冲刺", 61, 63, "低身冲刺"), ("收势", 64, 65, "低身冲刺"), ("长弓步", 66, 68, "长弓步")]),
    "lunge_b": (list(range(69, 75)), {"size": "3:2", "cols": 3}, [("长弓步续", 69, 72, "长弓步"), ("俯身", 73, 74, "长弓步")]),
    "spread": (list(range(75, 84)), {"cols": 5}, [("展臂", 75, 77, "展臂"), ("背身高举", 78, 80, "展臂"), ("举手站定", 81, 83, "展臂")]),
    "low_cut": (list(range(84, 92)), {}, [("低身横斩", 84, 91, "低身横斩")]),
    "arm_out": (list(range(92, 100)), {}, [("举刀", 92, 93, "举刀前指"), ("前指", 94, 96, "举刀前指"), ("腾跃", 97, 99, "腾跃")]),
    "back_thrust": (list(range(100, 109)), {"cols": 5}, [("背身前刺", 100, 102, "背身刺"), ("交臂", 103, 105, "背身刺"), ("背身下刺", 106, 108, "背身刺")]),
    "flip": (list(range(109, 115)), {"size": "3:2", "cols": 3}, [("翻转", 109, 114, "翻转")]),
    "rise_cut": (list(range(115, 123)), {}, [("低步上撩", 115, 122, "低步上撩")]),
    "gesture_a": (list(range(123, 132)), {"cols": 5}, [("挥臂", 123, 128, "挥臂平举"), ("平举", 129, 131, "挥臂平举")]),
    "gesture_b": (list(range(132, 140)), {}, [("举手", 132, 135, "举手摊手"), ("摊手", 136, 138, "举手摊手"), ("下蹲", 139, 139, "举手摊手")]),
    "down": (list(range(140, 146)), {"size": "3:2", "cols": 3}, [("击倒", 140, 143, "击倒"), ("蹲起", 144, 145, "击倒")]),
    "run": (list(range(151, 159)), {}, [("跑步", 151, 158, "跑步")]),
    "stance": (list(range(159, 165)), {"size": "3:2", "cols": 3}, [("连斩", 159, 164, "连斩")]),
    "flurry": ([165, 166, 167, 168, 169, 170, 172], {}, [("俯身回斩", 165, 167, "连续横扫"), ("连续横扫", 168, 173, "连续横扫")]),
    "sweep": (list(range(174, 182)), {}, [("回身突进", 174, 181, "回身突进")]),
    "poise": ([182, 183, 184, 190, 191, 192, 193, 194], {}, [("低身压刀", 182, 184, "低身压刀"), ("转身刺", 189, 191, "转身刺"), ("平刺", 192, 193, "转身刺"), ("回身斩", 194, 194, "回身斩")]),
    "thrust": (list(range(195, 201)), {"size": "3:2", "cols": 3}, [("回身斩续", 195, 200, "回身斩")]),
    "cleave_a": (list(range(201, 209)), {}, [("背身劈", 201, 204, "背身劈回旋"), ("回旋", 205, 208, "背身劈回旋")]),
    "cleave_b": ([209, 210, 211, 212, 213, 214, 215, 230, 231], {"cols": 5}, [("下潜上挑", 209, 216, "下潜上挑"), ("高踢", 230, 231, "回身高踢")]),
    "rising": (list(range(222, 230)), {}, [("上撩转身", 217, 224, "上撩转身"), ("回身高踢", 225, 229, "回身高踢")]),
    "finish": ([236, 237, 238, 240, 241, 242, 243, 244, 245], {"cols": 5}, [("收刀", 236, 237, "收刀"), ("收刀停", 238, 239, "收刀"), ("收刀末", 240, 240, "收刀"), ("终结", 241, 245, "终结")]),
}
# Held or reused slots: which frame's cell they take. Reused ones are overwritten at `final`, so any cell of their sheet would do; the source frame's cell keeps the look close.
HOLD = {1: 0, 2: 0, 3: 0, 7: 6, 8: 6, 10: 9, 11: 9, 12: 9, 147: 146, 148: 146, 149: 146, 186: 185, 187: 185, 188: 185, 233: 232, 234: 232, 235: 232,
        239: 238, 171: 169, 173: 169, 189: 190, 216: 215, 217: 222, 218: 222, 219: 222, 220: 222, 221: 222}
# Head-anchored clips: the source holds the head and torso while the feet step.
ANCHOR = {"clip_013_022", "clip_151_158"}
# Cells that set the sheet's size: upright, arms not overhead. Default all cells.
REF = {"idle": [0, 1, 2, 3, 5, 6, 7], "air": [0, 4, 5], "low_cut": [0, 1, 2, 3, 7], "arm_out": [0, 1, 2, 3, 4], "back_thrust": [3, 4],
       "flip": [0, 5], "gesture_b": [0, 1, 2, 3, 4, 5, 6], "down": [0, 5], "sweep": [0, 1, 2, 7], "poise": [4, 7], "thrust": [3, 4, 5],
       "cleave_b": [0, 1, 7], "rising": [2, 3, 6, 7], "finish": [0, 1, 2, 3], "spread": [0, 1, 2, 6, 7, 8], "gesture_a": [0, 1, 2, 3, 4, 5], "stance": [0, 2, 5], "rise_cut": [3, 4], "slash_b": [0, 1, 5, 6]}

motions = json.loads((HERE / "motions.json").read_text("utf-8")) if (HERE / "motions.json").exists() else {}
sheets, clips = {}, []
for name, (frames, layout, segments) in SHEETS.items():
    entry = dict(frames=frames, cols=layout.get("cols", 4), size=layout.get("size", "16:9"), ref_cells=REF.get(name, list(range(len(frames)))),
                 mark_grips=True, motion=COMMON + motions[name] if name in motions else "TODO", clips={})
    if layout.get("hold"):
        entry.update(hold=True, motion="Composed locally by idle_hand_edit.py, never sent to the model.")
    if name not in ("idle", "walk"):
        entry["pad_y"] = 40
    micro = {}
    for label, start, end, action in segments:
        ident = f"clip_{start:03d}_{end:03d}"
        rows = []
        for slot in range(start, end + 1):
            cell = frames.index(slot) if slot in frames else frames.index(HOLD[slot])
            rows.append(dict(slot=slot, cell=cell))
            if str(slot) in MICRO:
                micro[str(slot)] = MICRO[str(slot)]
        entry["clips"][ident] = rows
        clip = dict(name=label, start=start, end=end, sheet=name, action=action)
        if ident in ANCHOR:
            clip["anchor"] = "head"
            if ident == "clip_151_158":
                # Her hair streams up above her horns in the run, so the head match needs rows down to her face.
                clip["anchor_px"] = 48
        clips.append(clip)
    if micro:
        entry["micro"] = micro
    sheets[name] = entry
# Repairs after the first full pass: these fists were drawn off the hilt by more than the 12px the hand fit can pull.
REPAIRS = {
    "repair_a": [85, 86, 87, 181, 190, 168],
    "repair_b": [121, 159, 164, 226, 227],
    # Second try for raised fists the model kept drawing too low: 121 and 164 overhead, 190 at shoulder height.
    "repair_c": [121, 164, 190],
    # From the user's review: the closing fist (6), the other hand raised (126, 127), the hilt missed (131), the kick and the finish cut off at the cell edge (230, 231, 243-245).
    "repair_d": [6, 126, 127, 131],
    "repair_e": [230, 231, 243, 244, 245],
}
LAYOUT_REPAIR = {"repair_d": dict(cols=4, replace={"126": 1, "127": 2, "131": 3}), "repair_e": dict(cols=3, pad_x=150, pad_y=70, ref_cells=[1, 4],
                                                      # 243 and 244 are nearly the same source frame, and the model drew 244 from behind: both take the front view.
                                                      replace={"230": 0, "231": 1, "243": 2, "244": 2, "245": 4})}
for name, frames in REPAIRS.items():
    sheets[name] = dict(frames=frames, cols=3, size="16:9", ref_cells=list(range(len(frames))), mark_grips=True, pad_x=110, pad_y=50,
                        replace={str(f): k for k, f in enumerate(frames)}, motion=COMMON + motions[name] if name in motions else "TODO")
    sheets[name].update(LAYOUT_REPAIR.get(name, {}))
clips.sort(key=lambda c: c["start"])
covered = [s for c in clips for s in range(c["start"], c["end"] + 1)]
assert sorted(covered) == list(range(246)), ("missing", sorted(set(range(246)) - set(covered)), "doubled", sorted({s for s in covered if covered.count(s) > 1}))
note = "v03 clips. Names describe the look of the frames; they are not parsed game ANI definitions. Generated by make_sheets.py."
(HERE / "pose_sheets.json").write_text(json.dumps(sheets, ensure_ascii=False, indent=1), "utf-8")
(HERE / "clips.json").write_text(json.dumps(dict(note=note, clips=clips), ensure_ascii=False, indent=1), "utf-8")
(HERE / "reuse.json").write_text(json.dumps(REUSE, indent=1), "utf-8")
cells = sum(len(s["frames"]) for s in sheets.values())
cost = sum(0.29 if s["size"] == "3:2" else 0.22 for s in sheets.values())
print(len(sheets), "sheets,", cells, "cells,", len(clips), "clips, about $", round(cost, 2), "| no motion yet:", [n for n, s in sheets.items() if s["motion"] == "TODO"])
