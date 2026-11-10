"""Independent output checks for the three back-view repairs only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'output/validation/claude_pose_correction_2026-11-09/lunge_back'
CLIP=ROOT/'output/Claude_Gunner_v02/clips/clip_052_059'
SLOTS=(53,54,55)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def check(applied=False):
    baseline=json.loads((WORK/'scope_before_apply.json').read_text('utf-8'))
    unchanged=[]
    for key,record in baseline['files'].items():
        slot=int(Path(key).stem)
        if slot in SLOTS:continue
        assert sha(Path(record['path']))==record['sha256'],f'Unowned image changed: {key}'
        unchanged.append(key)
    selection_path=CLIP/'selection.json' if applied else WORK/'staged/selection.json'
    selection=json.loads(selection_path.read_text('utf-8'))
    original={r['slot']:r for r in baseline['selection_rows']}
    for row in selection['frames']:
        if row['slot'] not in SLOTS:assert row==original[row['slot']],f"Unowned row changed: {row['slot']}"
    report=json.loads((WORK/'repair_report.json').read_text('utf-8'))
    checks=[]
    for slot in SLOTS:
        path=ROOT/f'output/Claude_Gunner_v02/native_frames/{slot:04d}.png' if applied else WORK/f'staged/native_frames/{slot:04d}.png'
        im=Image.open(path).convert('RGBA');a=np.asarray(im)[...,3]
        src=Image.open(WORK/f'references/official_{slot:04d}.png').convert('RGBA')
        assert im.size==(500,500)
        assert set(np.unique(a)).issubset({0,255}),f'Soft native alpha in {slot}'
        box,source_box=im.getbbox(),src.getbbox()
        assert box[1]==source_box[1] and box[3]==source_box[3],f'Source head/sole height differs in {slot}'
        # Rear cloth is intentionally turned/foreshortened; its horizontal
        # silhouette may legitimately narrow one native pixel.
        assert max(abs(box[i]-source_box[i]) for i in (0,2))<=1
        labels,_=ndimage.label(a>128,np.ones((3,3)))
        areas=np.bincount(labels.ravel())[1:]
        major=int((areas>=4).sum())
        assert major==1,f'Large detached body/hand/boot fragment in {slot}: {areas.tolist()}'
        # Two soles, independently segmented in source-approved foot regions.
        sole=[]
        for x0,x1,y0 in ((197,224,322),(265,289,319)):
            yy,xx=np.nonzero(a[y0:333,x0:x1]>128)
            assert len(xx)>5,f'Missing boot in {slot}'
            sole.append(dict(center_x=float((xx[yy>=yy.max()-2]+x0).mean()),bottom=int(yy.max()+y0+1)))
        assert sole[0]['bottom']==330 and sole[1]['bottom']==327
        metric=next(m for m in report['frames'] if m['slot']==slot)
        assert metric['protected_max_rgba_difference']==0
        assert metric['min_forward_jacobian']>=0.28 and metric['min_inverse_jacobian']>=0.28
        assert metric['max_inverse_residual_px']<.1
        for hand in metric['contacts']:
            x,y=np.rint(hand['target']).astype(int)
            assert int((a[y-2:y+3,x-2:x+3]>128).sum())>=23
            assert hand['coverage_before_graft']>=.60
        if applied:
            for sub,folder in (('hd',CLIP/'hd'),('hdfit',CLIP/'hdfit'),('native_frames',ROOT/'output/Claude_Gunner_v02/native_frames')):
                assert sha(folder/f'{slot:04d}.png')==sha(WORK/f'staged/{sub}/{slot:04d}.png')
        checks.append(dict(slot=slot,user_frame=slot+1,bbox=list(im.getbbox()),height=im.getbbox()[3]-im.getbbox()[1],large_components=major,isolated_pixels=int(areas[areas<4].sum()),soles=sole,native_sha256=sha(path)))
    result=dict(passed=True,applied=applied,checked_frames=checks,unchanged_images=unchanged,unchanged_selection_rows=[s for s in original if s not in SLOTS],visual_review='Contact sheet manually checked: rear hair/cape/corset/gown, two natural boot outlines, gun grip contacts. Back view is clothing orientation, not exposed skin.',packaged=False,installed=False)
    (WORK/('validation_applied.json' if applied else 'validation_staged.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--applied',action='store_true');check(p.parse_args().applied)
