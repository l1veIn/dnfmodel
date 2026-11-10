"""Registration boundaries and derived status for project buff assets; no game writes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts" / "workbench"), str(ROOT / "scripts")]
import buff


class BuffAssets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnf_buff_api_")
        self.paths = buff.ROOT, buff.OUTPUT, buff.DESIGN
        buff.ROOT = Path(self.temp.name)
        buff.OUTPUT, buff.DESIGN = buff.ROOT / "output", buff.ROOT / "design"
        self.out = buff.OUTPUT / "portrait_v1" / "preview"
        (self.out / "frames").mkdir(parents=True)
        self.registration = buff.DESIGN / "sample" / "workbench" / "buff.json"
        self.registration.parent.mkdir(parents=True)
        self.entry = dict(id="portrait", name="sample buff", version="v1", manifest="output/portrait_v1/preview/manifest.json")
        self.write(self.registration, {"assets": [self.entry]})
        self.manifest = {"frames": 2, "size": [470, 668], "fps": 15, "targets": [],
                         "frame_sha256": [hashlib.sha256(b"fixture").hexdigest()] * 2}
        self.write(self.out / "manifest.json", self.manifest)
        for name in ("preview.webp", "sheet.png", "contact.jpg", "portrait_rgba.mov", "frames/frame_0000.png", "frames/frame_0001.png"):
            (self.out / name).write_bytes(b"fixture")
        self.project = dict(id="sample", current="sample", designs=["sample"], profession="gunner_at")

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), "utf-8")

    def tearDown(self):
        buff.ROOT, buff.OUTPUT, buff.DESIGN = self.paths
        self.temp.cleanup()

    def encoded(self, **overrides):
        (self.out / "portrait.bik").write_bytes(b"BIKi" + b"fixture for status derivation only")
        self.report = dict(status="encoded", file="portrait.bik", codec="binkvideo", width=470, height=668,
                           frames=2, fps=15, alpha=True, audio_streams=0, verified=True,
                           sha256=hashlib.sha256((self.out / "portrait.bik").read_bytes()).hexdigest())
        self.report.update(overrides)
        self.write(self.out / "encoding_report.json", self.report)

    def installed(self):
        self.encoded()
        self.game = buff.ROOT / "game" / "Video" / "Character"
        self.game.mkdir(parents=True)
        self.manifest["targets"] = ["Cutscene_buf/one.bk2", "Cutscene_buf/two.bk2"]
        self.write(self.out / "manifest.json", self.manifest)
        movie = self.out / "portrait.bik"
        digest = hashlib.sha256(movie.read_bytes()).hexdigest()
        rows = []
        for relative in self.manifest["targets"]:
            target = self.game / relative
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(movie.read_bytes())
            rows.append(dict(relative=relative, target=str(target), after_sha256=digest))
        self.receipt = dict(installed=True, source=str(movie), sha256=digest, game_root=str(self.game),
                            installed_at="2026-11-09T20:00:00", files=rows, ingame_verified=True)
        self.receipt_path = self.out.parent / "installation.json"
        self.write(self.receipt_path, self.receipt)
        self.root_patch = patch.object(buff, "_video_root", return_value=self.game.resolve())
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_prepared_metadata_and_known_files(self):
        self.assertEqual(buff.count(self.project), 1)
        asset = buff.assets(self.project)[0]
        self.assertEqual((asset["frames"], asset["width"], asset["height"], asset["status"]), (2, 470, 668, "prepared"))
        self.assertIn("k={k}", asset["frame_url"])
        self.assertIsNone(asset["files"]["bink"])
        self.assertEqual(buff.file(self.project, "portrait", "frame", 1), self.out / "frames/frame_0001.png")
        self.assertFalse(asset["ingame_verified"])
        self.assertFalse(asset["installed"])
        for kind in ("animation", "sheet", "contact", "mov", "manifest"):
            self.assertTrue(buff.file(self.project, "portrait", kind).is_file())

    def test_status_tracks_encoding_and_invalidated_hash(self):
        self.encoded()
        asset = buff.detail(self.project, "portrait")
        self.assertEqual(asset["status"], "encoded")
        self.assertFalse(asset["ingame_verified"])
        self.assertEqual(buff.file(self.project, "portrait", "bink").name, "portrait.bik")
        (self.out / "portrait.bik").write_bytes(b"BIKi" + b"changed bytes")
        self.assertEqual(buff.detail(self.project, "portrait")["status"], "prepared")
        with self.assertRaises(KeyError):
            buff.file(self.project, "portrait", "bink")

    def test_codec_alpha_dimensions_and_report_must_match(self):
        for change in ({"verified": False}, {"alpha": False}, {"codec": "qtrle"}, {"frames": 19}, {"fps": 10}, {"audio_streams": 1}):
            with self.subTest(change=change):
                self.encoded(**change)
                self.assertEqual(buff.detail(self.project, "portrait")["status"], "prepared")
        self.encoded()
        (self.out / "portrait.bik").write_bytes(b"MOV!")
        self.assertEqual(buff.detail(self.project, "portrait")["status"], "prepared")

    def test_changed_source_png_invalidates_encoding_status(self):
        self.encoded()
        before = buff.detail(self.project, "portrait")
        self.assertEqual(before["status"], "encoded")
        (self.out / "frames/frame_0000.png").write_bytes(b"a changed source frame")
        after = buff.detail(self.project, "portrait")
        self.assertEqual(after["status"], "prepared")
        self.assertNotEqual(before["stamp"], after["stamp"])
        with self.assertRaises(KeyError):
            buff.file(self.project, "portrait", "bink")

    def test_only_registered_assets_and_bounded_frames(self):
        for ident in ("missing", "../portrait", "portrait/../../"):
            with self.assertRaises((ValueError, KeyError)):
                buff.file(self.project, ident, "animation")
        for k in (-1, 2, 2.0, True, None):
            with self.assertRaises(ValueError):
                buff.file(self.project, "portrait", "frame", k)
        for kind in ("../../secret", "frames/frame_0000.png", "unknown"):
            with self.assertRaises(KeyError):
                buff.file(self.project, "portrait", kind)
        other = dict(id="other", current=None, designs=[])
        self.assertEqual(buff.assets(other), [])

    def test_registration_and_encoding_paths_cannot_escape(self):
        self.entry["manifest"] = "output/../../secret/manifest.json"
        self.write(self.registration, {"assets": [self.entry]})
        self.assertEqual(buff.detail(self.project, "portrait")["status"], "unavailable")
        with self.assertRaises(ValueError):
            buff.file(self.project, "portrait", "manifest")
        self.entry["manifest"] = "output/portrait_v1/preview/manifest.json"
        self.write(self.registration, {"assets": [self.entry]})
        self.encoded(file="../outside.bik")
        self.assertEqual(buff.detail(self.project, "portrait")["status"], "unavailable")
        with self.assertRaises(ValueError):
            buff.file(self.project, "portrait", "bink")

    def test_missing_png_is_not_ready(self):
        (self.out / "frames/frame_0001.png").unlink()
        asset = buff.detail(self.project, "portrait")
        self.assertEqual(asset["status"], "unavailable")
        self.assertEqual(asset["available_frames"], 1)

    def test_installed_requires_actual_targets_and_never_claims_ingame_approval(self):
        self.installed()
        frozen_manifest = (self.out / "manifest.json").read_bytes()
        frozen_report = (self.out / "encoding_report.json").read_bytes()
        asset = buff.detail(self.project, "portrait")
        self.assertTrue(asset["installed"])
        self.assertEqual(asset["installation"]["matching_targets"], 2)
        self.assertEqual(asset["status"], "encoded")
        self.assertFalse(asset["ingame_verified"])
        self.assertEqual((self.out / "manifest.json").read_bytes(), frozen_manifest)
        self.assertEqual((self.out / "encoding_report.json").read_bytes(), frozen_report)

    def test_restored_or_missing_target_removes_installed_state(self):
        self.installed()
        target = self.game / self.manifest["targets"][0]
        target.write_bytes(b"restored official video")
        asset = buff.detail(self.project, "portrait")
        self.assertFalse(asset["installed"])
        self.assertEqual(asset["installation"]["status"], "partial")
        self.assertEqual(asset["installation"]["matching_targets"], 1)
        target.unlink()
        self.assertFalse(buff.detail(self.project, "portrait")["installed"])

    def test_install_accepts_manifest_target_records_with_official_hashes(self):
        self.installed()
        self.manifest["targets"] = [dict(relative_to_video_character=relative, official_sha256="a" * 64)
                                    for relative in self.manifest["targets"]]
        self.write(self.out / "manifest.json", self.manifest)
        self.assertTrue(buff.detail(self.project, "portrait")["installed"])

    def test_install_receipt_cannot_follow_changed_source_or_different_target_set(self):
        self.installed()
        # A newly verified encoding does not retroactively update an old receipt.
        self.encoded(sha256=hashlib.sha256(b"BIKi" + b"new encoding").hexdigest())
        (self.out / "portrait.bik").write_bytes(b"BIKi" + b"new encoding")
        asset = buff.detail(self.project, "portrait")
        self.assertEqual(asset["status"], "encoded")
        self.assertFalse(asset["installed"])
        self.assertEqual(asset["installation"]["status"], "stale")

    def test_install_receipt_must_cover_registered_paths_in_configured_game_root(self):
        self.installed()
        self.receipt["files"][0]["target"] = str(buff.ROOT / "outside.bk2")
        self.write(self.receipt_path, self.receipt)
        asset = buff.detail(self.project, "portrait")
        self.assertFalse(asset["installed"])
        self.assertEqual(asset["installation"]["status"], "invalid")
        self.receipt["files"] = self.receipt["files"][:1]
        self.write(self.receipt_path, self.receipt)
        self.assertFalse(buff.detail(self.project, "portrait")["installed"])


class CurrentAssets(unittest.TestCase):
    def test_registered_real_sheet_is_19_frames(self):
        project = json.loads((ROOT / "design/projects.json").read_text("utf-8"))["projects"][1]
        asset = buff.detail(project, "portrait")
        self.assertEqual((asset["frames"], asset["width"], asset["height"], asset["fps"]), (19, 470, 668, 15))
        self.assertEqual(asset["available_frames"], 19)
        self.assertIn(asset["status"], ("prepared", "encoded"))
        from PIL import Image
        for k in (0, 18):
            with Image.open(buff.file(project, "portrait", "frame", k)) as image:
                self.assertEqual((image.mode, image.size), ("RGBA", (470, 668)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
