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
    ("buffart", "觉醒特写", "still"),
    ("portrait", "人物立绘", "still"),
    ("awake", "大招人物帧", "sprite"),
    ("effect", "技能特效和道具", "sprite"),
    ("monster", "召唤物", "sprite"),
    ("other", "其他", "sprite"),
]
LABEL = {k: label for k, label, _ in CATEGORIES}
PLAYER = {k: player for k, _, player in CATEGORIES}


# Illustrations outside the class folder: the close-up shown when an awakening skill is used (one per transfer; the COLG index
# calls interface/skillcutscene "使用觉醒时的职业特写"), and the class's
# standing illustrations: character creation, the transfer pictures (one IMG, a frame per transfer for every class) and the
# small animated faces of the adventure UI. File names carry the class and gender, so each profession has its prefixes.
PORTRAIT_DIRS = ("sprite/interface2/charactercreatever2/characterillust/", "sprite/interface2/adventurer2020/neo_",
                 "sprite/interface2/classchange/classchange_cha/", "sprite/interface2/classchange/experienceclassillust",
                 "sprite/interface2/awakening2/awakening_cha/", "sprite/interface2/powerwar_rvr/assault/character_cut/")
# One IMG holding a frame per transfer for every class: transfer pictures, second-awakening close-ups, PK close-ups (COLG index).
SHARED_PORTRAITS = ("sprite/interface2/classchange/classchange_cha/classchange_cha.img", "sprite/interface2/classchange/experienceclassillust.img",
                    "sprite/interface2/awakening2/awakening_cha/awakening2_cha.img", "sprite/interface2/powerwar_rvr/assault/character_cut/character_cut.img")
# profession: (skill portrait prefix, creation illustration name, adventure face prefix)
PREFIXES = {
    "swordman": ("ghost_", "slayerm", "neo_ghostm_"), "swordman_at": ("ghostf_", "slayerf", "neo_ghostf_"),
    "fighter_at": ("atfighter_", "fighterm", "neo_atfighter_"), "fighter": ("fighter_", "fighterf", "neo_fighterf_"),
    "gunner": ("gunner_", "gunnerm", "neo_gunnerm_"), "gunner_at": ("atgunner_", "gunnerf", "neo_gunnerf_"),
    "mage_at": ("magem_", "magem", "neo_magem_"), "mage": ("mage_", "magef", "neo_magef_"),
    "priest": ("priest_", "priestm", "neo_priestm_"), "priest_at": ("priestf_", "priestf", "neo_priestf_"),
    "thief": ("thief_", "thief", "neo_thief_"), "knight": ("knightf_", "knight", "neo_knightf_"),
    "demoniclancer": ("deminiclancer_", "demoniclancer", "neo_demoniclancer_"), "gunblader": ("gunblader_", "gunblader", "neo_gunblader"),
    "archer": ("archer_", "archer", "neo_archer_"),
}


def _bare(path):
    """File name without folder, extension or the (tn)/(18) tags."""
    return re.sub(r"^(\(\w+\))+", "", path.rsplit("/", 1)[1][:-4].lower())


def portrait_of(path, profession):
    """Whether a buff or standing portrait belongs to this profession. The shared transfer pictures belong to every class."""
    if profession not in PREFIXES:
        return False
    skill, illust, face = PREFIXES[profession]
    p, name = path.lower(), _bare(path)
    if p.startswith("sprite/interface/skillcutscene/"):
        return name.startswith(skill)
    if p.startswith("sprite/interface2/charactercreatever2/characterillust/"):
        return name == illust
    if p.startswith("sprite/interface2/adventurer2020/neo_"):
        return name.startswith(face)
    return p in SHARED_PORTRAITS


def portrait_paths(professions):
    """Official buff and standing portraits of these professions, from the resource library."""
    if not KB.exists():
        return []
    db = sqlite3.connect(f"file:{KB}?mode=ro", uri=True)
    rows = [r[0] for r in db.execute("select distinct path from img where (path like 'sprite/interface/skillcutscene/%' or path like 'sprite/interface2/charactercreatever2/characterillust/%' "
                                     "or path like 'sprite/interface2/adventurer2020/neo_%' or path like 'sprite/interface2/classchange/%' "
                                     "or path like 'sprite/interface2/awakening2/awakening_cha/%' or path like 'sprite/interface2/powerwar_rvr/assault/character_cut/%') "
                                     "and npk in (select id from npk where lower(name) like 'sprite%')")]
    db.close()
    return sorted(p for p in rows if classify(p) in ("buffart", "portrait") and any(portrait_of(p, prof) for prof in professions))


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
    if p.startswith("sprite/interface/skillcutscene/"):
        return "buffart"
    if any(p.startswith(prefix) for prefix in PORTRAIT_DIRS):
        return "portrait"
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


def official_totals(cls, eq, profession=None):
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
    if profession:
        mine = portrait_paths([profession])
        out["buffart"] = sum(1 for p in mine if classify(p) == "buffart")
        out["portrait"] = sum(1 for p in mine if classify(p) == "portrait")
    return out
