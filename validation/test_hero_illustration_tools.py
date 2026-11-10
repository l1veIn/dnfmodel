"""Offline regression for chroma edges, exact V2 geometry and signed packaging."""
from pathlib import Path
import hashlib
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import hero_cutin_video as video
import package_hero_illustrations as build
from dnf_resources import ImgArchive,read_npk,write_v2
from gunner_props_build import write_shared_npk


class ChromaTests(unittest.TestCase):
    def test_opaque_lilac_and_navy_interiors_survive_unchanged(self):
        a=np.full((32,32,3),(255,0,255),dtype=np.uint8)
        a[8:24,8:16]=(224,196,244)
        a[8:24,16:24]=(25,40,120)
        out=np.asarray(video.key_magenta(Image.fromarray(a)))
        self.assertTrue(np.all(out[8:24,8:24,3]==255))
        np.testing.assert_array_equal(out[8:24,8:24,:3],a[8:24,8:24])
        self.assertTrue(np.all(out[0,:,3]==0))

    def test_magenta_hole_and_soft_edge_are_keyed(self):
        a=np.full((32,32,3),(255,0,255),dtype=np.uint8)
        a[5:27,5:27]=(235,220,245)
        a[12:20,12:20]=(255,0,255)
        a[4,5:27]=(240,110,240)
        out=np.asarray(video.key_magenta(Image.fromarray(a)))
        self.assertTrue(np.all(out[12:20,12:20,3]==0))
        self.assertTrue(np.any(out[4,5:27,3]<255))
        self.assertEqual(out[10,10,3],255)

    def test_sampling_single_frame_and_endpoints(self):
        self.assertEqual([build.sample_index(i,1,4) for i in range(4)],[0,0,0,0])
        self.assertEqual(build.sample_index(0,10,1),0)
        self.assertEqual([build.sample_index(i,10,3) for i in range(3)],[0,4,9])

    def test_blue_profile_only_unmixes_saturated_magenta_at_boundary(self):
        a=np.zeros((40,40,4),dtype=np.uint8)
        a[3:37,3:37]=(25,40,120,255)
        a[3:12,5:15]=(224,196,244,255)
        a[20:25,3:5]=(120,14,204,216)
        a[18:22,18:22]=(120,14,204,255)
        out=np.asarray(video.clean_blue_hair_edges(Image.fromarray(a)))
        np.testing.assert_array_equal(out[3:12,5:15],a[3:12,5:15])
        np.testing.assert_array_equal(out[18:22,18:22],a[18:22,18:22])
        self.assertTrue(np.all(out[20:25,3:5,3]<216))
        self.assertTrue(np.all(out[20:25,3:5,0]<120))
        unchanged=(a[...,0]==25)&(a[...,1]==40)&(a[...,2]==120)
        np.testing.assert_array_equal(out[unchanged],a[unchanged])


class TransportTests(unittest.TestCase):
    def test_mp4_cover_stream_is_not_the_animation(self):
        cover=SimpleNamespace(index=0,disposition=int(video.av.stream.Disposition.attached_pic))
        motion=SimpleNamespace(index=2,disposition=1)
        container=SimpleNamespace(streams=SimpleNamespace(video=[cover,motion]))
        self.assertIs(video.playback_stream(container),motion)
        container.streams.video=[cover]
        with self.assertRaisesRegex(ValueError,'one continuous video'):video.playback_stream(container)
        container.streams.video=[cover,motion,SimpleNamespace(index=3,disposition=0)]
        with self.assertRaisesRegex(ValueError,'one continuous video'):video.playback_stream(container)

    def test_curl_keeps_authorization_in_stdin_and_verifies_tls(self):
        secret='offline-test-key-never-real'
        temporary=[]
        def run(args,**kwargs):
            self.assertEqual(args,['curl.exe','--config','-'])
            self.assertNotIn(secret,str(args))
            config=kwargs['input'].decode('utf-8')
            self.assertIn('Authorization: Bearer '+secret,config)
            self.assertNotIn('insecure',config)
            self.assertNotIn('location-trusted',config)
            options={line.split(' = ',1)[0]:json.loads(line.split(' = ',1)[1])
                     for line in config.splitlines() if ' = ' in line and line.split(' = ',1)[0] in ('output','data-binary')}
            request=Path(options['data-binary'][1:]); response=Path(options['output'])
            temporary.extend([request,response])
            self.assertNotIn(secret,request.read_text('utf-8'))
            self.assertEqual(json.loads(request.read_text('utf-8')),{'offline':True})
            response.write_bytes(b'{"ok":true}')
            return SimpleNamespace(returncode=0,stdout=b'200',stderr=b'')
        with patch.object(video.subprocess,'run',side_effect=run) as mocked:
            result=video.curl_transfer('https://example.invalid/v1/tasks','POST',
                                       {'Authorization':'Bearer '+secret},{'offline':True})
        self.assertEqual(json.loads(result),{'ok':True})
        self.assertEqual(mocked.call_count,1)
        self.assertTrue(all(not path.exists() for path in temporary))

    def test_uncertain_submission_has_one_call_and_cannot_be_resubmitted(self):
        folder=ROOT/'output/validation/hero_illustration_tools'/uuid.uuid4().hex
        folder.mkdir(parents=True)
        first=folder/'first.png'; Image.new('RGB',(160,90),'magenta').save(first)
        config=folder/'video.json'
        config.write_text(json.dumps({'clips':[{'id':'offline','first_frame':str(first),
                          'output':str(folder/'attempt'),'prompt':'offline','seconds':1}]}),encoding='utf-8')
        relay=SimpleNamespace(load_key=lambda:'offline-test-key-never-real',
                              to_data_uri=lambda _: 'data:image/png;base64,offline',unwrap=lambda x:x)
        with patch.object(video,'load_relay',return_value=relay), patch.object(video,'api_json',
                side_effect=video.urllib.error.URLError('offline transport failure')) as mocked:
            with self.assertRaisesRegex(RuntimeError,'outcome uncertain'):video.submit(config,'offline')
            with self.assertRaises(FileExistsError):video.submit(config,'offline')
        self.assertEqual(mocked.call_count,1)
        journal=json.loads((folder/'attempt/journal.json').read_text('utf-8'))
        self.assertEqual(journal['state'],'submission_uncertain')
        self.assertEqual(journal['transport_error_type'],'URLError')
        self.assertNotIn('offline-test-key-never-real',json.dumps(journal))


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'output/validation/hero_illustration_tools'/uuid.uuid4().hex
        cls.folder.mkdir(parents=True)
        cls.original_path='sprite/interface/skillcutscene/test_hero.img'
        images=[Image.new('RGBA',(5,7),'red'),Image.new('RGBA',(1,1)),
                Image.new('RGBA',(1,1)),Image.new('RGBA',(7,8),'blue')]
        metadata=[{'x':2,'y':3,'canvas_width':20,'canvas_height':18},
                  {'link':0},{'x':0,'y':0,'canvas_width':20,'canvas_height':18},
                  {'x':4,'y':5,'canvas_width':20,'canvas_height':18}]
        raw=write_v2(images,metadata,preserve_links=True)
        keep=write_v2([Image.new('RGBA',(2,3),(12,34,56,128))],
                      [{'x':1,'y':2,'canvas_width':10,'canvas_height':12}])
        cls.base=cls.folder/'base.NPK'
        cls.base.write_bytes(write_shared_npk([(cls.original_path,raw),('sprite/untouched.img',keep)]))
        cls.official=cls.folder/'official.NPK';cls.official.write_bytes(cls.base.read_bytes())
        cls.art=cls.folder/'new.png'; page=Image.new('RGBA',(20,18));page.paste((40,220,100,192),(9,1,18,15));page.save(cls.art)
        cls.config=cls.folder/'config.json'
        cls.cfg={'base_npk':str(cls.base),'base_sha256':build.sha(cls.base),'output':str(cls.folder/'candidate'),
                 'npk_name':'A_Test_Hero_v02.NPK','overlays':[{'source_npk':str(cls.official),
                 'path':cls.original_path,'frame_paths':[str(cls.art)],'frame_mode':'canvas','allow_geometry_change':True}]}
        cls.config.write_text(json.dumps(cls.cfg),encoding='utf-8')

    def protect(self,cfg):
        return {str(self.base):build.sha(self.base)}

    def test_a_stage_preserves_links_empty_frames_and_new_bbox(self):
        with patch.object(build,'protected',side_effect=self.protect):
            result=build.stage(self.config)
        self.assertTrue(result['staged'])
        m=json.loads((self.folder/'candidate/stage/manifest.json').read_text('utf-8'))
        img=ImgArchive((ROOT/m['edits'][0]['payload']).read_bytes())
        self.assertEqual(img.count,4)
        self.assertEqual(build.meta(img.frames[1]),{'link':0})
        self.assertEqual(build.meta(img.frames[0]),{'x':9,'y':1,'canvas_width':20,'canvas_height':18})
        self.assertEqual(build.shape(img.frames[0]),(9,14))
        self.assertIsNone(img.image(2).getbbox())
        self.assertEqual(build.shape(img.frames[2]),(1,1))
        np.testing.assert_array_equal(np.asarray(img.image(0)),np.asarray(Image.open(self.art))[1:15,9:18])

    def test_b_signed_input_change_prevents_package(self):
        before=self.art.read_bytes(); image=Image.new('RGBA',(20,18),'yellow');image.save(self.art)
        try:
            with patch.object(build,'protected',side_effect=self.protect):
                with self.assertRaisesRegex(ValueError,'Signed input changed'):
                    build.package_stage(self.config)
        finally:
            self.art.write_bytes(before)
        self.assertFalse((self.folder/'candidate/A_Test_Hero_v02.NPK').exists())

    def test_c_package_retains_unselected_payload_exactly(self):
        with patch.object(build,'protected',side_effect=self.protect):
            report=build.package_stage(self.config)
        self.assertEqual(report['entries'],2)
        self.assertEqual(report['unchanged_base_payloads'],1)
        _,old=build.payloads(self.base); _,new=build.payloads(Path(report['package']))
        self.assertEqual(old['sprite/untouched.img'],new['sprite/untouched.img'])
        self.assertNotEqual(old[self.original_path],new[self.original_path])
        self.assertFalse(report['installed'])

    def test_d_published_candidate_cannot_be_overwritten(self):
        with patch.object(build,'protected',side_effect=self.protect):
            with self.assertRaises(FileExistsError):build.stage(self.config,True)
            with self.assertRaises(FileExistsError):build.package_stage(self.config)

    def test_e_canvas_resize_requires_explicit_permission(self):
        source=ImgArchive(build.payloads(self.base)[1][self.original_path])
        cfg=dict(self.cfg['overlays'][0]); cfg['allow_geometry_change']=False
        with self.assertRaisesRegex(ValueError,'explicit allow_geometry_change'):
            build.edit_img(source,cfg,{})

    def test_f_local_dimension_mismatch_is_rejected(self):
        source=ImgArchive(build.payloads(self.base)[1][self.original_path])
        cfg=dict(self.cfg['overlays'][0]);cfg['frame_mode']='local';cfg['allow_geometry_change']=False
        with self.assertRaisesRegex(ValueError,'Local PNG size differs'):
            build.edit_img(source,cfg,{})

    def test_g_portrait_contain_does_not_stretch(self):
        image=Image.new('RGBA',(16,9),'white')
        result=build.fit_canvas(image,(20,40),{'fit_to_canvas':True})
        self.assertEqual(result.size,(20,40))
        self.assertEqual(result.getbbox(),(0,14,20,25))


if __name__=='__main__':
    unittest.main(verbosity=2)
