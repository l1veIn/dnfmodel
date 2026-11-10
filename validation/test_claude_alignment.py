"""Independent raster checks for the current clap, standing and walking repair.

These inspect the actual workbench files against the saved originals, without
importing the repair script. Other workers may edit their own separate actions.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/Claude_Gunner_v02"
WORK = ROOT / "output/validation/claude_motion_review_2026-11-09/alignment"
BEFORE = WORK / "before"
os.environ["PATCH_ID"] = "claude_gunner"
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit.config import P
from kit.source import layer_world


def pixels(path):
    return np.asarray(Image.open(path).convert("RGBA")).copy()


def region(a, box):
    x0, y0, x1, y1 = box
    return a[y0:y1, x0:x1]


def shift(a, xy):
    image = Image.new("RGBA", (500, 500))
    image.paste(Image.fromarray(a, "RGBA"), tuple(xy))
    return np.asarray(image)


class CharacterAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slots = list(range(10, 21)) + list(range(68, 76))
        cls.old = {k: pixels(BEFORE / f"native_frames/{k:04d}.png") for k in cls.slots}
        cls.new = {k: pixels(OUT / f"native_frames/{k:04d}.png") for k in cls.slots}

    def test_clap_planted_boot_is_identical_and_other_foot_still_steps(self):
        foot = (199, 319, 216, 338)
        expected = region(self.old[10], foot)
        self.assertGreater(int((expected[..., 3] > 128).sum()), 80)
        other_centers = []
        for k in range(10, 14):
            np.testing.assert_array_equal(region(self.new[k], foot), expected)
            # The screen-right foot is the stepping foot. It must still move
            # inward rather than being frozen along with the planted side.
            mask = self.new[k][322:337, 240:280, 3] > 128
            _, x = np.where(mask)
            self.assertGreater(len(x), 50)
            other_centers.append(float(x.mean()))
        self.assertGreater(other_centers[0] - other_centers[-1], 6)

    def test_clap_preserves_upper_body_and_each_hand_pose(self):
        for k in range(10, 14):
            # Local correction starts at the waist. This checks pixel identity
            # on the entire top part, including all distinct clapping hands.
            np.testing.assert_array_equal(self.new[k][:258], self.old[k][:258])
        hands = [self.new[k][230:276, 210:260] for k in range(10, 14)]
        self.assertEqual(len({a.tobytes() for a in hands}), 4)

    def test_standing_original_feet_are_static_and_new_boots_are_static(self):
        original_shoes = []
        for k in range(14, 21):
            image = Image.new("RGBA", (500, 500))
            for layer in P.order:
                if layer.startswith("shoes/"):
                    image.alpha_composite(layer_world(layer, k))
            original_shoes.append(np.asarray(image))
        for a in original_shoes[1:]:
            np.testing.assert_array_equal(a, original_shoes[0])
        for box in ((205, 324, 221, 338), (256, 324, 272, 338)):
            expected = region(self.old[14], box)
            for k in range(14, 21):
                np.testing.assert_array_equal(region(self.new[k], box), expected)

    def test_standing_hand_motion_preserved_without_new_body_changes(self):
        foot_mask = np.zeros((500, 500), bool)
        foot_mask[324:338, 205:221] = True
        foot_mask[324:338, 256:272] = True
        for k in range(14, 21):
            delta = (-1, 0) if k in (18, 19) else (0, 0)
            expected = shift(self.old[k], delta)
            np.testing.assert_array_equal(self.new[k][~foot_mask], expected[~foot_mask])
        self.assertGreater(len({self.new[k][220:300, 200:280].tobytes() for k in range(14, 21)}), 4)

    def test_walk_head_height_matches_official_head_band_and_poses_are_intact(self):
        # This deliberately measures a local head ROI, not full-body height or
        # a silhouette box that could be affected by a lifted foot or sleeve.
        official_top, new_top = [], []
        translations = [(0, 0), (-1, 0), (0, 1), (1, 3), (0, 4), (-2, 3), (0, 5), (0, 2)]
        for k, delta in zip(range(68, 76), translations):
            official = np.asarray(layer_world(P.body, k))
            source_head = official[200:240, 225:260, 3] > 128
            drawn_head = self.new[k][200:240, 225:265, 3] > 128
            official_top.append(int(np.where(source_head.any(1))[0].min()))
            new_top.append(int(np.where(drawn_head.any(1))[0].min()))
            np.testing.assert_array_equal(self.new[k], shift(self.old[k], delta))
            # Integer repositioning must not rescale or bend hands or legs.
            old_colors = Counter(map(tuple, self.old[k][self.old[k][..., 3] > 0]))
            new_colors = Counter(map(tuple, self.new[k][self.new[k][..., 3] > 0]))
            self.assertEqual(new_colors, old_colors)
        self.assertLessEqual(max(new_top) - min(new_top), 1)
        self.assertEqual([y - new_top[0] for y in new_top], [y - official_top[0] for y in official_top])

    def test_rasters_remain_solid_and_approved_idle_is_untouched(self):
        for k, a in self.new.items():
            with self.subTest(frame=k):
                self.assertEqual(a.shape, (500, 500, 4))
                self.assertEqual(set(np.unique(a[..., 3])), {0, 255})
                _, count = ndimage.label(a[..., 3] > 128, np.ones((3, 3)))
                self.assertEqual(count, 1)
        snapshot = json.loads((BEFORE / "snapshot.json").read_text("utf-8"))["native_sha256"]
        for k in range(4):
            path = OUT / f"native_frames/{k:04d}.png"
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), snapshot[path.relative_to(ROOT).as_posix()])


if __name__ == "__main__":
    unittest.main()
