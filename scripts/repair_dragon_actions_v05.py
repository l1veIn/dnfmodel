"""Stage only the 29 dragon character frames requested in workbench issues10–16.

No generation, old-source writes, final/build, NPK writes or game access beyond
read-only original weapon diagnostics. Native pixels outside each local edit
are copied exactly; the published palette and other217 frames stay untouched.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
os.environ['PATCH_ID'] = 'gpt_dragon_slayer_v03'
sys.path.insert(0, str(ROOT / '.claude/skills/dnf-character-patch/scripts'))
from kit import art
from kit.config import P
from kit.source import armed, native_world, weapon_layers, weapon_world
from kit.hands import _hilt_gap

BASE = ROOT / 'output/gpt_dragon_slayer_v03'
WORK = ROOT / 'output/dragon_action_repair_v05'
CONFIG = ROOT / 'design/gpt_dragon_slayer_v03/action_repair_v05.json'
TARGETS = sorted(set(range(4)) | set(range(5,13)) | set(range(123,132)) |
                 {230} | set(range(232,236)) | set(range(243,246)))
GROUPS = {'idle_breath':list(range(4)), 'head_nod':list(range(4,9)),
          'hip_breath':list(range(9,13)), 'gesture_planted':list(range(123,132)),
          'kick_match':[229,230,231], 'back_breath':list(range(232,236)),
          'finish_hands':list(range(241,246))}


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p,d): Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def smooth(x): return np.clip(x,0,1)**2*(3-2*np.clip(x,0,1))
def rgba(p): return np.asarray(Image.open(p).convert('RGBA')).copy()


def local_warp(arr, field_x, field_y, *, hard_alpha=False):
    """Premultiplied local inverse warp, leaving every unedited pixel exact."""
    h,w=arr.shape[:2]
    y,x=np.mgrid[:h,:w].astype(np.float32)
    changed=(np.abs(field_x)>0.0001)|(np.abs(field_y)>0.0001)
    pre=arr.astype(np.float32); pre[...,:3]*=pre[...,3:]/255
    out=np.stack([ndimage.map_coordinates(pre[...,c],[y-field_y,x-field_x],order=1,mode='constant',cval=0) for c in range(4)],axis=2)
    out[...,:3]/=np.maximum(out[...,3:]/255,1e-5)
    if hard_alpha:
        # Keep native art's binary-alpha pixel style; RGB is sampled from the
        # source's nearest pixel, so this pass adds no new palette entries.
        ny=np.clip(np.rint(y-field_y).astype(int),0,h-1)
        nx=np.clip(np.rint(x-field_x).astype(int),0,w-1)
        out[...,:3]=arr[ny,nx,:3]
        out[...,3]=(out[...,3]>=127.5)*255
    result=arr.copy(); result[changed]=np.clip(np.rint(out[changed]),0,255).astype(np.uint8)
    return result


def breath_field(x,y,phase,cx,cy):
    # Closed contour deformation around ribcage, rather than moving the upper
    # half as a solid card. Both neck/face and pelvis remain fixed.
    vertical=smooth((y-(cy-13))/5)*(1-smooth((y-(cy+10))/6))
    horizontal=np.exp(-((x-cx)/12)**4)
    envelope=vertical*horizontal
    dx=phase*0.80*np.tanh((x-cx)/5)*envelope
    dy=-phase*0.85*np.exp(-((y-(cy-3))/10)**2)*envelope
    return dx,dy


def nod_field(x,y,amount):
    # Clockwise nod about neck: face tips down while lower neck stays fixed.
    cx,cy=247.0,305.0;theta=np.deg2rad(amount)
    sx=cx+np.cos(theta)*(x-cx)+np.sin(theta)*(y-cy)
    sy=cy-np.sin(theta)*(x-cx)+np.cos(theta)*(y-cy)
    mask=smooth((x-229)/5)*(1-smooth((x-264)/5))*(1-smooth((y-300)/7))*smooth((y-262)/3)
    return (x-sx)*mask,(y-sy)*mask


def arm_field(x,y,frame):
    # The old automatic target was a forearm contact at y301/300. The actual
    # gap between the guard and pommel is y293/292. Extend only that forearm.
    hand_y=299 if frame==243 else 298
    pivot_y=326 if frame==243 else 325
    stretch=(pivot_y-(hand_y-6))/(pivot_y-hand_y)
    sy=pivot_y+(y-pivot_y)/stretch
    progress=np.clip((pivot_y-sy)/(pivot_y-hand_y),0,1)
    mask=smooth((x-223)/5)*(1-smooth((x-243)/5))*smooth((y-283)/5)*(1-smooth((y-323)/5))
    return -2.0*progress*mask,(y-sy)*mask


def hd_field(hd,row,report,func):
    left,top=art.placement(report['window'],row['scale'],row['offset'][0]+row['track'][0],row['offset'][1]+row['track'][1])
    size=round(report['window'][2]*row['scale']);k=size/hd.shape[1]
    y,x=np.mgrid[:hd.shape[0],:hd.shape[1]].astype(np.float32)
    dx,dy=func(left+x*k,top+y*k)
    return dx/k,dy/k


def native_palette():
    # Recover published global pre-hand palette by the original deterministic
    # sampling. It is used only for the newly recovered eight-pixel fist.
    samples=[]
    for sel in sorted((BASE/'clips').glob('*/selection.json')):
        report=json.loads(sel.read_text('utf-8'))
        for row in report['frames'][::3]:
            hd=Image.open(sel.parent/f"hd/{row['slot']:04d}.png").convert('RGBA')
            c,a=art.downscale(hd,(round(report['window'][2]*row['scale']),)*2)
            samples.append((art.sharpen(art.grade(c)),a))
    return art.build_palette(samples,96)


def render_native(hd,row,report,palette):
    size=round(report['window'][2]*row['scale'])
    c,a=art.downscale(Image.fromarray(hd,'RGBA'),(size,size))
    sprite=art.finish(art.sharpen(art.grade(c)),a,palette)
    left,top=art.placement(report['window'],row['scale'],row['offset'][0]+row['track'][0],row['offset'][1]+row['track'][1])
    world=Image.new('RGBA',(900,900));world.paste(sprite,(left+200,top+200))
    return np.asarray(world.crop((200,200,700,700))).copy()


def checker(size):
    y,x=np.mgrid[:size[1],:size[0]];v=((x//8+y//8)%2)*10+42
    return Image.fromarray(np.stack([v,v+4,v+14,np.full_like(v,255)],2).astype(np.uint8),'RGBA')


def review(candidate,frames):
    review_dir=candidate/'review';review_dir.mkdir(exist_ok=True)
    for group,slots in GROUPS.items():
        crop=(180,255,350,392) if group=='kick_match' else (185,250,315,393)
        cw,ch=crop[2]-crop[0],crop[3]-crop[1]
        board=Image.new('RGB',(len(slots)*(cw*2+8),2*(ch*2+28)),(42,46,60));d=ImageDraw.Draw(board)
        anim_before=[];anim_after=[];native_anim=[]
        for j,k in enumerate(slots):
            a=rgba(BASE/f'native_frames/{k:04d}.png');b=frames.get(k,a)
            for row,arr,label in [(0,a,'before'),(1,b,'after')]:
                im=Image.fromarray(arr,'RGBA');part=im.crop(crop).resize((cw*2,ch*2),Image.Resampling.NEAREST)
                x=j*(cw*2+8);y=row*(ch*2+28);board.paste(part,(x,y+22),part);d.text((x+3,y+3),f'{label} user{k+1}/tool{k}',fill='white')
            for arr,store in [(a,anim_before),(b,anim_after)]:
                im=checker((cw,ch));im.alpha_composite(Image.fromarray(arr,'RGBA').crop(crop));store.append(im.resize((cw*3,ch*3),Image.Resampling.NEAREST).convert('RGB'))
            im=checker((cw,ch));im.alpha_composite(Image.fromarray(b,'RGBA').crop(crop));native_anim.append(im.convert('RGB'))
        board.save(review_dir/f'{group}_before_after.jpg',quality=94)
        duration=150 if len(slots)<=5 else 100
        for label,imgs in [('before',anim_before),('after',anim_after),('native',native_anim)]:
            imgs[0].save(review_dir/f'{group}_{label}.webp',save_all=True,append_images=imgs[1:],duration=duration,loop=0,lossless=True)
    # Hand proof always includes actual unchanged game weapon layers.
    board=Image.new('RGB',(3*420,4*240),(42,46,60));d=ImageDraw.Draw(board)
    grip_data=[]
    for j,k in enumerate([243,244,245]):
        a=rgba(BASE/f'native_frames/{k:04d}.png');b=frames[k]
        weapon=Image.new('RGBA',(500,500))
        for layer in weapon_layers():weapon.alpha_composite(weapon_world(k,layer))
        gap=_hilt_gap(np.asarray(weapon)[...,3]>0)
        grip_data.append({'frame':k,'actual_hilt_gap':gap})
        crop=(210,250,265,330) if k<245 else (228,248,272,295)
        for row,(im,label) in enumerate([(armed(native_world(k),k),'original+weapon'),(armed(Image.fromarray(a,'RGBA'),k),'before+weapon'),(armed(Image.fromarray(b,'RGBA'),k),'after+weapon'),(Image.fromarray(b,'RGBA'),'after bare arm')]):
            part=im.crop(crop);part.thumbnail((400,210));part=part.resize((round(part.width*min(400/part.width,210/part.height)),round(part.height*min(400/part.width,210/part.height))),Image.Resampling.NEAREST)
            x=j*420;y=row*240;board.paste(part,(x+10,y+25),part);d.text((x+10,y+4),f'{label} user{k+1}',fill='white')
    board.save(review_dir/'finish_weapon_contact.png')
    return grip_data


def prepare(name='candidate01'):
    if (WORK/'freeze.json').exists():raise SystemExit('This repair is frozen; create a new version.')
    candidate=WORK/name
    if (candidate/'manifest.json').exists():raise SystemExit('Candidate exists; refuse overwrite.')
    native_dir=candidate/'native_frames';native_dir.mkdir(parents=True,exist_ok=True)
    before={str(i):sha(BASE/f'native_frames/{i:04d}.png') for i in range(246)}
    src={i:rgba(BASE/f'native_frames/{i:04d}.png') for i in range(246)}
    selections={};owners={}
    for sel in (BASE/'clips').glob('*/selection.json'):
        rep=json.loads(sel.read_text('utf-8'));selections[sel.parent.name]=rep
        for row in rep['frames']:owners[row['slot']]=(sel.parent.name,row)
    result={};fields={};notes={};hds={}
    y,x=np.mgrid[:500,:500].astype(np.float32)
    breath_groups=[(range(4),0,250,316),(range(9,13),9,244,317),(range(232,236),232,242,315)]
    for slots,base,cx,cy in breath_groups:
        for n,k in enumerate(slots):
            phase=[0.0,0.80,1.20,0.65][n]
            func=lambda xx,yy,p=phase,xx0=cx,yy0=cy:breath_field(xx,yy,p,xx0,yy0)
            dx,dy=func(x,y);result[k]=local_warp(src[base],dx,dy,hard_alpha=True);fields[k]=func
            notes[k]={'issue':10 if base==0 else 12 if base==9 else 15,'base_frame':base,'phase':phase,'method':'local ribcage expansion/lift; face and pelvis fixed'}
    for k,angle in zip(range(5,9),[1.8,3.0,3.8,2.2]):
        func=lambda xx,yy,a=angle:nod_field(xx,yy,a)
        dx,dy=func(x,y);result[k]=local_warp(src[k],dx,dy,hard_alpha=True);fields[k]=func
        notes[k]={'issue':11,'clockwise_nod_degrees':angle,'method':'head-only nod around neck; body untouched'}
    for k in range(123,132):
        # Transition remains at waist; planted entire skirt/legs/heels remain
        # identical to the first requested frame, while9 original arms survive.
        # Transition in the overlapping folds below the hip, away from the
        # changing sleeve roots. A hard horizontal waist splice cuts the arms'
        # long drapes, so use a premultiplied cloth transition here instead.
        weight=smooth((y-324)/14)
        a=src[k].astype(float);b=src[123].astype(float)
        aa=a[...,3:]/255;ba=b[...,3:]/255
        alpha=aa*(1-weight[...,None])+ba*weight[...,None]
        color=(a[...,:3]*aa*(1-weight[...,None])+b[...,:3]*ba*weight[...,None])/np.maximum(alpha,1e-6)
        arr=src[k].copy();transition=(weight>0)&(weight<1)
        palette=np.unique(np.concatenate([src[k][src[k][...,3]>0,:3],src[123][src[123][...,3]>0,:3]]),axis=0)
        if transition.any():
            _,nearest=cKDTree(palette).query(color[transition])
            arr[transition,:3]=palette[nearest]
            arr[transition,3]=(alpha[...,0][transition]>=.5)*255
        arr[weight>=1]=src[123][weight>=1]
        result[k]=arr;notes[k]={'issue':13,'lower_body_reference':123,'fully_locked_from_world_y':338,'method':'original arm frames; soft native-palette transition at lower waist, full fixed hips/legs/heels'}
    result[230]=src[229].copy();notes[230]={'issue':14,'byte_copy_source_frame':229,'method':'explicitly authorized reuse'}
    for k in [243,244]:
        func=lambda xx,yy,frame=k:arm_field(xx,yy,frame)
        dx,dy=func(x,y);result[k]=local_warp(src[k],dx,dy,hard_alpha=True);fields[k]=func
        notes[k]={'issue':16,'method':'extend raised forearm6px toward actual hilt gap, no whole-body shift'}
    # Fifth repair_e drawing extends above the nominal second-row cell. The
    # source itself is intact; include56px from above and compensate placement.
    raw=Image.open(BASE/'parts/raw/poses_repair_e_v1_0.png').convert('RGB')
    cw=raw.width//3;ch=raw.height//2;extra=56
    figure=art.matte(raw.crop((cw,ch-extra,2*cw,raw.height)))
    recovered=Image.new('RGBA',(cw,cw));recovered.paste(figure,(0,0))
    owner,row=owners[245];rep=copy.deepcopy(selections[owner]);newrow=copy.deepcopy(row)
    size=round(rep['window'][2]*row['scale']);comp=round(extra*size/cw)
    newrow['offset'][1]-=comp
    restored=render_native(np.asarray(recovered),newrow,rep,native_palette())
    arr=src[245].copy();roi=(x>=239)&(x<=262)&(y<=281)&(y>=248)
    arr[roi]=restored[roi];result[245]=arr
    notes[245]={'issue':16,'method':'recover complete source fist across former row cut; keep old character elsewhere','raw_crop':[cw,ch-extra,2*cw,raw.height],'hd_top_extension':extra,'world_y_compensation':-comp,'native_patch_roi':[239,248,263,282]}
    hds[245]=np.asarray(recovered).copy()
    for k in TARGETS:
        owner,row=owners[k];rep=selections[owner]
        if k not in hds:
            origin=notes[k].get('base_frame',notes[k].get('byte_copy_source_frame',k))
            oldowner,oldrow=owners[origin];oldrep=selections[oldowner]
            oldhd=rgba(BASE/f'clips/{oldowner}/hd/{origin:04d}.png')
            if k in fields:
                dx,dy=hd_field(oldhd,oldrow,oldrep,fields[k]);hds[k]=local_warp(oldhd,dx,dy)
            elif k in range(123,132):
                basehd=rgba(BASE/f'clips/{owners[123][0]}/hd/0123.png')
                # HD diagnostic is the native-world compositing result lifted
                # back into this frame's source canvas, not a recut operation.
                left,top=art.placement(rep['window'],row['scale'],row['offset'][0]+row['track'][0],row['offset'][1]+row['track'][1]);scale=round(rep['window'][2]*row['scale'])/oldhd.shape[1]
                hy,hx=np.mgrid[:oldhd.shape[0],:oldhd.shape[1]].astype(np.float32)
                ny=top+hy*scale;nx=left+hx*scale
                stage=result[k];hds[k]=np.stack([ndimage.map_coordinates(stage[...,c],[ny,nx],order=0,mode='constant') for c in range(4)],2).astype(np.uint8)
            else:hds[k]=oldhd
        Image.fromarray(result[k],'RGBA').save(native_dir/f'{k:04d}.png')
        dst=candidate/f'clips/{owner}/hd';dst.mkdir(parents=True,exist_ok=True)
        Image.fromarray(hds[k],'RGBA').save(dst/f'{k:04d}.png')
    # Store new-source selection annotations without modifying originals. The
    # native candidate is authoritative; callers must not re-run final on it.
    for owner in {owners[k][0] for k in TARGETS}:
        rep=copy.deepcopy(selections[owner])
        for row in rep['frames']:
            k=row['slot']
            if k in notes:row['action_repair_v05']=notes[k]
            if k==245:row['offset']=newrow['offset'];row['video_frame']='repair_e:4:expanded_top56'
            if k==230:
                origin=copy.deepcopy(owners[229][1]);origin['slot']=230;origin['action_repair_v05']=notes[k];row.update(origin)
        js(candidate/f'clips/{owner}/selection.json',rep)
    grips=review(candidate,result)
    checks={
        'outside_target_native_sha_unchanged':all(sha(BASE/f'native_frames/{k:04d}.png')==before[str(k)] for k in range(246)),
        'unchanged_other_native_frames':217,
        'breathing_face_and_feet_fixed':all(np.array_equal(result[k][:301],src[base][:301]) and np.array_equal(result[k][337:],src[base][337:]) for slots,base,cx,cy in breath_groups for k in slots),
        'gesture_lower_body_pixel_exact':all(np.array_equal(result[k][338:],src[123][338:]) for k in range(123,132)),
        'reuse230_equals_original229_rgba':np.array_equal(result[230],src[229]),
        'finish_arm_outside_local_roi_unchanged':all(np.array_equal(result[k][330:],src[k][330:]) for k in [243,244,245]),
        'recovered_fist_above_old_crop':int(np.count_nonzero((result[245][...,3]>0)&(y<263)))>0,
        'all_breathing_neighbour_transitions_nonzero':all(np.any(result[k]!=result[list(slots)[(j+1)%4]]) for slots,base,cx,cy in breath_groups for j,k in enumerate(slots)),
    }
    assert all(v is True or isinstance(v,int) and v>0 for v in checks.values()),checks
    manifest={'status':'candidate_pending_root_visual_review','base':BASE.relative_to(ROOT).as_posix(),'targets':TARGETS,'frame_count':len(TARGETS),'issues':[10,11,12,13,14,15,16],'native_dir':native_dir.relative_to(ROOT).as_posix(),'hd_root':(candidate/'clips').relative_to(ROOT).as_posix(),'selection_root':(candidate/'clips').relative_to(ROOT).as_posix(),'native_sha256':{str(k):sha(native_dir/f'{k:04d}.png') for k in TARGETS},'baseline_native_sha256':before,'per_frame_repairs':notes,'checks':checks,'actual_weapon_grips':grips,'new_imagegen_calls':0,'new_65535_calls':0,'installed':False,'game_runtime_validated':False,'user_aesthetic_approved':False,'rerender_warning':'Native output is authoritative; do not invoke global final or rebuild from raw HD. Frozen published palette retained for all untouched pixels.'}
    js(candidate/'manifest.json',manifest)
    js(CONFIG,{'candidate_manifest':(candidate/'manifest.json').relative_to(ROOT).as_posix(),'issues':manifest['issues'],'target_frames':TARGETS,'only_local_preparation':True,'source_native':manifest['base']+'/native_frames'})
    print(json.dumps({'candidate':candidate.relative_to(ROOT).as_posix(),'targets':len(TARGETS),'checks':checks},ensure_ascii=False,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',default='candidate01');args=ap.parse_args();prepare(args.candidate)
