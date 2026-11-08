"""One way of sorting a patch's IMG paths into what the user cares about, used by the dashboard's coverage and by the review board.

A patch is compared with the game by these categories, so two projects can be read side by side: which ones touched the
cut-ins, which kept the official awakening frames, and so on.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "kb" / "kb.sqlite"

# (key, label, review player). Order is the order of columns and tabs everywhere.
CATEGORIES = [
    ("avatar", "人物时装", None),
    ("growtype", "转职附加外观", "sprite"),
    ("weapon", "武器", "sprite"),
    ("cutin", "切入图", "screen"),
    ("awake", "大招人物帧", "sprite"),
    ("effect", "技能特效和道具", "sprite"),
    ("monster", "召唤物", "sprite"),
    ("other", "其他", "sprite"),
]
LABEL = {k: label for k, label, _ in CATEGORIES}
PLAYER = {k: player for k, _, player in CATEGORIES}


def classify(path):
    p = path.lower()
    name = p.rsplit("/", 1)[-1]
    if re.match(r"^sprite/character/[^/]+/[^/]+/avatar/", p):
        return "avatar"
    if re.match(r"^sprite/character/[^/]+/[^/]+/weapon/", p) or "/weapon/" in p and p.startswith("sprite/character/"):
        return "weapon"
    if re.match(r"^sprite/character/[^/]+/[^/]+/(growtype|custom)/", p) or p.startswith("sprite/character/character/"):
        return "growtype"
    if "/effect/cutin/" in p:
        return "cutin"
    if "awakebody" in name:
        return "awake"
    if p.startswith("sprite/monster/"):
        return "monster"
    if p.startswith("sprite/character/"):
        return "effect"
    return "other"


def _female_side(stem, eq):
    """Cut-in files of the patched gender, by the usual naming: 'at' files belong to the 'atequipment' side. Only an estimate."""
    stem = re.sub(r"^\(\d+\)", "", stem)
    return stem.startswith("at") == eq.startswith("at")


def official_totals(cls, eq):
    """How many official IMGs each category has for this class folder, from the resource library. Effects are shared by both genders."""
    if not KB.exists():
        return {}
    db = sqlite3.connect(f"file:{KB}?mode=ro", uri=True)
    official = "npk in (select id from npk where lower(name) like 'sprite%')"
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0]  # noqa: E731
    out = {
        "avatar": one(f"select count(*) from avatar_img where cls=? and eq=? and {official}", cls, eq),
        "weapon": one(f"select count(*) from weapon_img where cls=? and eq=? and {official}", cls, eq),
        "growtype": one(f"select count(*) from img where (path like ? or path like ? or path like ?) and {official}",
                        f"sprite/character/{cls}/{eq}/growtype/%", f"sprite/character/{cls}/{eq}/custom/%", f"sprite/character/character/{cls}/{eq}/%"),
        "awake": one(f"select count(*) from img where path like ? and path like '%awakebody%' and {official}", f"sprite/character/{cls}/%"),
        "effect": one(f"select count(*) from img where path like ? and path not like '%/effect/cutin/%' and path not like '%awakebody%' and {official}", f"sprite/character/{cls}/effect/%"),
    }
    cutins = [r[0] for r in db.execute(f"select path from img where path like ? and {official}", (f"sprite/character/{cls}/effect/cutin/%",))]
    out["cutin"] = sum(1 for p in cutins if _female_side(p.rsplit("/", 1)[1][:-4], eq))
    db.close()
    return out
