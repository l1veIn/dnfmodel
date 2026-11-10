"""Pixel/shape regression for the two corrected rear-reaching reload arms."""
from pathlib import Path
import hashlib
import json
import unittest

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "output/validation/claude_motion_review_2026-11-09/reload"
OUT = ROOT / "output/Claude_Gunner_v02"


def rgba(path):
    return np.asarray(Image.open(path).convert("RGBA"))


class ReloadArms(unittest.TestCase):
    def test_fixed_head_front_hand_and_lower_body(self):
        for k in (4,5):
            with self.subTest(frame=k):
                old = rgba(WORK / f"before/native_{k:04d}.png")
                new = rgba(OUT / f"native_frames/{k:04d}.png")
                np.testing.assert_array_equal(new[:238], old[:238])
                np.testing.assert_array_equal(new[290:], old[290:])
                np.testing.assert_array_equal(new[245:286,237:275], old[245:286,237:275])
                hd = rgba(OUT / f"clips/clip_004_009/hd/{k:04d}.png")
                original = rgba(WORK / f"before/hd_{k:04d}.png")
                mask = np.asarray(Image.open(WORK / f"staged/mask_{k:04d}.png")) > 0
                np.testing.assert_array_equal(hd[~mask], original[~mask])

    def test_old_downward_open_hand_is_removed(self):
        for k in (4,5):
            with self.subTest(frame=k):
                old = rgba(WORK / f"before/native_{k:04d}.png")
                new = rgba(OUT / f"native_frames/{k:04d}.png")
                def bright_pixels(array):
                    roi = array[265:285,208:227].astype(np.int16)
                    return int(((roi[...,3]>128)&(roi[...,0]>145)&(roi[...,1]>130)&(roi[...,2]>80)).sum())
                self.assertLess(bright_pixels(new), bright_pixels(old)*0.65)
                changed = np.any(old != new,axis=2)
                self.assertGreater(int(changed.sum()),50)
                self.assertLess(int(changed.sum()),1200)
                ys,xs=np.nonzero(changed)
                self.assertTrue(np.all((xs>=200)&(xs<240)&(ys>=238)&(ys<290)))

    def test_no_detached_hand_and_placement_is_unchanged(self):
        current = OUT / "clips/clip_004_009/selection.json"
        self.assertEqual(current.read_bytes(),(WORK / "before/selection.json").read_bytes())
        for k in (4,5):
            with self.subTest(frame=k):
                image = rgba(OUT / f"native_frames/{k:04d}.png")
                self.assertEqual(set(np.unique(image[...,3])),{0,255})
                _, count = ndimage.label(image[...,3]>128,np.ones((3,3)))
                self.assertEqual(count,1)

    def test_final_pixels_are_bound_to_local_review(self):
        report=json.loads((WORK / "repair_report.json").read_text("utf-8"))
        self.assertTrue(report["applied"])
        for item in report["frames"]:
            path=OUT / f"native_frames/{item['tool_frame']:04d}.png"
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),item["native_sha256"])
        self.assertTrue((ROOT / "design/claude_gunner/reload_repair_prompts.txt").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
