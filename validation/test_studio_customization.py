"""Run with the project's Python. Synthetic NPKs; never touches the game or real wardrobe."""
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts" / "workbench"), str(ROOT / "scripts")]
import customize
import render
import studio
from dnf_resources import IMG_MAGIC, write_npk, write_v2


def indexed(version=4):
    payload = zlib.compress(bytes([1, 1, 0, 0]))
    frame = struct.pack("<9i", 14, 6, 2, 2, len(payload), 10, 20, 500, 500)
    return IMG_MAGIC + struct.pack("<QII", 36 * 3, version, 3) + (struct.pack("<i", 1) if version == 6 else b"") + struct.pack("<i", 2) + bytes([0, 0, 0, 0, 255, 0, 0, 255]) + frame * 3 + payload * 3


class CustomizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        meta = [dict(x=10, y=20, canvas_width=500, canvas_height=500)] * 3
        body = write_v2([Image.new("RGBA", (4, 4), (80, 80, 80, 255))] * 3, meta)
        pants_meta = [dict(x=12, y=22, canvas_width=500, canvas_height=500)] * 3
        pants = write_v2([Image.new("RGBA", (2, 2), (0, 40, 255, 255))] * 3, pants_meta)
        self.source = self.base / "fixture.NPK"
        self.source.write_bytes(write_npk([("body.img", body), ("coat.img", indexed()), ("coat6.img", indexed(6)), ("pants.img", pants)]))
        self.layers = [dict(path=path, source=str(self.source), slot=slot, z=z, palette=0, tag=slot, name=slot, item_id=slot)
                       for path, slot, z in [("body.img", "skin", 0), ("coat.img", "coat", 100), ("pants.img", "pants", 200)]]

        def plan(prof, outfit, overlay=""):
            layers = [dict(l) for l in self.layers]
            if isinstance(overlay, list):
                for l in layers:
                    for src in overlay:
                        if l["path"] in render.npk_entries(str(src)):
                            l["source"] = str(src)
            return dict(layers=layers, frames=3, hidden=[], missing=[])

        for p in [patch.object(studio, "role", lambda p: {"role": p, "frames": 3}), patch.object(studio, "plan", plan),
                  patch.object(studio, "ROOT", self.base), patch.object(studio, "WARDROBE", self.base / "wardrobe.json"), patch.object(studio, "EXPORTS", self.base / "exports"),
                  patch.object(render, "CACHE", self.base / "cache")]:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(render.reset)
        self.outfit = {"coat": "coat", "pants": "pants"}

    def test_default_is_unchanged_and_keys_include_recipe(self):
        plain = studio.compose("fixture", self.outfit)
        empty = studio.compose("fixture", self.outfit, customization={})
        self.assertEqual(plain["key"], empty["key"])
        self.assertEqual(studio.atlas("fixture", self.outfit), studio.atlas("fixture", self.outfit, customization={}))
        altered = studio.compose("fixture", self.outfit, customization={"dyes": {"coat": {"hue": 120}}})
        self.assertNotEqual(plain["key"], altered["key"])

    def test_indexed_palette_changes_only_selected_slot_without_mutation(self):
        plain = studio.compose("fixture", self.outfit)
        dyed = studio.compose("fixture", self.outfit, customization={"dyes": {"coat": {"colors": [{"from": "#ff0000", "to": "#00ff00"}]}}})
        box = tuple(plain["box"])
        before, after = studio._one_frame(plain, box, 0), studio._one_frame(dyed, box, 0)
        at = lambda p: (p[0] - box[0], p[1] - box[1])
        self.assertEqual(before.getpixel(at((10, 20))), (255, 0, 0, 255))
        self.assertEqual(after.getpixel(at((10, 20))), (0, 255, 0, 255))
        self.assertEqual(before.getpixel(at((12, 22))), after.getpixel(at((12, 22))))
        self.assertEqual(render.load_img(str(self.source), "coat.img").palettes[0][1], [255, 0, 0, 255])
        v6 = dict(self.layers[1], path="coat6.img")
        self.assertEqual(customize.layer_frame(v6, 0, box, dyed["customization"]["dyes"]).getpixel(at((10, 20))), (0, 255, 0, 255))
        self.assertEqual(render.load_img(str(self.source), "coat6.img").palettes[0][1], [255, 0, 0, 255])

    def test_semtransparent_pixel_save_reload_and_exact_export(self):
        recipe = {"dyes": {"coat": {"hue": 120}}, "pixels": [
            {"frame": 1, "x": 11, "y": 22, "color": "#ffaa2280"},
            {"frame": 1, "x": 10, "y": 20, "color": "#00000000"}]}
        entry = studio.save_outfit(dict(name="translucent", role="fixture", outfit=self.outfit, customization=recipe))
        loaded = studio.wardrobe()["outfits"][0]
        self.assertEqual(entry["customization"], loaded["customization"])
        p = studio.compose("fixture", self.outfit, customization=loaded["customization"])
        box = p["box"]
        frames = studio._frames(p, box, 3)
        at = (11 - box[0], 22 - box[1])
        self.assertEqual(frames[1].getpixel(at), (255, 170, 34, 128))
        self.assertEqual(frames[0].getpixel(at), frames[2].getpixel(at))
        self.assertNotEqual(frames[0].getpixel(at), frames[1].getpixel(at))
        report = studio.export_outfit(dict(name="translucent", role="fixture", current=self.outfit, target=self.outfit, customization=loaded["customization"]))
        self.assertEqual(report["check"]["differing_pixels"], 0)
        self.assertEqual(report["check"]["max_rgba_delta"], 0)
        self.assertTrue(report["check"]["passed"])

    def test_source_alpha_is_not_squared_and_negative_offsets_are_clipped(self):
        src = self.base / "alpha.NPK"
        image = Image.new("RGBA", (2, 2), (200, 100, 50, 128))
        meta = [dict(x=-1, y=-1, canvas_width=4, canvas_height=4)]
        src.write_bytes(write_npk([("alpha.img", write_v2([image], meta))]))
        result = render.frame(str(src), "alpha.img", 0, (0, 0, 2, 2))
        self.assertEqual(result.getpixel((0, 0)), (200, 100, 50, 128))
        self.assertEqual(result.getpixel((1, 1)), (0, 0, 0, 0))

    def test_sample_uses_original_indexed_color_after_dye_and_pixel_edits(self):
        recipe = {"dyes": {"coat": {"hue": 120}}, "pixels": [{"frame": 0, "x": 10, "y": 20, "color": "#123456ff"}]}
        payload = dict(role="fixture", outfit=self.outfit, customization=recipe, slot="coat", frame=0, x=10, y=20)
        sampled = studio.sample(payload)
        self.assertTrue(sampled["matched"])
        self.assertEqual((sampled["color"], sampled["alpha"], sampled["path"]), ("#ff0000", 255, "coat.img"))
        recipe = {"dyes": {"coat": {"hue": 120, "colors": [{"from": sampled["color"], "to": "#0000ff"}]}}}
        p = studio.compose("fixture", self.outfit, customization=recipe)
        self.assertEqual(studio._one_frame(p, p["box"], 0).getpixel((10 - p["box"][0], 20 - p["box"][1])), (0, 0, 255, 255))
        self.assertEqual(render.load_img(str(self.source), "coat.img").palettes[0][1], [255, 0, 0, 255])

    def test_sample_keeps_unblended_alpha_and_uses_top_layer_within_slot(self):
        source = self.base / "translucent.NPK"
        meta = [dict(x=10, y=20, canvas_width=500, canvas_height=500)] * 3
        source.write_bytes(write_npk([("top.img", write_v2([Image.new("RGBA", (2, 2), (240, 30, 60, 128))] * 3, meta))]))
        top = dict(self.layers[1], source=str(source), path="top.img", z=150)
        self.layers.insert(2, top)
        payload = dict(role="fixture", outfit=self.outfit, slot="coat", frame=0, x=10, y=20)
        sampled = studio.sample(payload)
        self.assertEqual((sampled["color"], sampled["alpha"], sampled["path"]), ("#f01e3c", 128, "top.img"))
        p = studio.compose("fixture", self.outfit)
        visible = studio._one_frame(p, p["box"], 0).getpixel((10 - p["box"][0], 20 - p["box"][1]))
        self.assertNotEqual(visible, (240, 30, 60, 128))
        self.assertEqual([s["slot"] for s in sampled["available_slots"]], ["coat", "skin"])
        missing = studio.sample(dict(payload, x=12, y=22))
        self.assertFalse(missing["matched"])
        self.assertIsNone(missing["color"])
        self.assertIsNone(missing["path"])
        self.assertEqual(missing["alpha"], 0)
        self.assertEqual([s["slot"] for s in missing["available_slots"]], ["pants", "skin"])

    def test_sample_rejects_invalid_coordinates_slots_and_frame(self):
        payload = dict(role="fixture", outfit=self.outfit, slot="coat", frame=0, x=10, y=20)
        for change in [dict(slot="private"), dict(slot=[]), dict(frame=3), dict(frame=True), dict(x=.5),
                       dict(y=float("nan")), dict(x=4097), dict(overlay=["C:/private.NPK"]), dict(source="C:/private.NPK")]:
            with self.subTest(change=str(change)), self.assertRaises(ValueError):
                studio.sample(dict(payload, **change))

    def test_scene_roundtrip_and_source_validation(self):
        import game
        path = "sprite/character/fixture/effect/known/flash.img"
        scene = {"effects": [{"path": path, "source": "official", "start": 2, "fps": 15, "x": -12, "y": 4,
                               "scale": 1.5, "opacity": .5, "front": False, "loop": True}]}
        with patch.object(studio, "class_folder", lambda p: "fixture"), \
             patch.object(render, "official_npk", lambda p: "known.npk" if p == path else None), \
             patch.object(game, "mods", lambda: {}):
            studio.save_outfit(dict(name="effect", role="fixture", outfit=self.outfit, scene=scene))
            self.assertEqual(studio.wardrobe()["outfits"][0]["scene"], scene)
            for invalid in [{"effects": [dict(scene["effects"][0], path="C:/private.txt")]},
                            {"effects": [dict(scene["effects"][0], source="unrelated")]},
                            {"effects": scene["effects"] * 9}]:
                with self.assertRaises(ValueError):
                    studio.scene("fixture", invalid)

    def test_scene_playback_enabled_order_and_recipe_roundtrip(self):
        import game
        path = "sprite/character/fixture/effect/known/flash.img"
        scene = {"effects": [{"path": path, "source": "official", "start": 9, "fps": 15, "x": -12, "y": 4,
                               "scale": 1.5, "opacity": .5, "front": False, "loop": True, "enabled": False, "blend": "add"},
                              {"path": path, "source": "official", "start": 2, "fps": 12, "x": 18, "y": 6,
                               "scale": 1, "opacity": 1, "front": False, "loop": False, "enabled": True, "blend": "normal"}],
                 "playback": {"start": 1, "end": 2, "fps": 11.5}}
        recipe = {"dyes": {"skin": {"lightness": -10}}, "pixels": [{"frame": 1, "x": 10, "y": 21, "color": "#ffaa2280"}]}
        with patch.object(studio, "class_folder", lambda p: "fixture"), \
             patch.object(render, "official_npk", lambda p: "known.npk" if p == path else None), \
             patch.object(game, "mods", lambda: {}):
            saved = studio.save_outfit(dict(name="arranged", role="fixture", outfit=self.outfit, scene=scene, customization=recipe))
            loaded = studio.wardrobe()["outfits"][0]
            self.assertEqual(saved["scene"], scene)
            self.assertEqual(loaded["scene"], scene)
            self.assertEqual(loaded["customization"], customize.recipe(recipe, 3))
            for invalid in [dict(playback={"start": 0, "end": 3, "fps": 10}),
                            dict(playback={"start": 2, "end": 1, "fps": 10}),
                            dict(playback={"start": 0, "end": 1, "fps": 61}),
                            dict(playback={"start": 0, "end": 1}),
                            dict(effects=[dict(scene["effects"][0], enabled="false")]),
                            dict(effects=[dict(scene["effects"][0], blend="screen")]),
                            dict(effects=[dict(scene["effects"][0], blend=True)]),
                            dict(effects=[dict(scene["effects"][0], blend=["add"])])]:
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    studio.scene("fixture", dict(scene, **invalid))

    def test_rejects_invalid_and_excessive_input(self):
        bad = [{"dyes": {"coat": {"hue": float("nan")}}}, {"dyes": {"invalid": {}}},
               {"pixels": [{"frame": 3, "x": 0, "y": 0, "color": "#fff000ff"}]},
               {"pixels": [{"frame": 0, "x": .5, "y": 0, "color": "#fff000ff"}]},
               {"pixels": [{}] * 2001}, {"dyes": {"coat": {"colors": [{"from": "#fff", "to": "#000000"}]}}}]
        for value in bad:
            with self.subTest(value=str(value)[:80]), self.assertRaises(ValueError):
                customize.recipe(value, 3)
        with self.assertRaises(ValueError):
            studio.valid_overlay(["C:/arbitrary.NPK"])
        with self.assertRaises(ValueError):
            customize.expanded_box((0, 0, 8, 8), [dict(x=4096, y=4096)], 3)


def real_resource_check():
    """Optional local-client regression: puts its checked NPK under output/validation only."""
    outfit = studio.default_outfit("gunner_at")
    destination = ROOT / "output" / "validation" / "studio_polish_v02" / "exports"
    for label, overlay, candidates in [("official_layers", "", ["coat", "hair", "pants", "shoes"]), ("claude_skin", "claude", ["skin"])]:
        base = studio.compose("gunner_at", outfit, overlay)
        image = studio._one_frame(base, base["box"], 0)
        before = np.asarray(image)
        if not image.getbbox():
            raise AssertionError("real character frame is empty")
        for slot in candidates:
            recipe = {"dyes": {slot: {"hue": 35, "lightness": -12}}}
            dyed = studio.compose("gunner_at", outfit, overlay, recipe)
            after = np.asarray(studio._one_frame(dyed, base["box"], 0))
            changed = (before[..., 3] > 0) & np.any(before[..., :3] != after[..., :3], axis=2)
            if changed.any():
                break
        else:
            raise AssertionError(f"{label}: no selected-slot dye actually changed visible pixels")
        yy, xx = np.argwhere(changed)[len(np.argwhere(changed)) // 2]
        x, y = int(base["box"][0] + xx), int(base["box"][1] + yy)
        sampled = studio.sample(dict(role="gunner_at", outfit=outfit, overlay=overlay, customization=recipe, slot=slot, frame=0, x=x, y=y))
        assert sampled["matched"] and sampled["alpha"] > 0, sampled
        recipe["dyes"][slot]["colors"] = [{"from": sampled["color"], "to": "#22aaff", "tolerance": 0}]
        recipe["pixels"] = [{"frame": 0, "x": x, "y": y, "color": "#fbaa2280"}]
        # Real wardrobe data is never changed; roundtrip the same normalized recipe in an isolated file.
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, "WARDROBE", Path(tmp) / "wardrobe.json"), patch.object(studio, "EXPORTS", destination):
            studio.save_outfit(dict(name=label, role="gunner_at", outfit=outfit, overlay=overlay, customization=recipe))
            loaded = studio.wardrobe()["outfits"][0]
            assert loaded["customization"] == customize.recipe(recipe, base["frames"])
            result = studio.export_outfit(dict(role="gunner_at", current=outfit, target=outfit, overlay=overlay, name=label, customization=loaded["customization"]))
        assert result["check"]["passed"] and result["check"]["max_rgba_delta"] == 0, result["check"]
        print(json.dumps({"case": label, "dyed_slot": slot, "visible_dyed_pixels_frame0": int(changed.sum()), "sampled_source": sampled,
                          "real_resources": result["check"], "frames": result["frames"], "size": result["size"], "folder": result["folder"]}))


if __name__ == "__main__":
    if "--real" in sys.argv:
        real_resource_check()
        sys.argv.remove("--real")
    unittest.main()
