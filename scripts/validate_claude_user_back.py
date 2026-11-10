"""Independently inspect the source-skin contamination and 140-frame scope."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
os.environ['PATCH_ID']='claude_gunner'
sys.path.insert(0,str(ROOT/'.claude/skills/dnf-character-patch/scripts'))
from kit import hands
from kit.config import P
from kit.source import layer_world,armed

WORK=ROOT/'output/validation/claude_user_back_reference_2026-11-09'
STAGE=WORK/'staged'
CLIP=P.out/'clips/clip_052_059'
SLOTS=(53,54,55)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text('utf-8'))

def check(applied=False):
    baseline=load(WORK/'scope_before.json');report=load(WORK/'stage_report.json')
    assert {p.name for p in (P.out/'native_frames').glob('*.png')}==set(baseline['all_native_sha256'])
    unchanged={}
    for name,digest in baseline['all_native_sha256'].items():
        if int(Path(name).stem) not in SLOTS:
            actual=sha(P.out/'native_frames'/name);assert actual==digest,name;unchanged[name]=actual
    assert len(unchanged)==140
    old={r['slot']:r for r in baseline['selection']['frames']};current=load(CLIP/'selection.json')
    assert len(current['frames'])==len(old) and {r['slot'] for r in current['frames']}==set(old)
    for row in current['frames']:
        if row['slot'] not in SLOTS:assert row==old[row['slot']]
    for path,digest in baseline['same_clip_hd_hdfit_sha256'].items():
        if int(Path(path).stem) not in SLOTS:assert sha(CLIP/path)==digest
    frames=[];palette=Image.open(ROOT/'output/validation/claude_idle_feet_fix/palette_original.png')
    for slot in SLOTS:
        pre=Image.open(STAGE/'before_graft'/f'{slot:04d}.png').convert('RGBA');post=Image.open(STAGE/'native_frames'/f'{slot:04d}.png').convert('RGBA')
        pa,qa=np.asarray(pre),np.asarray(post);targets=hands.sprite_hands(slot);high=targets[0][2]
        assert np.array_equal(pa[high],qa[high]),'Upper source mask changed the generated head/fist'
        assert np.array_equal(pa[226:248,264:282],qa[226:248,264:282]),'Upper fist/head neighborhood changed after lower-only graft'
        ghost=high&(pa[...,3]==0)
        assert int((qa[ghost,3]>0).sum())==0,'Source head/face ghost pixels returned'
        pre_labels,_=ndimage.label(pa[...,3]>128,np.ones((3,3)));sizes=np.bincount(pre_labels.ravel());sizes[0]=0;main=int(sizes.argmax())
        contacts=[]
        for number,target in enumerate(targets):
            x,y=np.rint(target[:2]).astype(int);solid=int((pa[y-2:y+3,x-2:x+3,3]>128).sum())
            assert solid>=23 and (pa[y-1:y+2,x-1:x+2,3]>128).all()
            assert pre_labels[y,x]==main,'Generated fist floats separately from body'
            if number==0:
                sleeve=int((pre_labels[y+4:y+11,x-5:x+6]==main).sum());assert sleeve>=8,'Generated upper fist does not connect to sleeve'
            else:sleeve=None
            contacts.append(dict(grip=list(target[:2]),before_graft_5x5=solid,before_graft_3x3=9,connected_to_body=True,upper_sleeve_pixels=sleeve))
        labels,_=ndimage.label(qa[...,3]>128,np.ones((3,3)));areas=np.bincount(labels.ravel())[1:]
        assert int((areas>=4).sum())==1 and int(areas[areas<4].sum())==0,'Floating skin/body fragment'
        assert post.getbbox()[1]==221 and post.getbbox()[3]==330
        if applied:
            for sub,folder in [('hd',CLIP/'hd'),('hdfit',CLIP/'hdfit'),('native_frames',P.out/'native_frames')]:assert sha(folder/f'{slot:04d}.png')==sha(STAGE/sub/f'{slot:04d}.png')
        frames.append(dict(slot=slot,user_frame=slot+1,bbox=list(post.getbbox()),upper_source_mask_pixels=int(high.sum()),upper_source_mask_overlap_before=float((pa[...,3][high]>128).mean()),upper_source_ghost_pixels_not_copied=int(ghost.sum()),upper_source_rgba_changes=0,upper_grip_neighborhood_rgba_changes=0,visible_upper_grip_pixel_provenance='Calibrated generated art retained verbatim. Original weapon overlay may expose only a knuckle pixel; no upper source-skin graft is applied.',isolated_pixels=0,contacts=contacts,native_sha256=sha(STAGE/'native_frames'/f'{slot:04d}.png')))
        if slot==53:
            # Deliberately show the rejected upper graft next to the corrected
            # art, so the source of the pink face fragment remains reviewable.
            board=Image.new('RGB',(2000,780),(55,63,80));d=ImageDraw.Draw(board)
            source_skin=layer_world(P.body,slot);hypothetical=hands.graft(pre,slot,palette)
            for row,box in enumerate(((248,218,284,251),(224,246,248,270))):
                for col,(title,im) in enumerate([('Original skin',source_skin),('Generated art before graft',pre),('REJECTED all-skin graft',hypothetical),('Corrected: lower graft only',post),('Corrected + original weapon',armed(post,slot))]):
                    crop=im.crop(box);factor=min(360//crop.width,330//crop.height);crop=crop.resize((crop.width*factor,crop.height*factor),Image.Resampling.NEAREST)
                    board.paste(crop,(col*400+20,row*390+40),crop);d.text((col*400+10,row*390+10),title,fill='white')
            board.save(WORK/'grip_graft_layers_final.png')
    result=dict(passed=True,applied=applied,source_skin_finding='Original high near-weapon visible-skin mask includes the old profile face. The 58.7% overlap is preserved as a diagnostic, not treated as contact accuracy. No upper source skin is copied; the generated fist already occupies the grip and joins its sleeve.',frames=frames,unchanged_other_native_count=140,unchanged_other_native_sha256=unchanged,weapon='Original armed() weapon layers at unchanged source placement',packaged=False,installed=False)
    (WORK/('independent_applied.json' if applied else 'independent_staged.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(dict(passed=True,applied=applied,unchanged_other_native_count=140,frames=[{k:v for k,v in f.items() if k in ['slot','upper_source_ghost_pixels_not_copied','upper_source_rgba_changes','isolated_pixels']} for f in frames]),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--applied',action='store_true');check(p.parse_args().applied)
