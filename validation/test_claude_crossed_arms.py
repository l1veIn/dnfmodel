"""Read-only raster checks for the four newly drawn chest-crossing frames.

Default: verify actual workbench assets after publication. During visual review,
CLAUDE_CROSSED_REVIEW=settled checks staged 65-67; =full checks all staged frames.
These checks cannot decide which shoulder an arm comes from. That decision must
be made from the weapon-overlay contact sheet and the original arm-path guide.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import unittest

import numpy as np
from PIL import Image
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/Claude_Gunner_v02"
WORK = ROOT / "output/validation/claude_pose_correction_2026-11-09/hold_cross"
REVIEW = os.environ.get("CLAUDE_CROSSED_REVIEW", "")
STAGED = REVIEW in {"settled", "full"}
NATIVE = (WORK / "staged" if STAGED else OUT) / "native_frames"
CLIP = WORK / "staged" if STAGED else OUT / "clips/clip_064_067"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgba(path):
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA")).copy()


def bbox(frame):
    yy, xx = np.nonzero(frame[..., 3] > 128)
    return int(xx.min()), int(yy.min()), int(xx.max()+1), int(yy.max()+1)


class CrossedArms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = "settled_report.json" if REVIEW == "settled" else "repair_report.json"
        cls.report = json.loads((WORK / name).read_text("utf-8"))
        cls.rows = {row["slot"]: row for row in cls.report["frames"]}
        cls.frames = {slot: rgba(NATIVE / f"{slot:04d}.png") for slot in cls.rows}

    def test_native_rasters_match_reviewed_report(self):
        for slot, frame in self.frames.items():
            with self.subTest(slot=slot):
                self.assertEqual(frame.shape, (500, 500, 4))
                self.assertEqual(set(np.unique(frame[..., 3])), {0, 255})
                self.assertEqual(sha(NATIVE / f"{slot:04d}.png"), self.rows[slot]["native_sha256"])
                self.assertEqual(list(bbox(frame)), self.rows[slot]["new_bbox"])
                self.assertLessEqual(abs(bbox(frame)[3]-bbox(frame)[1]-(122 if slot == 64 else 123)), 1)
                self.assertLessEqual(abs(bbox(frame)[1]-(211 if slot == 64 else 210)), 1)

    def test_both_grips_touch_one_connected_body_without_large_stretch(self):
        for slot, frame in self.frames.items():
            with self.subTest(slot=slot):
                row = self.rows[slot]
                self.assertGreater(row["min_inverse_jacobian"], .4)
                labels, n = ndimage.label(frame[..., 3] > 128, np.ones((3, 3)))
                areas = np.bincount(labels.ravel())[1:]
                # Minute disconnected speed-line tips may survive downsampling;
                # a detached fist, shoe or duplicate leg may not.
                body = int(areas.argmax()+1)
                self.assertLessEqual(int(areas.sum()-areas.max()), 4)
                for hand in row["hands"]:
                    self.assertLessEqual(hand["gap"], 5)
                    x, y = np.round(hand["target"]).astype(int)
                    self.assertEqual(int(labels[y, x]), body)
                    self.assertGreaterEqual(int((frame[y-2:y+3, x-2:x+3, 3] > 128).sum()), 20)

    def test_settled_face_torso_height_and_lower_body_do_not_float(self):
        settled = [self.frames[slot] for slot in (65, 66, 67)]
        first = settled[0]
        self.assertGreater(int((first[210:232, 235:266, 3] > 128).sum()), 150)
        for frame in settled[1:]:
            np.testing.assert_array_equal(frame[210:232, 235:266], first[210:232, 235:266])
            np.testing.assert_array_equal(frame[280:], first[280:])
        placements = [self.rows[slot]["origin"] for slot in (65, 66, 67)]
        self.assertEqual(placements, [placements[0]]*3)

    def test_exactly_two_intact_shoes_near_original_stance(self):
        for slot, frame in self.frames.items():
            with self.subTest(slot=slot):
                _, shoes = ndimage.label(frame[325:, :, 3] > 128, np.ones((3, 3)))
                self.assertEqual(shoes, 2)
                # Original left sole333/right sole328. Outfit boots differ in
                # shape; these tolerances cover complete boots, not pasted toes.
                for x0, x1, source_x, sole, tolerance in (
                    (0, 240, 210.82, 333, 2.0),
                    (240, 500, 278.82, 328, 8.0),
                ):
                    yy, xx = np.nonzero(frame[320:, x0:x1, 3] > 128)
                    self.assertGreater(len(xx), 20)
                    bottom = int(yy.max()+321)
                    self.assertLessEqual(abs(bottom-sole), 1)
                    center = float(xx[yy >= yy.max()-7].mean()+x0)
                    self.assertLessEqual(abs(center-source_x), tolerance)

    def test_selection_describes_all_four_slots_without_rescaling_scene(self):
        old = json.loads((WORK / "before/selection.json").read_text("utf-8"))
        new = json.loads((CLIP / "selection.json").read_text("utf-8"))
        self.assertEqual([row["slot"] for row in new["frames"]], [64, 65, 66, 67])
        self.assertEqual(new["window"], old["window"])
        self.assertEqual(new["base_scale"], old["base_scale"])
        self.assertEqual(new["sheet"], "hold_crossed_arms")
        self.assertFalse(self.report["installed"])

    def test_previously_accepted_other_actions_are_preserved(self):
        snapshot = json.loads((WORK / "before/native_sha256.json").read_text("utf-8"))
        self.assertEqual(len(snapshot), 143)
        # The same user request separately authorized back-facing53-55. Those
        # are owned and verified by the other worker, not by this repair.
        authorized = {53, 54, 55, 64, 65, 66, 67}
        for name, expected in snapshot.items():
            if int(Path(name).stem) not in authorized:
                with self.subTest(frame=name):
                    self.assertEqual(sha(OUT / "native_frames" / name), expected)


if __name__ == "__main__":
    unittest.main()
