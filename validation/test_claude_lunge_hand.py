"""Independent checks of the published lunge's bounded hand fitting."""
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
CLIP = OUT / "clips/clip_052_059"
WORK = ROOT / "output/validation/claude_motion_review_2026-11-09/lunge"
BEFORE = WORK / "before"
SLOTS = (56, 57, 58)


def rgba(path):
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA")).copy()


class LocalLungeHand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((BEFORE / "selection.json").read_text("utf-8"))
        cls.raw = {k: rgba(CLIP / f"hd/{k:04d}.png") for k in SLOTS}
        cls.fixed = {k: rgba(CLIP / f"hdfit/{k:04d}.png") for k in SLOTS}
        cls.native = {k: rgba(OUT / f"native_frames/{k:04d}.png") for k in SLOTS}

    def test_approved_hd_and_world_placement_unchanged(self):
        current = json.loads((CLIP / "selection.json").read_text("utf-8"))
        self.assertEqual(current["window"], self.report["window"])
        for k in SLOTS:
            with self.subTest(frame=k):
                self.assertEqual(next(r for r in current["frames"] if r["slot"] == k),
                                 next(r for r in self.report["frames"] if r["slot"] == k))
                self.assertEqual((CLIP / f"hd/{k:04d}.png").read_bytes(), (BEFORE / f"hd/{k:04d}.png").read_bytes())

    def test_head_hair_waist_gown_and_boots_match_raw_drawing(self):
        for k in SLOTS:
            a, b = self.raw[k], self.fixed[k]
            with self.subTest(frame=k):
                np.testing.assert_array_equal(b[300:], a[300:])
                np.testing.assert_array_equal(b[:, :214], a[:, :214])
                np.testing.assert_array_equal(b[150:223, 170:255], a[150:223, 170:255])
                np.testing.assert_array_equal(b[282:320, 180:310], a[282:320, 180:310])
                # The hand fit itself must remain; merely reverting the entire
                # HD to the unaligned source would also remove the bad foot.
                changed_arm = np.any(b[190:282, 255:400] != a[190:282, 255:400], axis=2)
                self.assertGreater(int(changed_arm.sum()), 1000)

    def test_native_lower_body_restored_without_ghost(self):
        for k in SLOTS:
            reference = rgba(WORK / f"staged/raw_native/{k:04d}.png")
            old = rgba(BEFORE / f"native_frames/{k:04d}.png")
            with self.subTest(frame=k):
                np.testing.assert_array_equal(self.native[k][280:], reference[280:])
                self.assertGreater(int(np.any(old[280:] != reference[280:], axis=2).sum()), 100)

    def test_native_contact_pixels_stay_at_existing_grip(self):
        for k in SLOTS:
            row = next(r for r in self.report["frames"] if r["slot"] == k)
            x, y = row["hands"][0]["target"]
            old = rgba(BEFORE / f"native_frames/{k:04d}.png")
            new = self.native[k]
            with self.subTest(frame=k):
                np.testing.assert_array_equal(new[y-3:y+4, x-3:x+4], old[y-3:y+4, x-3:x+4])
                self.assertGreater(int(np.count_nonzero(new[y-3:y+4, x-3:x+4, 3])), 20)

    def test_two_boots_and_no_detached_finger_or_floaters(self):
        for k in SLOTS:
            with self.subTest(frame=k):
                solid = self.fixed[k][..., 3] > 128
                _, components = ndimage.label(solid, np.ones((3, 3)))
                self.assertEqual(components, 1)
                # Below the frilled hem the approved drawing has exactly two
                # separated shoe silhouettes, one on each side of the lunge.
                labels, _ = ndimage.label(solid[520:], np.ones((3, 3)))
                sizes = np.bincount(labels.ravel())[1:]
                self.assertEqual(int((sizes > 8).sum()), 2)
                native_solid = self.native[k][..., 3] > 128
                _, count = ndimage.label(native_solid, np.ones((3, 3)))
                self.assertEqual(count, 1)
                self.assertEqual(set(np.unique(self.native[k][..., 3])), {0, 255})

    def test_accepted_fit_and_untouched_neighbours_are_preserved(self):
        hashes = json.loads((BEFORE / "clip_native_sha256.json").read_text("utf-8"))
        # Frames 53-55 have a later authorized back-facing redraw. Guard the
        # two remaining neighbours and the exact accepted local-fit outputs.
        for k in (52, 59):
            with self.subTest(frame=k):
                path = OUT / f"native_frames/{k:04d}.png"
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), hashes[str(k)])
        repaired = json.loads((WORK / "repair_report.json").read_text("utf-8"))
        for row in repaired["frames"]:
            path = OUT / f"native_frames/{row['slot']:04d}.png"
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["output_native_sha256"])


if __name__ == "__main__":
    unittest.main()
