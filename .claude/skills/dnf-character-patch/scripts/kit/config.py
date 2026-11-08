"""One patch's settings, read from design/<id>/patch.json. The CLI sets PATCH_ID before importing the other modules."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "scripts"))

GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
PARTS = ("belt", "cap", "coat", "face", "hair", "neck", "pants", "shoes", "skin")


class Patch:
    def __init__(self, ident):
        self.id = ident
        self.run = ROOT / "design" / ident
        self.data = json.loads((self.run / "patch.json").read_text("utf-8"))
        d = self.data
        self.title = d["title"]
        self.version = d["version"]
        self.cls, self.equipment = d["class"], d["equipment"]
        self.pack = f"sprite_character_{self.cls}_{self.equipment}"
        self.prefix = f"sprite/character/{self.cls}/{self.equipment}/avatar/"
        self.frames = d["frames"]
        self.canvas = d.get("canvas", 500)
        self.body = d["body"]
        self.order = tuple(d["composite_order"])
        self.figure = tuple(d["figure_layers"])
        self.cover = tuple(d["cover_layers"])
        self.weapon = d.get("weapon")
        self.out = ROOT / "output" / d.get("out", f"{ident}_v{self.version}")
        self.materials = ROOT / "materials" / d["materials"]
        self.composites = self.materials / "reference_composite/frames"
        self.parts = self.out / "parts"
        self.master = self.parts / "raw" / d.get("master", "master_0.png")
        self.npk = f"{d['npk_stem']}_v{self.version:02d}.NPK"
        self.old_npks = tuple(f"{d['npk_stem']}_v{v:02d}.NPK" for v in range(1, self.version))
        self.standing = d["standing_frames"]
        self.height_ratio = d.get("height_ratio", 0.98)
        self.skin_rule = d.get("skin_rule", dict(red_minus_green=[36, 95], red_min=195, blue_min=115))
        self.graft = d.get("graft_hands", True)
        self.hand_detect = d.get("hand_detect", "visible_skin")
        self.grips_per_frame = d.get("grips_per_frame", 1)
        self.grip_fallback = d.get("grip_fallback", False)
        self.preview_box = d.get("preview_box")
        self.grip_gap = d.get("grip_gap", False)
        self.most_move = d.get("most_move", 18)
        self.grade = d.get("grade", {})
        self.ink = d.get("ink")
        self.sheet_style = d.get("sheet_style")
        self.character = d.get("character", {})
        self.notes = d.get("license_note", "")

    def clips(self):
        data = json.loads((self.run / "clips.json").read_text("utf-8"))["clips"]
        for clip in data:
            clip["id"] = f"clip_{clip['start']:03d}_{clip['end']:03d}"
        return data


P = Patch(os.environ["PATCH_ID"]) if os.environ.get("PATCH_ID") else None
