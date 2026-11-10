"""Independent actual-stage/package verification for an illustration config."""
from pathlib import Path
import hashlib
import json
import sys
import unittest

import numpy as np
from PIL import Image,ImageOps

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from dnf_resources import ImgArchive,read_npk
from survey_gunner_effects import reader


def resolve(value):
    p=Path(value);return (p if p.is_absolute() else ROOT/p).resolve(strict=True)


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def entries(path):
    data=Path(path).read_bytes();rows=read_npk(path)
    return {r['path']:(r,data[r['offset']:r['offset']+r['length']]) for r in rows}


def size(frame):return frame.get('w',frame.get('width')),frame.get('h',frame.get('height'))
def canvas(frame):return frame.get('cw',frame.get('canvas_width')),frame.get('ch',frame.get('canvas_height'))
def pic(img,k):
    image=img.image(k)
    return image.convert('RGBA') if image is not None else Image.new('RGBA',size(img.resolve(k)))


CONFIG=resolve(sys.argv[1]);CFG=json.loads(CONFIG.read_text('utf-8'))
OUT=(ROOT/CFG['output']).resolve() if not Path(CFG['output']).is_absolute() else Path(CFG['output']).resolve()
STAGE=OUT/'stage/manifest.json';MANIFEST=json.loads(STAGE.read_text('utf-8'))
PACKAGE=OUT/CFG['npk_name']


class StageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources={};cls.loaded=[]
        cls.specs={s['path']:s for s in CFG['overlays']}
        for e in MANIFEST['edits']:
            source=resolve(e['source_npk'])
            if source not in cls.sources:cls.sources[source]=entries(source)
            row,data=cls.sources[source][e['path']]
            cls.loaded.append((e,reader(data,row['version']),ImgArchive(resolve(e['payload']).read_bytes())))

    def test_signed_inputs_and_payloads_are_unchanged(self):
        self.assertEqual(MANIFEST['base_sha256'],sha(resolve(CFG['base_npk'])))
        for path,digest in MANIFEST['inputs_sha256'].items():self.assertEqual(sha(resolve(path)),digest,path)
        for e,_,_ in self.loaded:self.assertEqual(sha(resolve(e['payload'])),e['payload_sha256'])

    def test_explicit_scope_is_complete_and_unique(self):
        wanted=[s['path'] for s in CFG['overlays']]
        actual=[e['path'] for e in MANIFEST['edits']]
        self.assertEqual(set(wanted),set(actual));self.assertEqual(len(actual),len(set(actual)))

    def test_frame_counts_links_and_canvas_match_official(self):
        for e,old,new in self.loaded:
            self.assertEqual(old.count,new.count,e['path'])
            for k,(before,after) in enumerate(zip(old.frames,new.frames,strict=True)):
                self.assertEqual(before.get('link'),after.get('link'),(e['path'],k))
                if 'link' in before:continue
                self.assertEqual(canvas(before),canvas(after),(e['path'],k))
                if not e['allow_geometry_change']:
                    self.assertEqual(size(before),size(after))
                    self.assertEqual((before['x'],before['y']),(after['x'],after['y']))

    def test_original_empty_frames_stay_empty(self):
        for e,old,new in self.loaded:
            for record in e['frames']:
                if not record.get('original_empty'):continue
                k=record['frame'];self.assertIsNone(pic(new,k).getbbox(),(e['path'],k))
                np.testing.assert_array_equal(np.asarray(pic(new,k)),np.asarray(pic(old,k)))

    def test_staged_visible_rgba_equals_selected_source_png(self):
        for e,old,new in self.loaded:
            spec=self.specs[e['path']]
            for record in e['frames']:
                if not record.get('png'):continue
                k=record['frame'];expected=Image.open(resolve(record['png'])).convert('RGBA');actual=pic(new,k)
                if e['frame_mode']=='canvas':
                    wanted=canvas(old.frames[k])
                    if expected.size!=wanted:
                        self.assertTrue(spec.get('fit_to_canvas'))
                        if spec.get('canvas_fit','contain')=='resize':expected=expected.resize(wanted,Image.Resampling.LANCZOS)
                        else:
                            small=ImageOps.contain(expected,wanted,Image.Resampling.LANCZOS)
                            expected=Image.new('RGBA',wanted);expected.paste(small,((wanted[0]-small.width)//2,(wanted[1]-small.height)//2))
                    page=Image.new('RGBA',wanted);f=new.frames[k];page.paste(actual,(f['x'],f['y']));actual=page
                a=np.asarray(expected);b=np.asarray(actual)
                self.assertEqual(a.shape,b.shape,(e['path'],k))
                np.testing.assert_array_equal(a[...,3],b[...,3],err_msg=str((e['path'],k)))
                visible=(a[...,3]>0)|(b[...,3]>0)
                np.testing.assert_array_equal(a[...,:3][visible],b[...,:3][visible],err_msg=str((e['path'],k)))

    def test_protected_game_buff_and_native_hashes_match(self):
        for path,digest in MANIFEST['protected_sha256'].items():self.assertEqual(sha(resolve(path)),digest,path)


@unittest.skipUnless(PACKAGE.exists(),'No published package yet')
class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=entries(resolve(CFG['base_npk']));cls.new=entries(PACKAGE)
        cls.report=json.loads((OUT/'validation.json').read_text('utf-8'))
        cls.changed={e['path'] for e in MANIFEST['edits']}

    def test_old_payloads_outside_explicit_scope_are_byte_identical(self):
        self.assertTrue(set(self.base).issubset(self.new))
        self.assertEqual(set(self.new)-set(self.base),self.changed-set(self.base))
        for path,(_,data) in self.base.items():
            if path not in self.changed:self.assertEqual(data,self.new[path][1],path)

    def test_package_overlay_payloads_equal_signed_stage(self):
        for e in MANIFEST['edits']:self.assertEqual(self.new[e['path']][1],resolve(e['payload']).read_bytes())

    def test_package_is_bound_to_manifest_and_source_hash(self):
        self.assertEqual(self.report['stage_manifest_sha256'],sha(STAGE))
        self.assertEqual(self.report['sha256'],sha(PACKAGE))
        self.assertEqual(self.report['base_sha256'],MANIFEST['base_sha256'])
        self.assertFalse(self.report['installed']);self.assertFalse(self.report['ingame_verified'])


if __name__=='__main__':
    suite=unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(StageTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(PackageTests))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'passed':result.wasSuccessful(),'tests_run':result.testsRun,'skipped':len(result.skipped),
            'failures':[str(t[0]) for t in result.failures],'errors':[str(t[0]) for t in result.errors],
            'stage_sha256':sha(STAGE),'package_validated':PACKAGE.exists(),'validator_sha256':sha(Path(__file__)),
            'scope':'Actual source PNGs, IMG links/canvas/visible RGBA, signed inputs, protected files and unchanged base payloads; not user aesthetics or in-game timing.'}
    (OUT/'independent_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));sys.exit(0 if result.wasSuccessful() else 1)
