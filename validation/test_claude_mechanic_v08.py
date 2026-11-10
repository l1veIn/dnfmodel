"""Independent checks of signed v08 stage and optional packaged artifact.

Run after --stage, then again after --package. Missing integration artifacts are
explicitly skipped, not counted as verified. No game or source writes.
"""
from pathlib import Path
import colorsys
import hashlib
import json
import sys
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import package_claude_mechanic_v08 as build
from dnf_resources import ImgArchive, read_npk
from survey_gunner_effects import reader

STAGE = build.OUT / 'stage/manifest.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def npk_payloads(path):
    rows = read_npk(path)
    data = path.read_bytes()
    return {row['path']: data[row['offset']:row['offset']+row['length']] for row in rows}


def geometry(frame):
    if 'link' in frame:
        return ('link', frame['link'])
    return (frame.get('width', frame.get('w')), frame.get('height', frame.get('h')),
            frame['x'], frame['y'], frame.get('canvas_width', frame.get('cw')),
            frame.get('canvas_height', frame.get('ch')))


class GlowUnitTests(unittest.TestCase):
    def test_alpha_including_fractional_alpha_unchanged(self):
        pixels = np.array([[[0, 30, 230, a] for a in (0, 1, 32, 128, 254, 255)]], dtype=np.uint8)
        actual, count = build.orange_glow(Image.fromarray(pixels))
        self.assertTrue(np.array_equal(np.asarray(actual)[..., 3], pixels[..., 3]))
        self.assertEqual(count, 5)

    def test_warm_and_neutral_pixels_not_recolored(self):
        pixels = np.array([[[0, 0, 0, 255], [92, 28, 10, 255], [222, 98, 44, 255],
                            [255, 236, 208, 255], [130, 130, 130, 150]]], dtype=np.uint8)
        actual, count = build.orange_glow(Image.fromarray(pixels))
        self.assertEqual(count, 0)
        self.assertTrue(np.array_equal(np.asarray(actual), pixels))

    def test_cyan_blue_green_and_purple_become_warm(self):
        pixels = np.array([[[20, 210, 230, 255], [20, 20, 255, 255], [20, 255, 20, 255],
                            [140, 20, 220, 255]]], dtype=np.uint8)
        actual, count = build.orange_glow(Image.fromarray(pixels))
        self.assertEqual(count, 4)
        rgb = np.asarray(actual)[..., :3]
        self.assertTrue(np.all(rgb[..., 0] >= rgb[..., 1]))
        self.assertTrue(np.all(rgb[..., 1] >= rgb[..., 2]))

    def test_energy_mode_keeps_black_white_and_alpha(self):
        pixels = np.array([[[0, 0, 0, 255], [255, 255, 255, 200], [0, 255, 0, 128],
                            [255, 0, 0, 90], [255, 0, 255, 0]]], dtype=np.uint8)
        actual, count = build.orange_glow(Image.fromarray(pixels), 'energy')
        output = np.asarray(actual)
        self.assertEqual(count, 2)
        self.assertTrue(np.array_equal(output[..., 3], pixels[..., 3]))
        self.assertTrue(np.array_equal(output[:, :2], pixels[:, :2]))
        self.assertTrue(np.array_equal(output[:, 4:], pixels[:, 4:]))


@unittest.skipUnless(STAGE.exists(), 'No v08 stage yet')
class StageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(STAGE.read_text(encoding='utf-8'))
        cls.items = []
        for edit in cls.manifest['edits']:
            source = Path(edit['source_npk'])
            row = next(r for r in read_npk(source) if r['path'] == edit['path'])
            with source.open('rb') as stream:
                stream.seek(row['offset'])
                original_data = stream.read(row['length'])
            official = reader(original_data, row['version'])
            payload = (ROOT / edit['payload']).read_bytes()
            new = ImgArchive(payload)
            cls.items.append((edit, official, new))
        cls.base_rows = {r['path']: r for r in read_npk(build.BASE)}

    def inherited(self, edit, official):
        row = self.base_rows.get(edit['path'])
        if row is None:
            return official
        with build.BASE.open('rb') as stream:
            stream.seek(row['offset'])
            return reader(stream.read(row['length']), row['version'])

    def test_signed_source_inputs_and_exact_base(self):
        self.assertEqual(sha(build.BASE), 'd56c0a3cbe2beba5a82f29854db174286f0f4ad28662819c6d937f0cc9ae9483')
        for filename, expected in self.manifest['inputs_sha256'].items():
            with self.subTest(filename=filename):
                self.assertEqual(sha(Path(filename)), expected)

    def test_stage_payload_hashes(self):
        self.assertGreater(len(self.items), 0)
        for edit, _, new in self.items:
            with self.subTest(path=edit['path']):
                self.assertEqual(sha(ROOT / edit['payload']), edit['payload_sha256'])
                self.assertEqual(new.version, 2)

    def test_frame_count_links_dimensions_and_all_offsets(self):
        for edit, old, new in self.items:
            self.assertEqual(old.count, new.count, edit['path'])
            for k, (a, b) in enumerate(zip(old.frames, new.frames, strict=True)):
                with self.subTest(path=edit['path'], frame=k):
                    self.assertEqual(geometry(a), geometry(b))

    def test_redrawn_frames_match_pngs_pixel_for_pixel(self):
        tested = 0
        for edit, _, new in self.items:
            for info in edit['frames']:
                if info.get('png'):
                    expected = np.asarray(Image.open(info['png']).convert('RGBA'))
                    actual = np.asarray(new.image(info['frame']))
                    self.assertTrue(np.array_equal(actual, expected), (edit['path'], info['frame']))
                    tested += 1
        self.assertGreater(tested, 0)

    def test_unedited_redraw_frames_inherit_prior_pixels(self):
        for edit, old, new in self.items:
            if edit['mode'] != 'redraw':
                continue
            prior = self.inherited(edit, old)
            for info in edit['frames']:
                if 'link' in info or info.get('png'):
                    continue
                k = info['frame']
                if np.prod(info['size']) <= 1:
                    continue
                self.assertTrue(np.array_equal(np.asarray(prior.image(k)), np.asarray(new.image(k))),
                                (edit['path'], k))

    def test_glow_preserves_alpha_transparency_and_warm_neutrals(self):
        for edit, old, new in self.items:
            if edit['mode'] != 'glow':
                continue
            prior = self.inherited(edit, old)
            changed_total = 0
            for k, frame in enumerate(prior.frames):
                if 'link' in frame or np.prod(geometry(frame)[:2]) <= 1:
                    continue
                a, b = np.asarray(prior.image(k)), np.asarray(new.image(k))
                self.assertTrue(np.array_equal(a[..., 3], b[..., 3]), (edit['path'], k))
                changed = np.any(a[..., :3] != b[..., :3], axis=2)
                self.assertFalse(np.any(changed & (a[..., 3] == 0)))
                changed_total += int(changed.sum())
                samples = a[..., :3][changed]
                for r, g, blue in samples[::max(1, len(samples)//1000)]:
                    hue, sat, _ = colorsys.rgb_to_hsv(float(r)/255, float(g)/255, float(blue)/255)
                    if edit.get('glow_mapping') == 'energy':
                        self.assertGreater(sat, .07)
                    else:
                        self.assertTrue(.27 <= hue <= .95 and sat > .11)
                changed_rgb = b[..., :3][changed]
                if len(changed_rgb):
                    self.assertTrue(np.all(changed_rgb[:, 0] >= changed_rgb[:, 1]))
                    self.assertTrue(np.all(changed_rgb[:, 1] >= changed_rgb[:, 2]))
            self.assertGreater(changed_total, 0)

    def test_protected_game_buff_and_native_hashes(self):
        protected = self.manifest['protected_sha256']
        self.assertGreaterEqual(len(protected), 149)
        for filename, expected in protected.items():
            with self.subTest(filename=filename):
                self.assertEqual(sha(Path(filename)), expected)


@unittest.skipUnless(STAGE.exists() and build.PACKAGE.exists(), 'No published v08 package yet')
class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(STAGE.read_text(encoding='utf-8'))
        cls.report = json.loads((build.OUT / 'validation.json').read_text(encoding='utf-8'))
        cls.old, cls.new = npk_payloads(build.BASE), npk_payloads(build.PACKAGE)
        cls.edits = {e['path']: e for e in cls.manifest['edits']}

    def test_every_old_path_and_unchanged_payload_preserved(self):
        self.assertEqual(len(self.old), 7700)
        self.assertTrue(set(self.old).issubset(self.new))
        for name in set(self.old)-set(self.edits):
            self.assertEqual(self.old[name], self.new[name], name)

    def test_only_explicit_paths_added_or_changed(self):
        self.assertEqual(set(self.new)-set(self.old), set(self.edits)-set(self.old))
        for name, edit in self.edits.items():
            self.assertEqual(hashlib.sha256(self.new[name]).hexdigest(), edit['payload_sha256'])

    def test_package_bound_to_stage_and_file_digest(self):
        self.assertEqual(sha(STAGE), self.report['stage_manifest_sha256'])
        self.assertEqual(sha(build.PACKAGE), self.report['sha256'])
        self.assertFalse(self.report['installed'])
        self.assertFalse(self.report['ingame_verified'])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    report = {'passed': result.wasSuccessful(), 'tests_run': result.testsRun, 'skipped': len(result.skipped),
              'failures': [str(x[0]) for x in result.failures], 'errors': [str(x[0]) for x in result.errors],
              'stage_validated': STAGE.exists(), 'package_validated': build.PACKAGE.exists(),
              'test_script_sha256': sha(Path(__file__)),
              'scope': 'Actual IMG geometry/links/RGBA, inherited payloads and protected file hashes; not in-game timing or aesthetic acceptance'}
    if STAGE.exists():
        report['stage_sha256'] = sha(STAGE)
        build.write_json(build.OUT / 'independent_validation.json', report)
    print(json.dumps(report, indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
