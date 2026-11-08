"""Generates clips.json and the rollout part of pose_sheets.json for the whale maid. Motions live in motions.json, keyed by sheet name.

Sheets follow the user's segments (design/fatfish/action_catalog/manual_motion.json); a segment too long for one sheet is split, since a clip must live on one sheet.
Run from the project root. Sheets already defined by hand (idle, walk) are kept.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
# name of segment, start, end, sheet
CLIPS = [
    ("默认走路", 0, 9, "walk"), ("待机站立", 10, 13, "idle_stand"), ("战斗待机", 14, 17, "idle"),
    # Split where a repair sheet replaces some frames: one scale per clip, and frames from two sheets need two scales.
    ("战斗跑", 18, 21, "run"), ("前冲 举杖", 22, 23, "run"), ("前冲 飞扑", 24, 24, "run"), ("前冲 飞扑二", 25, 25, "run"),
    ("前冲摔倒 举杖", 26, 26, "fall"), ("前冲摔倒 举杖二", 27, 27, "fall"), ("前冲摔倒", 28, 34, "fall"),
    ("碎霸", 35, 41, "smash"),
    ("召唤 起手", 42, 47, "summon_a"), ("蹲伏", 53, 54, "summon_a"),
    ("召唤 举手", 48, 48, "summon_b"), ("召唤 举手二", 49, 52, "summon_b"), ("杰克爆弹 起手", 55, 55, "summon_b"), ("杰克爆弹 后仰", 56, 56, "summon_b"), ("杰克爆弹 后仰二", 57, 57, "summon_b"),
    ("杰克爆弹 跃起", 58, 61, "jack"), ("落花掌 起手", 62, 65, "jack"),
    ("落花掌 踢", 66, 73, "kick"),
    ("落花掌 收", 74, 75, "jump_a"), ("跳跃 起跳", 76, 81, "jump_a"),
    ("跳跃 落下", 82, 83, "jump_b"), ("跳跃平A 起手", 84, 88, "jump_b"), ("跳跃平A 举杖", 89, 89, "jump_b"),
    ("跳跃平A 挥", 90, 90, "jump_c"), ("跳跃平A 翻", 91, 91, "jump_c"), ("跳跃平A 倒转", 92, 93, "jump_c"), ("跳跃平A 收", 94, 96, "jump_c"),
    ("啦啦啦 起手", 97, 100, "lala_a"), ("啦啦啦 一", 101, 104, "lala_a"),
    ("啦啦啦 二", 105, 108, "lala_b"), ("三段平A 一", 109, 109, "lala_b"), ("三段平A 一举", 110, 110, "lala_b"), ("三段平A 一收", 111, 112, "lala_b"),
    ("三段平A 二a", 113, 114, "combo_a"), ("三段平A 二b", 115, 115, "combo_a"), ("三段平A 二c", 116, 118, "combo_a"), ("三段平A 二d", 119, 119, "combo_a"), ("三段平A 二e", 120, 120, "combo_a"),
    ("三段平A 三 举杖", 121, 122, "combo_b"), ("三段平A 三", 123, 127, "combo_b"),
    ("受击", 128, 129, "hit"), ("受击倒地", 130, 134, "hit"),
    ("魔法星弹 一", 135, 142, "star"),
    ("魔法星弹 二", 143, 143, "buff"), ("加buff", 144, 147, "buff"), ("鞭挞 一", 148, 150, "buff"),
    ("鞭挞 二", 151, 154, "whip"), ("魔道学者修东西", 155, 157, "whip"),
    ("魔道学者丢东西", 158, 162, "scholar"), ("魔道学者修东西2", 163, 165, "scholar"),
    ("召唤骑士", 166, 169, "knight"), ("驱散", 170, 173, "knight"),
]
LAYOUT = {"fall": {"cols": 5}}
KEEP = ("idle", "walk")

slots = sorted(s for _, a, b, _ in CLIPS for s in range(a, b + 1))
assert slots == list(range(174)), "every frame in exactly one clip"
ANNOTATED = json.loads((HERE.parent / "fatfish/action_catalog/manual_motion.json").read_text("utf-8"))["clips"]


def action_of(start):
    """The user's own segment holding this clip: one action for review, however many clips a sheet split it into."""
    return next(c["name"] for c in ANNOTATED if c["start"] <= start <= c["end"])


(HERE / "clips.json").write_text(json.dumps({
    "note": "Segments from the user's annotation (manual_motion.json revision 26), not parsed ANI; split where one sheet cannot hold them. action names the annotated segment.",
    # The walk's head and torso barely move in the source, so it is placed by its head, not its soles.
    "clips": [{"name": n, "action": action_of(a), "start": a, "end": b, "sheet": s, **({"anchor": "head"} if (a, b) == (0, 9) else {})} for n, a, b, s in CLIPS]}, ensure_ascii=False, indent=1), "utf-8")

old = json.loads((HERE / "pose_sheets.json").read_text("utf-8"))
motions = json.loads((HERE / "motions.json").read_text("utf-8")) if (HERE / "motions.json").exists() else {}
settings = json.loads((HERE / "sheet_settings.json").read_text("utf-8")) if (HERE / "sheet_settings.json").exists() else {}
sheets = {k: dict(old[k], **settings.get(k, {})) for k in KEEP}
for sheet in dict.fromkeys(s for *_, s in CLIPS if s not in KEEP):
    members = [(a, b) for _, a, b, s in CLIPS if s == sheet]
    frames = [i for a, b in members for i in range(a, b + 1)]
    entry = {"frames": frames, "cols": LAYOUT.get(sheet, {}).get("cols", 4), "size": "16:9", "ref_cells": list(range(len(frames))), "motion": motions.get(sheet, "TODO")}
    entry.update(settings.get(sheet, {}))
    entry["clips"] = entry.get("clips") or {f"clip_{a:03d}_{b:03d}": [{"slot": i, "cell": frames.index(i)} for i in range(a, b + 1)] for a, b in members}
    sheets[sheet] = entry
# These were drawn before the source composites were fixed, and have to be cut with the layout they were drawn with.
zooms = json.loads((HERE / "drawn_zooms.json").read_text("utf-8"))
for name, sheet in sheets.items():
    if name in zooms:
        sheet["zoom"] = zooms[name]
(HERE / "pose_sheets.json").write_text(json.dumps(sheets, ensure_ascii=False, indent=1), "utf-8")
print(len(sheets), "sheets", {k: len(v["frames"]) for k, v in sheets.items()})
print("TODO:", [k for k, v in sheets.items() if v["motion"] == "TODO"])
