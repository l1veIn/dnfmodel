"""Check optional addon discovery with a synthetic local workspace."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/workbench")]
import addons
from dnf_resources import write_npk, write_v2

PORTRAIT = "sprite/interface2/charactercreatever2/characterillust/magef.img"


class WorkbenchAddonTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix="workbench-addons-")
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name).resolve()
        self.registry = self.root / "design/workbench_addons.json"
        self.registry.parent.mkdir()
        self.manifest = self.root / "output/addon/manifest.json"
        self.package = self.manifest.with_name("A_Addon_v01.NPK")
        self.enterContext(patch.object(addons, "ROOT", self.root))
        self.enterContext(patch.object(addons, "REGISTRY", self.registry))
        self.enterContext(patch.object(addons, "GAME", self.root / "game"))
        self.enterContext(patch.object(addons.categories, "portrait_paths", return_value=[PORTRAIT]))
        self.addCleanup(addons.reset)
        self.write_registry("output/addon/manifest.json")
        payload = write_v2([Image.new("RGBA", (2, 2), (130, 80, 40, 255))],
                           [dict(x=0, y=0, canvas_width=2, canvas_height=2)])
        self.content = write_npk([(PORTRAIT, payload)])
        self.meta = dict(schema=1, id="portraits", status="user_approved", edits=[
            dict(path=PORTRAIT, frame_count=1, changed_frames=[0],
                 payload_sha256=hashlib.sha256(payload).hexdigest(), source_payload_sha256="0" * 64,
                 project_targets={"mage_test": [0]})],
            npk="output/addon/A_Addon_v01.NPK", sha256=hashlib.sha256(self.content).hexdigest(),
            projects={"mage_test": {PORTRAIT: [0]}})
        self.project = dict(id="mage_test", profession="mage")

    def write_registry(self, manifest):
        self.registry.write_text(json.dumps(dict(schema=1, addons=[
            dict(id="portraits", manifest=manifest)])), encoding="utf-8")

    def write_manifest(self, **overrides):
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        self.manifest.write_text(json.dumps({**self.meta, **overrides}), encoding="utf-8")

    def test_unbuilt_addon_is_omitted_until_both_files_appear(self):
        self.assertEqual(addons.for_project(self.project), [])
        self.assertEqual(addons.cache_token()[1], ())
        with self.assertRaises(KeyError):
            addons.file_for_project(self.project, "portraits")

        self.write_manifest()
        self.assertEqual(addons.for_project(self.project), [])
        self.assertEqual(addons.cache_token()[1], ())
        with self.assertRaises(KeyError):
            addons.file_for_project(self.project, "portraits")

        self.package.write_bytes(self.content)
        listing = addons.for_project(self.project)
        self.assertEqual([row["id"] for row in listing], ["portraits"])
        self.assertEqual(len(addons.cache_token()[1]), 1)
        self.assertEqual(addons.file_for_project(self.project, "portraits"), self.package.resolve())

    def test_invalid_manifest_path_is_rejected_even_when_absent(self):
        self.write_registry("design/missing.json")
        with self.assertRaisesRegex(ValueError, "inside workspace output"):
            addons.for_project(self.project)

    def test_existing_manifest_is_checked_when_package_is_absent(self):
        for overrides, message in (
            ({"schema": 2}, "packaged addon manifest"),
            ({"id": "wrong"}, "ID differs"),
            ({"npk": "design/A_Missing.NPK"}, "inside workspace output"),
            ({"sha256": "invalid"}, "declare a SHA-256"),
        ):
            with self.subTest(overrides=overrides):
                self.write_manifest(**overrides)
                with self.assertRaisesRegex(ValueError, message):
                    addons.for_project(self.project)

    def test_existing_package_with_wrong_digest_is_rejected(self):
        self.write_manifest()
        self.package.write_bytes(self.content + b"corrupt")
        with self.assertRaisesRegex(ValueError, "hash differs"):
            addons.for_project(self.project)


if __name__ == "__main__":
    unittest.main()
