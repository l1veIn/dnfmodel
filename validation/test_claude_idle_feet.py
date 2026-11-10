"""Independent raster checks for the four repaired Claude idle frames.

Run after scripts/fix_claude_idle_feet.py has applied its prepared frames.
This reads the actual workbench images and the pre-repair backup; it neither
imports the repair implementation nor changes assets or game files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/Claude_Gunner_v02"
BACKUP = ROOT / "output/validation/claude_idle_feet_fix/before"
CLIP = "clip_000_003"


def rgba(path):
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA")).copy()


def crop(array, box):
    x0, y0, x1, y1 = box
    return array[y0:y1, x0:x1]


def changed(a, b):
    return int(np.count_nonzero(np.any(a != b, axis=-1)))


class RepairedIdle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before_native = [rgba(BACKUP / f"native_frames/{k:04d}.png") for k in range(4)]
        cls.before_hd = [rgba(BACKUP / f"hd/{k:04d}.png") for k in range(4)]
        cls.native = [rgba(OUT / f"native_frames/{k:04d}.png") for k in range(4)]
        cls.hd = [rgba(OUT / f"clips/{CLIP}/hd/{k:04d}.png") for k in range(4)]
        cls.snapshot = json.loads((BACKUP / "snapshot.json").read_text("utf-8"))

    def test_entire_native_boot_and_ankle_region_is_fixed(self):
        # Includes both boots, their ankles, exterior transparent pixels and a
        # margin above the previously moving y324 cross-section. A fixed sole
        # alone would not pass this check.
        foot_box = (220, 323, 265, 339)
        expected = crop(self.before_native[0], foot_box)
        self.assertGreater(int(np.count_nonzero(expected[..., 3])), 80)
        for k, frame in enumerate(self.native):
            with self.subTest(frame=k):
                np.testing.assert_array_equal(crop(frame, foot_box), expected)
        # Both recognizable shoe lobes remain, not a flattened single blob.
        for x0, x1 in ((231, 242), (242, 252)):
            self.assertGreater(int(np.count_nonzero(self.native[0][325:337, x0:x1, 3])), 8)

    def test_hd_boots_are_fixed_before_downsampling(self):
        # The shoe tops begin around source y489. Include a 19px upper margin,
        # the entire width and all remaining rows, so the ankles are also fixed
        # before downsampling rather than pasted over the final small pixels.
        first_row = 470
        expected = self.before_hd[0][first_row:]
        for k, frame in enumerate(self.hd):
            with self.subTest(frame=k):
                np.testing.assert_array_equal(frame[first_row:], self.hd[0][first_row:])
                delta = np.abs(frame[first_row:].astype(np.int16) - expected.astype(np.int16))
                # Old sway(phase=0) premultiplied and unpremultiplied even still
                # pixels, clearing hidden RGB at alpha zero. Compare alpha
                # exactly and visible RGB with at most one byte of rounding;
                # invisible background RGB does not describe the shoe's color.
                np.testing.assert_array_equal(frame[first_row:, ..., 3], expected[..., 3])
                visible = expected[..., 3] > 0
                self.assertLessEqual(int(delta[visible, :3].max()), 1)

    def test_accepted_idle_frames_match_recorded_output(self):
        # Scope of the original repair (139 untouched frames) is recorded in
        # its report. Later authorized motion repairs may change those other
        # actions; this regression must protect the accepted idle itself.
        recorded = self.snapshot["native_file_sha256"]
        self.assertEqual(len(recorded), 143)
        report = json.loads((BACKUP.parent / "repair_report.json").read_text("utf-8"))
        self.assertEqual(report["unchanged_other_frames"], 139)
        for k, expected in enumerate(report["native_sha256"]):
            with self.subTest(frame=k):
                path = OUT / f"native_frames/{k:04d}.png"
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_world_scale_and_placement_are_unchanged(self):
        old = json.loads((BACKUP / "selection.json").read_text("utf-8"))
        new = json.loads((OUT / f"clips/{CLIP}/selection.json").read_text("utf-8"))
        self.assertEqual(new["window"], old["window"])
        self.assertEqual(new["base_scale"], old["base_scale"])
        self.assertEqual([row["slot"] for row in new["frames"]], list(range(4)))
        for a, b in zip(old["frames"], new["frames"]):
            with self.subTest(frame=b["slot"]):
                for key in ("scale", "offset", "track", "offset_before_ground", "hands"):
                    self.assertEqual(b.get(key), a.get(key), key)

    def test_clothes_and_hair_still_move_through_all_four_transitions(self):
        # These ROIs were chosen from the source drawing, independently of the
        # repair's displacement masks. They exclude the locked feet.
        regions = {
            "upper_body_and_sleeves": (194, 133, 312, 310),
            "hanging_hair": (153, 160, 225, 363),
            "skirt": (145, 310, 365, 475),
        }
        for name, box in regions.items():
            reference = crop(self.hd[0], box)
            differences = [changed(crop(frame, box), reference) for frame in self.hd[1:]]
            with self.subTest(region=name):
                self.assertGreater(max(differences), 100)
        for k in range(4):
            j = (k + 1) % 4
            with self.subTest(transition=f"{k}->{j}"):
                self.assertGreater(changed(self.hd[k], self.hd[j]), 200)
                self.assertGreater(changed(self.native[k], self.native[j]), 10)

    def test_micro_motion_keeps_silhouette_solid_and_small(self):
        old_solid = self.before_native[0][..., 3] > 128
        core = ndimage.distance_transform_edt(old_solid) > 3
        self.assertGreater(int(np.count_nonzero(core)), 1000)
        original_area = int(old_solid.sum())
        centers = []
        for k, frame in enumerate(self.native):
            with self.subTest(frame=k):
                self.assertEqual(frame.shape, (500, 500, 4))
                self.assertEqual(set(np.unique(frame[..., 3])), {0, 255})
                solid = frame[..., 3] > 128
                _, components = ndimage.label(solid, np.ones((3, 3)))
                self.assertEqual(components, 1)
                self.assertTrue(np.all(solid[core]), "An interior hole appeared")
                self.assertLess(abs(int(solid.sum()) - original_area) / original_area, 0.04)
                centers.append(np.asarray(ndimage.center_of_mass(solid)))
        for k in range(4):
            self.assertLess(float(np.linalg.norm(centers[k] - centers[(k + 1) % 4])), 1.5)


if __name__ == "__main__":
    unittest.main()
