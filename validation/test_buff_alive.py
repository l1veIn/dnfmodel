"""Independent pixel/transport checks for the actual v05 local-animation export.

Run after build_buff_alive.py. No generation, encoding changes or game writes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

import av
import numpy as np
from PIL import Image, ImageSequence
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_buff_alive as alive


class ActualPortrait(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / "design/claude_gunner/buff_v05.json").read_text("utf-8"))
        cls.output = ROOT / cls.cfg["output"]
        cls.manifest = json.loads((cls.output / "manifest.json").read_text("utf-8"))
        cls.frames = np.stack([np.array(Image.open(cls.output / "frames" / f"frame_{k:04d}.png").convert("RGBA")) for k in range(19)])
        cls.base = np.array(Image.open(cls.output / "static_base.png").convert("RGBA"))
        cls.fields = np.load(cls.output / "local_displacement.npz")["xy"]
        cls.protected = np.array(Image.open(cls.output / "motion_masks/protected.png")) > 0
        cls.eyes = np.maximum.reduce([np.array(Image.open(cls.output / "motion_masks" / f"eye_{name}.png")) for name in ("viewer_left", "viewer_right")]) > 0

    def test_source_and_all_frame_hashes(self):
        source = ROOT / self.cfg["source"]
        self.assertEqual((self.output / "source.png").read_bytes(), source.read_bytes())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), self.manifest["source_raw_sha256"])
        for k, expected in enumerate(self.manifest["frame_sha256"]):
            self.assertEqual(hashlib.sha256((self.output / "frames" / f"frame_{k:04d}.png").read_bytes()).hexdigest(), expected)

    def test_static_camera_and_protected_identity(self):
        # Independently reproduce the one approved cover crop, with no pose.
        source = Image.open(ROOT / self.cfg["source"]).convert("RGBA")
        scale = 470 / 1024
        expected = source.transform((470, 668), Image.Transform.AFFINE,
                                    (1 / scale, 0, 512 - 235 / scale,
                                     0, 1 / scale, 768 - 334 / scale),
                                    Image.Resampling.BICUBIC, fillcolor=0)
        np.testing.assert_array_equal(self.base, np.array(expected))
        np.testing.assert_array_equal(self.frames[0], self.base)
        np.testing.assert_array_equal(self.frames[-1], self.base)
        static = self.protected & ~self.eyes
        self.assertGreater(np.count_nonzero(static), 100_000)
        for frame in self.frames:
            np.testing.assert_array_equal(frame[static], self.base[static])
        np.testing.assert_array_equal(self.fields[:, self.protected], 0)
        cameras = [x["camera"] for x in self.manifest["frame_metrics"]]
        self.assertTrue(all(camera == cameras[0] for camera in cameras))

    def test_local_bounded_nonrigid_motion_without_fold(self):
        field = self.fields
        self.assertEqual(field.shape, (19, 668, 470, 2))
        magnitude = np.linalg.norm(field, axis=-1)
        self.assertGreater(float(magnitude.max()), 1)
        self.assertLessEqual(float(magnitude.max()), 3)
        np.testing.assert_array_equal(field[0], 0)
        np.testing.assert_array_equal(field[-1], 0)
        # Stationary interior plus a spatially varying field rules out a rigid
        # whole-image push/pull, translation, or duplicated drifting overlay.
        self.assertGreater(np.count_nonzero(magnitude.max(axis=0) == 0), 150_000)
        self.assertGreater(float(np.std(field[13, ..., 0])), 0.05)
        dxdy, dxdx = np.gradient(field[..., 0], axis=(1, 2))
        dydy, dydx = np.gradient(field[..., 1], axis=(1, 2))
        jacobian = (1 - dxdx) * (1 - dydy) - dxdy * dydx
        self.assertGreater(float(jacobian.min()), 0.5)
        self.assertLess(float(jacobian.max()), 1.6)
        self.assertLess(float(np.linalg.norm(np.diff(field, axis=0), axis=-1).max()), 1)
        # Each configured hair/cloth mask must actually change, with a fixed
        # zero-weight boundary or root. This prevents an inert cosmetic mask.
        for cfg in self.cfg["local_motion"]:
            mask = np.array(Image.open(self.output / "motion_masks" / f"{cfg['name']}.png")) > 64
            with self.subTest(region=cfg["name"]):
                self.assertGreater(np.count_nonzero(mask), 20)
                self.assertGreater(float(magnitude[:, mask].max()), 0.1)
                self.assertGreater(np.count_nonzero(np.any(self.frames[:, mask] != self.base[mask], axis=(0, 2))), 10)

    def test_blink_is_short_local_and_replaces_iris(self):
        sequence = [m["blink"] for m in self.manifest["frame_metrics"]]
        self.assertEqual([i for i, name in enumerate(sequence) if name == "closed"], [8])
        self.assertEqual([i for i, name in enumerate(sequence) if name == "half"], [7, 9])
        for k in (7, 8, 9):
            # No generated alpha, no changed eyebrows, nose, mouth, forehead or
            # other face pixels. Only eye RGB can change within the protected head.
            np.testing.assert_array_equal(self.frames[k, ..., 3][self.protected], self.base[..., 3][self.protected])
            self.assertGreater(np.count_nonzero(np.any(self.frames[k, self.eyes, :3] != self.base[self.eyes, :3], axis=1)), 500)
        # Small independently chosen iris interiors, mapped from original source
        # centers: warm saturated amber must recede when the lids close.
        for x0, y0, x1, y1 in ((226, 93, 237, 101), (282, 112, 292, 122)):
            def amber(frame):
                roi = frame[y0:y1, x0:x1].astype(np.int16)
                return np.count_nonzero((roi[..., 0] - roi[..., 2] > 90) & (roi[..., 1] > 65))
            self.assertLess(amber(self.frames[8]), amber(self.frames[0]) * 0.65)
        self.assertGreater(np.count_nonzero(self.frames[7, self.eyes, :3] != self.frames[8, self.eyes, :3]), 100)

    def test_no_transparency_holes_in_opaque_interior(self):
        # A four-pixel interior margin exceeds every configured displacement.
        interior = distance_transform_edt(self.base[..., 3] > 245) > 4
        self.assertGreater(np.count_nonzero(interior), 100_000)
        for frame in self.frames:
            self.assertGreater(int(frame[..., 3][interior].min()), 240)
            self.assertEqual(int(frame[..., 3].min()), 0)
            self.assertGreater(np.count_nonzero(frame[..., 3] > 240), 150_000)

    def test_mov_and_webp_roundtrip(self):
        with av.open(str(self.output / "portrait_rgba.mov")) as mov:
            self.assertEqual(mov.streams.video[0].average_rate, 15)
            decoded = np.stack([frame.to_ndarray(format="rgba") for frame in mov.decode(video=0)])
        np.testing.assert_array_equal(decoded, self.frames)
        with Image.open(self.output / "preview.webp") as webp:
            self.assertEqual(webp.n_frames, 19)
            for k, image in enumerate(ImageSequence.Iterator(webp)):
                got = np.array(image.convert("RGBA"))
                np.testing.assert_array_equal(got[..., 3], self.frames[k, ..., 3])
                visible = self.frames[k, ..., 3] > 0
                np.testing.assert_array_equal(got[visible, :3], self.frames[k, visible, :3])

    def test_missing_eye_artwork_fails_before_export(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["blink"]["states"]["closed"]["path"] = "output/this-eye-artwork-does-not-exist.png"
        with self.assertRaisesRegex(FileNotFoundError, "not exporting a blink placeholder"):
            alive.render(cfg, Image.open(ROOT / cfg["source"]).convert("RGBA"))


if __name__ == "__main__":
    unittest.main()
