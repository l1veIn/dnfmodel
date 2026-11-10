"""Read-only checks of the exported v07 opening, transport and frozen inputs.

Geometry is checked against actual exported character pixels, not just the
builder's transform metadata. This does not claim real-game playback testing.
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_buff_center


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExportedCenterOpening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=json.loads((ROOT/'design/claude_gunner/buff_v07.json').read_text('utf-8'))
        cls.folder=ROOT/cls.cfg['output']
        cls.manifest=json.loads((cls.folder/'manifest.json').read_text('utf-8'))
        cls.proof=json.loads((cls.folder/'center_validation.json').read_text('utf-8'))
        cls.source=ROOT/'output/claude_buff_v05/preview'
        cls.sources=[np.asarray(Image.open(cls.source/f'frames/frame_{k:04d}.png').convert('RGBA')) for k in range(19)]
        cls.frames=[np.asarray(Image.open(cls.folder/f'frames/frame_{k:04d}.png').convert('RGBA')) for k in range(19)]
        cls.characters=[np.asarray(Image.open(cls.folder/f'layers/character/frame_{k:04d}.png').convert('RGBA')) for k in range(19)]
        cls.backgrounds=[np.asarray(Image.open(cls.folder/f'layers/background/frame_{k:04d}.png').convert('RGBA')) for k in range(19)]
        cls.foregrounds=[np.asarray(Image.open(cls.folder/f'layers/foreground/frame_{k:04d}.png').convert('RGBA')) for k in range(19)]

    def test_frozen_v05_v06_and_game_files_unchanged(self):
        for folder,expected in self.proof['frozen_trees'].items():
            actual={p.relative_to(ROOT/folder).as_posix():sha(p) for p in (ROOT/folder).rglob('*') if p.is_file()}
            self.assertEqual(actual,expected,folder)
        self.assertGreaterEqual(len(self.proof['game_files']),6)
        for path,expected in self.proof['game_files'].items():
            self.assertEqual(sha(Path(path)),expected,path)
        self.assertFalse(self.manifest['installed'])

    def test_output_and_input_hashes_are_actual(self):
        for k,expected in enumerate(self.manifest['frame_sha256']):
            self.assertEqual(sha(self.folder/f'frames/frame_{k:04d}.png'),expected)
        for asset in self.manifest['motif_sources'].values():
            self.assertEqual(sha(ROOT/asset['path']),asset['sha256'])
        self.assertTrue(self.manifest['motifs_complete'])
        self.assertEqual(sha(ROOT/self.cfg['fx_source']),self.manifest['fx_sha256'])
        self.assertEqual(sha(self.folder/'sheet.png'),self.manifest['sheet_sha256'])

    def test_actual_character_pixels_keep_coordinates_scale_and_local_motion(self):
        widths=[2,28,72,121,153]+[165]*14
        distance=np.abs(np.arange(470,dtype=np.float32)-235)
        t=np.clip((667-np.arange(668))/80,0,1)
        bottom=t*t*(3-2*t)
        for k,(source,actual,half) in enumerate(zip(self.sources,self.characters,widths,strict=True)):
            with self.subTest(frame=k):
                # Independent reconstruction of the sole permitted alpha
                # operations. No x/y sampling or geometric resize is allowed.
                faded=np.rint(source[...,3]*bottom[:,None]).astype(np.uint8)
                opening=np.clip((half-distance)/3,0,1)
                expected=np.rint(faded*opening[None,:]).astype(np.uint8)
                np.testing.assert_array_equal(actual[...,3],expected)
                visible=actual[...,3]>0
                np.testing.assert_array_equal(actual[visible,:3],source[visible,:3])
                self.assertEqual(self.manifest['frame_metrics'][k]['character_transform'],{'x':0,'y':0,'scale':1})
        # Actual changing pixels in the held-open character still equal the
        # original hair/cloth frames, rather than a static layer being zoomed.
        local=np.any(self.sources[5][220:570,80:390]!=self.sources[15][220:570,80:390],axis=2)
        self.assertGreater(int(local.sum()),100)
        patch=self.sources[12][125:160,260:288]
        self.assertGreater(float(patch[...,:3].std()),5)
        np.testing.assert_array_equal(self.characters[12][125:160,260:288],patch)

    def test_center_reveal_is_symmetric_monotonic_and_settled_before_blink(self):
        expected=[2,28,72,121,153]+[165]*14
        masks=[]
        for k,half in enumerate(expected):
            metric=self.manifest['frame_metrics'][k]
            self.assertEqual(metric['reveal_edges'],[235-half,235+half])
            self.assertEqual(metric['rail_x'],metric['reveal_edges'])
            value=np.clip((half-np.abs(np.arange(470)-235))/3,0,1)
            np.testing.assert_array_equal(value[1:235],value[469:235:-1])
            masks.append(value)
        self.assertTrue(np.all(np.diff(np.asarray(masks),axis=0)>=0))
        self.assertEqual(self.manifest['composition']['opening_complete_frame'],5)
        self.assertEqual(self.manifest['frame_metrics'][7]['blink'],'half')

    def test_both_full_height_rail_cores_follow_opening_edges(self):
        for k,background in enumerate(self.backgrounds):
            left,right=self.manifest['frame_metrics'][k]['rail_x']
            with self.subTest(frame=k):
                np.testing.assert_array_equal(background[:,left],np.tile([255,198,83,255],(668,1)))
                np.testing.assert_array_equal(background[:,right],np.tile([255,235,184,255],(668,1)))
                self.assertEqual(left+right,470)
                self.assertEqual(self.manifest['frame_metrics'][k]['rail_texture_y'],k*2)
        self.assertEqual(self.manifest['frame_metrics'][-1]['rail_texture_y'],36)

    def test_blink_is_inherited_and_foreground_avoids_face_and_hand(self):
        source_manifest=json.loads((self.source/'manifest.json').read_text('utf-8'))
        for k,foreground in enumerate(self.foregrounds):
            with self.subTest(frame=k):
                self.assertEqual(self.manifest['frame_metrics'][k]['blink'],source_manifest['frame_metrics'][k]['blink'])
                self.assertFalse(foreground[55:213,151:337,3].any())
                self.assertFalse(foreground[204:376,264:432,3].any())
                if k>=3:
                    source=self.sources[k][60:213,160:330]
                    actual=self.frames[k][60:213,160:330]
                    opaque=source[...,3]>=250
                    self.assertGreater(int(opaque.sum()),10000)
                    self.assertLessEqual(int(np.max(np.abs(source[opaque].astype(np.int16)-actual[opaque].astype(np.int16)))),2)
        difference=np.any(self.sources[8][60:213,160:330]!=self.sources[0][60:213,160:330],axis=2)
        self.assertGreater(int(difference.sum()),48)
        self.assertEqual(self.manifest['frame_metrics'][8]['blink'],'closed')

    def test_motifs_have_visible_lower_signature_and_transient_center_pulse(self):
        self.assertEqual(self.cfg['effects']['a_slash_width'],76)
        self.assertEqual(self.cfg['effects']['a_slash_center'],[235,605])
        self.assertGreater(int((self.foregrounds[12][570:640,190:280,3]>100).sum()),500)
        self.assertGreater(int(self.foregrounds[3][350:480,150:320,3].max()),100)
        self.assertEqual(int(self.foregrounds[18][350:480,150:320,3].max()),0)
        # Rail texture foreground is weaker than 90 alpha; the brighter small
        # shapes here witness the separate retained edge-star ornament.
        self.assertGreater(int((self.foregrounds[12][80:109,70:102,3]>90).sum()),10)

    def test_alpha_is_transparent_outside_band_and_encoder_compatible(self):
        for k,frame in enumerate(self.frames):
            with self.subTest(frame=k):
                self.assertEqual(frame.shape,(668,470,4))
                self.assertEqual(int(frame[...,3].min()),0)
                self.assertEqual(int(frame[...,3].max()),255)
                self.assertFalse(frame[:,:46,3].any())
                self.assertFalse(frame[:,425:,3].any())
                invisible=frame[...,3]==0
                self.assertFalse(frame[invisible,:3].any())
                yy,xx=np.nonzero(frame[...,3]>8)
                self.assertEqual((int(yy.min()),int(yy.max())),(0,667))
                self.assertLessEqual(int(xx.max()-xx.min()+1),379)

    def test_source_bottom_has_soft_eighty_pixel_matte(self):
        for k in (5,12,18):
            actual=self.characters[k]
            source=self.sources[k]
            self.assertFalse(actual[667,:,3].any())
            for y in (590,610,630,650,667):
                t=np.clip((667-y)/80,0,1)
                expected=np.rint(source[y,90:380,3]*(t*t*(3-2*t))).astype(np.uint8)
                np.testing.assert_array_equal(actual[y,90:380,3],expected)

    def test_mov_and_webp_preserve_nineteen_rgba_frames(self):
        self.assertFalse(self.proof['seamless_loop_claimed'])
        self.assertEqual(self.manifest['preview_duration_ms'],1267)
        self.assertGreater(int(np.max(np.abs(self.frames[0].astype(np.int16)-self.frames[-1].astype(np.int16)))),50)
        with av.open(str(self.folder/'portrait_rgba.mov')) as container:
            decoded=[frame.to_ndarray(format='rgba') for frame in container.decode(video=0)]
        self.assertEqual(len(decoded),19)
        for actual,transport in zip(self.frames,decoded,strict=True):
            np.testing.assert_array_equal(actual,transport)
        with Image.open(self.folder/'preview.webp') as image:
            webp=[np.array(frame.convert('RGBA')) for frame in ImageSequence.Iterator(image)]
        self.assertEqual(len(webp),19)
        for actual,transport in zip(self.frames,webp,strict=True):
            visible=actual[...,3]>0
            np.testing.assert_array_equal(actual[...,3],transport[...,3])
            np.testing.assert_array_equal(actual[visible],transport[visible])

    def test_builder_refuses_default_overwrite(self):
        with self.assertRaises(FileExistsError):
            build_buff_center.build()


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExportedCenterOpening))
    folder=ROOT/'output/validation/buff_v07_center'
    folder.mkdir(parents=True,exist_ok=True)
    report={'tests_run':result.testsRun,'passed':result.wasSuccessful(),
            'failures':[name.id() for name,_ in result.failures],
            'errors':[name.id() for name,_ in result.errors],
            'test_script_sha256':sha(Path(__file__)),
            'manifest_sha256':sha(ExportedCenterOpening.folder/'manifest.json'),
            'scope':'Actual exported pixels, source/game read-only hashes, alpha and lossless MOV/WebP; no real-game playback claim'}
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    raise SystemExit(not result.wasSuccessful())
