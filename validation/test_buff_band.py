"""Read-only checks of the exported v06 band and its frozen v05 inputs.

The scene is single-play; no first/last matching or in-game compatibility claim.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_buff_band


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExportedBand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / 'design/claude_gunner/buff_v06.json').read_text('utf-8'))
        cls.folder = ROOT / cls.cfg['output']
        cls.manifest = json.loads((cls.folder / 'manifest.json').read_text('utf-8'))
        cls.proof = json.loads((cls.folder / 'band_validation.json').read_text('utf-8'))
        cls.source = ROOT / 'output/claude_buff_v05/preview'
        cls.sources = [np.asarray(Image.open(cls.source / f'frames/frame_{k:04d}.png').convert('RGBA')) for k in range(19)]
        cls.frames = [np.asarray(Image.open(cls.folder / f'frames/frame_{k:04d}.png').convert('RGBA')) for k in range(19)]
        cls.characters = [np.asarray(Image.open(cls.folder / f'layers/character/frame_{k:04d}.png').convert('RGBA')) for k in range(19)]

    def test_frozen_source_files_and_output_hashes(self):
        actual_files = {p.relative_to(self.source).as_posix():sha(p) for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(actual_files, self.proof['source_files'])
        for k, frame_hash in enumerate(self.manifest['frame_sha256']):
            self.assertEqual(sha(self.folder / f'frames/frame_{k:04d}.png'), frame_hash)
        self.assertEqual(sha(ROOT / self.cfg['fx_source']), self.manifest['fx_sha256'])
        self.assertFalse(self.manifest['installed'])

    def test_actual_alpha_band_and_full_height_rails(self):
        for k, frame in enumerate(self.frames):
            with self.subTest(frame=k):
                self.assertEqual(frame.shape, (668,470,4))
                alpha = frame[...,3]
                self.assertEqual(int(alpha.min()),0)
                self.assertEqual(int(alpha.max()),255)
                self.assertFalse(alpha[:,:46].any())
                self.assertFalse(alpha[:,425:].any())
                self.assertTrue(np.all(alpha[:,70] == 255))
                self.assertTrue(np.all(alpha[:,400] == 255))
                yy,xx=np.nonzero(alpha>8)
                self.assertLessEqual(int(xx.max()-xx.min()+1),379)
                self.assertEqual((int(yy.min()),int(yy.max())),(0,667))

    def test_integer_upward_motion_without_resizing(self):
        expected=[389,251,149,81,39,19,11,5,0,-4,-7,-10,-12,-16,-20,-26,-34,-47,-68]
        for k,dy in enumerate(expected):
            with self.subTest(frame=k):
                self.assertEqual(self.manifest['frame_metrics'][k]['character_transform'],{'x':0,'y':dy,'scale':1})
                source=self.sources[k]
                y0,y1=max(0,-dy),min(587,668-dy)
                reference=source[y0:y1,76:394]
                actual=self.characters[k][y0+dy:y1+dy,76:394]
                visible=reference[...,3]>0
                np.testing.assert_array_equal(actual[visible],reference[visible])
                # A textured face patch is an actual coordinate witness, not
                # merely trust in the transform written by the builder.
                patch=source[125:160,260:288]
                self.assertGreater(float(patch[...,:3].std()),5)
                np.testing.assert_array_equal(self.characters[k][125+dy:160+dy,260:288],patch)

    def test_blink_pixels_retained_and_foreground_does_not_cover_face(self):
        source_manifest=json.loads((self.source/'manifest.json').read_text('utf-8'))
        for k,source in enumerate(self.sources):
            dy=self.cfg['motion']['y_offsets'][k]
            self.assertEqual(self.manifest['frame_metrics'][k]['blink'],source_manifest['frame_metrics'][k]['blink'])
            lo,hi=max(60,-dy),min(213,668-dy)
            a=source[lo:hi,160:330]
            b=self.frames[k][lo+dy:hi+dy,160:330]
            opaque=a[...,3]>=250
            self.assertGreater(int(opaque.sum()),10000)
            # v05's generated source uses alpha254 over most facial pixels;
            # the new backing can legitimately change composited RGBA by one
            # quantization unit. The actual character layer is exact above.
            self.assertLessEqual(int(np.max(np.abs(a[opaque].astype(np.int16)-b[opaque].astype(np.int16)))),2)
        changed=np.max(np.abs(self.sources[8][60:213,160:330].astype(np.int16)-self.sources[0][60:213,160:330].astype(np.int16)),axis=2)
        self.assertGreater(int(np.count_nonzero(changed)),48)
        self.assertEqual(self.manifest['frame_metrics'][8]['blink'],'closed')

    def test_fixed_rails_have_continuous_overscan_not_wrap_seam(self):
        positions=[]
        for k in range(19):
            background=np.asarray(Image.open(self.folder/f'layers/background/frame_{k:04d}.png').convert('RGBA'))
            np.testing.assert_array_equal(background[:,70],np.tile([255,198,83,255],(668,1)))
            np.testing.assert_array_equal(background[:,400],np.tile([255,235,184,255],(668,1)))
            positions.append(self.manifest['frame_metrics'][k]['rail_texture_y'])
        self.assertEqual(positions,list(range(0,38,2)))
        # The crop reaches into a 705-high source, never restarts at its top.
        self.assertEqual(max(positions),36)
        self.assertNotEqual(self.manifest['frame_metrics'][0]['character_transform']['y'],positions[0])

    def test_source_bottom_crop_fades_before_it_is_exposed(self):
        last=self.characters[-1]
        source=self.sources[-1]
        self.assertFalse(last[599:,:,3].any())
        for sy in (590,610,630,650,667):
            t=np.clip((667-sy)/80,0,1)
            expected=np.rint(source[sy,90:380,3]*(t*t*(3-2*t))).astype(np.uint8)
            np.testing.assert_array_equal(last[sy-68,90:380,3],expected)

    def test_single_play_not_a_loop_and_mov_webp_transport(self):
        self.assertFalse(self.proof['seamless_loop_claimed'])
        self.assertGreater(int(np.max(np.abs(self.frames[0].astype(np.int16)-self.frames[-1].astype(np.int16)))),50)
        with av.open(str(self.folder/'portrait_rgba.mov')) as container:
            decoded=[frame.to_ndarray(format='rgba') for frame in container.decode(video=0)]
        self.assertEqual(len(decoded),19)
        for source,transport in zip(self.frames,decoded,strict=True):
            np.testing.assert_array_equal(source,transport)
        with Image.open(self.folder/'preview.webp') as image:
            webp=[np.array(frame.convert('RGBA')) for frame in ImageSequence.Iterator(image)]
        self.assertEqual(len(webp),19)
        for source,transport in zip(self.frames,webp,strict=True):
            visible=source[...,3]>0
            np.testing.assert_array_equal(source[...,3],transport[...,3])
            np.testing.assert_array_equal(source[visible],transport[visible])

    def test_builder_refuses_to_overwrite_existing_output_by_default(self):
        with self.assertRaises(FileExistsError):
            build_buff_band.build()


if __name__=='__main__':
    unittest.main()
