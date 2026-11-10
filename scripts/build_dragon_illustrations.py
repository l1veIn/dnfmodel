"""Prepare dragon v04 artwork and a distinct silver-wing buff; no paid calls/game writes.

Commands: static, buff, cutins. Packager stage/package is intentionally separate.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from buff_portrait import ROOT, digest, write_mov
from build_buff_alive import fixed_camera, make_fields, displacement, warp_local
from hero_cutin_video import key_magenta

DESIGN = ROOT / 'design/gpt_dragon_slayer_v03'
OUT = ROOT / 'output/dragon_illustrations_v04'
SCOPE = ROOT / 'output/validation/awakening_completion_2026-11-10/scope.json'
FAMILIES = ['weapon', 'darktempler', 'demonslayer', 'blade', 'vagabond']


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def scope():
    return json.loads(SCOPE.read_text('utf-8-sig'))['projects']['dragon']


def family(path):
    if any(x in path for x in ['weapon', 'swordmaster', 'majesty']): return 'weapon'
    if any(x in path for x in ['darktempl', 'punishment']): return 'darktempler'
    if any(x in path for x in ['demonslayer', 'deicide']): return 'demonslayer'
    if any(x in path for x in ['blade', 'vendetta']): return 'blade'
    if any(x in path for x in ['vegabond', 'vagabond', 'swordempress']): return 'vagabond'
    raise ValueError(path)


def seed_dir(name):
    return OUT / 'video_seeds' / ('weapon_v2' if name == 'weapon' else name)


def geometry(row):
    return next(x for x in row['frame_geometry'] if x.get('link') is None)


def overlay(row, paths):
    return dict(source_npk=row['source_npk'], path=row['path'], frame_paths=paths,
                frame_mode='canvas', allow_geometry_change=True, preserve_empty_frames=True)


def package_config(overlays):
    s=scope()
    return dict(title='GPT 龙娘 v04 · 五职业一觉、全部切入与银翼 buff',
                base_npk=s['base_npk'], base_sha256=s['base_npk_sha256'],
                output='output/gpt_dragon_slayer_v04', npk_name='A_GPTDragon_FSlayer_v04.NPK',
                protect_paths=['output/gpt_dragon_slayer_v03/native_frames'], overlays=overlays,
                note='Stage only until root visual QA. No installation, no paid API calls. Original sprite entries retained.')


def static():
    """Intentional close art crops on each official canvas, never landscape containment."""
    s=scope(); master={}; records=[]; overlays=[]
    crop_center={'weapon':.64,'darktempler':.57,'demonslayer':.61,'blade':.58,'vagabond':.59}
    for name in FAMILIES:
        source=seed_dir(name)/'first_frame.png'
        keyed=key_magenta(Image.open(source).convert('RGB'))
        d=OUT/'static'/name; d.mkdir(parents=True,exist_ok=True)
        keyed.save(d/'source_rgba.png'); master[name]=keyed
    contact=Image.new('RGB',(415*3,365*4),'#252733');draw=ImageDraw.Draw(contact)
    for i,row in enumerate(s['awakening']):
        name=family(row['path']); g=geometry(row); size=(g['cw'],g['ch'])
        im=master[name]; event=row.get('variant_kind')=='event_alternate_art'
        # 415:339 official aspect. Events receive a closer portrait, not an old original.
        src_h=im.height*(.90 if event else 1.0); src_w=src_h*size[0]/size[1]
        cx=im.width*(crop_center[name] + (.015 if event else 0))
        x=max(0,min(im.width-src_w,cx-src_w/2)); y=0
        page=im.transform(size,Image.Transform.AFFINE,(src_w/size[0],0,x,0,src_h/size[1],y),Image.Resampling.BICUBIC)
        # The artwork is a close cut-in; taper the intentional lower canvas crop softly.
        arr=np.array(page); yy=np.arange(size[1])[:,None]
        fade=np.clip((size[1]-1-yy)/17,0,1)
        arr[:,:,3]=np.rint(arr[:,:,3]*fade).astype(np.uint8);page=Image.fromarray(arr)
        stem=Path(row['path']).stem; target=OUT/'static'/stem/'frame_0000.png';target.parent.mkdir(parents=True,exist_ok=True);page.save(target)
        rel=target.relative_to(ROOT).as_posix();overlays.append(overlay(row,[rel]))
        record=dict(path=row['path'],family=name,variant_kind=row.get('variant_kind'),source=seed_dir(name).relative_to(ROOT).as_posix()+'/first_frame.png',source_sha256=digest(seed_dir(name)/'first_frame.png'),source_crop=[x,y,x+src_w,y+src_h],canvas=list(size),output=rel,sha256=digest(target),alpha_range=list(page.getchannel('A').getextrema()))
        records.append(record)
        thumb=page.copy();thumb.thumbnail((415,339));xy=((i%3)*415,(i//3)*365+22);contact.paste(thumb,xy,thumb);draw.text((xy[0]+3,xy[1]-18),stem,fill='white')
    contact.save(OUT/'static_contact.jpg',quality=95)
    save(OUT/'static_manifest.json',dict(frames=records,status='prepared_for_visual_review',method='Five new identity-preserving hero keyarts, keyed before intentional uniform portrait crop; aliases mapped by family; official canvas retained.'))
    cfg=package_config(overlays);cfg['incomplete_cutins']=True
    save(DESIGN/'illustrations_v04_static.json',cfg)
    print(json.dumps(dict(static=len(records),contact='output/dragon_illustrations_v04/static_contact.jpg')))


def eye_states(original,cfg):
    masks=[]
    for poly in cfg['eyes']['polygons']:
        m=Image.new('L',original.size);ImageDraw.Draw(m).polygon([tuple(p) for p in poly],fill=255);m=m.filter(ImageFilter.GaussianBlur(1.5));masks.append(m)
    union=Image.fromarray(np.maximum.reduce([np.asarray(m) for m in masks]))
    states={'open':original};reports={}
    for name in ['half','closed']:
        raw=Image.open(ROOT/cfg['eyes'][name]).convert('RGBA')
        if raw.size!=original.size:raise ValueError('Eye edit changed registration size')
        state=Image.composite(raw,original,union);state.putalpha(original.getchannel('A'));states[name]=state
        delta=np.max(np.abs(np.array(state).astype(np.int16)-np.array(original).astype(np.int16)),axis=2)
        reports[name]=dict(changed_eye_pixels=int(np.count_nonzero(delta)),outside_mask_changed=int(np.count_nonzero(delta[np.array(union)==0])),source_sha256=digest(ROOT/cfg['eyes'][name]))
        if reports[name]['outside_mask_changed']:raise ValueError('Eye patch changed outside eyes')
    return states,reports,union


def wing_paths():
    # Curved silver feathers, independent code-native geometry behind the character.
    return [[(66,592),(90,470),(122,385),(197,254),(388,61)],
            [(70,553),(126,475),(161,398),(239,288),(395,105)],
            [(87,520),(168,459),(216,380),(276,290),(403,153)],
            [(102,491),(198,448),(259,376),(322,292),(411,204)]]


def buff_fx(k,size):
    scale=3; w,h=size;back=Image.new('RGBA',(w*scale,h*scale));d=ImageDraw.Draw(back)
    def line(points,fill,width):d.line([(round(x*scale),round(y*scale)) for x,y in points],fill=fill,width=max(1,round(width*scale)),joint='curve')
    # A silver wing opens diagonally; the silhouette is never a pair of vertical rails.
    gain=[190,245,230,220,210,180,125,90,73,65,58,53,49,45,42,40,38,35,32][k]
    for i,p in enumerate(wing_paths()):
        offset=(k-3)*1.2 if k<7 else 4.8
        p=[(x+offset,y-offset*.8) for x,y in p]
        line(p,(123,100,215,int(gain*.7)),7-i*.7);line(p,(221,213,255,gain),1.2)
        if k < 2:
            line(p[-2:],(248,245,255,255),.9)
    # Motif on the back wing: six small interlaced loops echo her existing knot clasps.
    if k>=4:
        for j in range(6):
            angle=j*math.pi/3;cx=352+11*math.cos(angle);cy=568+11*math.sin(angle)
            r=[int((cx-12)*scale),int((cy-17)*scale),int((cx+12)*scale),int((cy+17)*scale)]
            d.ellipse(r,outline=(206,195,255,100),width=2)
    # Deterministic sparse shards follow the slash, away from her eyes.
    for j in range(18):
        age=k-j%6
        if age<0:continue
        x=76+(j*71)%328+age*2.2;y=618-(j*89)%530-age*6
        if 140<x<310 and 110<y<240:continue
        alpha=max(0,185-age*15);r=2+(j%3)
        poly=[(x,y-r*2),(x+r*.6,y),(x,y+r*2),(x-r*.6,y)]
        d.polygon([(round(x*scale),round(y*scale)) for x,y in poly],fill=(225,219,255,alpha))
    return back.resize(size,Image.Resampling.LANCZOS)


def buff():
    cfg=json.loads((DESIGN/'buff_v01.json').read_text('utf-8'))
    out=ROOT/cfg['output'];out.mkdir(parents=True,exist_ok=True);(out/'frames').mkdir(exist_ok=True)
    original=Image.open(ROOT/cfg['source']).convert('RGBA');states,eye_report,eye_mask=eye_states(original,cfg)
    base,camera=fixed_camera(original,(470,668),cfg['framing'])
    fields,protected,_=make_fields(cfg,original,base,camera)
    Image.fromarray((protected*255).astype(np.uint8)).save(out/'protected.png');eye_mask.save(out/'eye_mask.png')
    for f in fields:Image.fromarray(np.rint(f['weight']*255).astype(np.uint8)).save(out/(f['config']['name']+'_mask.png'))
    yy,xx=np.mgrid[:668,:470];frames=[];metrics=[];local_frames=[]
    # Distinct irregular vertical aperture; character is locked, material edges drift.
    left=57+18*np.sin(yy/160);right=414-16*np.cos(yy/175)
    band=np.clip((xx-left)/4,0,1)*np.clip((right-xx)/4,0,1)
    band*=np.clip((667-yy)/60,0,1)
    for k in range(19):
        state=cfg['blink_sequence'][k];state_base,_=fixed_camera(states[state],(470,668),cfg['framing'])
        dx,dy,region=displacement(fields,k,19,max_displacement=2.4)
        local=warp_local(state_base,dx,dy,protected);local_frames.append(local)
        a=np.array(local);phase=[-495,-350,-200,-45,130,310,520][min(k,6)]
        rank=(xx-235)+.52*(yy-334)
        reveal=np.clip((phase-rank)/22+.5,0,1)
        # No subject translation/scaling, only a single diagonal wing-shaped reveal.
        a[:,:,3]=np.rint(a[:,:,3]*band*reveal).astype(np.uint8)
        figure=Image.fromarray(a)
        # Violet backing is shaped by figure alpha, not a rectangular panel.
        shadow=figure.getchannel('A').filter(ImageFilter.GaussianBlur(8));sh=np.array(shadow)
        backing=Image.new('RGBA',(470,668),(24,20,52,0));backing.putalpha(Image.fromarray(np.rint(sh*.32).astype(np.uint8)))
        frame=buff_fx(k,(470,668));frame=Image.alpha_composite(frame,backing);frame=Image.alpha_composite(frame,figure)
        # Bright leading blade is brief, with no opaque flash on her face.
        if 1<=k<=5:
            fx=Image.new('RGBA',(470,668));z=ImageDraw.Draw(fx)
            p1=(phase+235+.52*334,0);p2=(phase+235-.52*(668-334),668)
            z.line([p1,p2],fill=(229,224,255,[0,95,190,215,170,90][k]),width=3)
            # Exclude the face so eye-line reads through the effect.
            fm=np.array(fx);fm[100:225,140:312,3]=0;frame=Image.alpha_composite(frame,Image.fromarray(fm))
        frame.save(out/'frames'/f'frame_{k:04d}.png');frames.append(frame)
        original_base=np.array(state_base);ld=np.array(local);changed=np.max(np.abs(ld.astype(np.int16)-original_base.astype(np.int16)),axis=2)>0
        if np.any(changed & protected):raise ValueError('Protected face/body pixels drifted')
        metrics.append(dict(frame=k,blink=state,reveal_threshold=phase,camera_translation=[0,0],camera_scale=1,local_changed_pixels=int(np.count_nonzero(changed)),protected_changed_pixels=0,max_displacement_px=float(np.hypot(dx,dy).max()),regions=region))
    durations=[round((k+1)*1000/15)-round(k*1000/15) for k in range(19)]
    frames[0].save(out/'preview.webp',save_all=True,append_images=frames[1:],duration=durations,lossless=True,loop=0,exact=True)
    sheet=Image.new('RGBA',(470*4,668*5));contact=Image.new('RGB',(188*4,285*5),'#242632');dr=ImageDraw.Draw(contact)
    for k,im in enumerate(frames):
        sheet.alpha_composite(im,(k%4*470,k//4*668));t=im.resize((188,267),Image.Resampling.LANCZOS);xy=(k%4*188,k//4*285+18);contact.paste(t,xy,t);dr.text((xy[0]+3,xy[1]-15),str(k+1)+' '+cfg['blink_sequence'][k],fill='white')
    sheet.save(out/'sheet.png');contact.save(out/'contact.jpg',quality=95);base.save(out/'static_base.png')
    mov=write_mov(frames,out/'portrait_rgba.mov',15)
    targets=[dict(relative_to_video_character='Cutscene_buf/'+x['file'],official_sha256=x['sha256']) for x in scope()['buff_targets']]
    report=dict(camera_locked=True,protected_changed_pixels=0,eyes=eye_report,mov_roundtrip=mov,local_phase_endpoint_equal=bool(np.array_equal(np.asarray(local_frames[0]),np.asarray(local_frames[-1]))),frame_metrics=metrics)
    save(out/'motion_validation.json',report)
    manifest=dict(title=cfg['title'],frames=19,size=[470,668],fps=15,duration_seconds=19/15,preview_duration_ms=sum(durations),source_reference=cfg['reference'],source_illustration=cfg['source'],source_raw_sha256=digest(ROOT/cfg['source']),source_size=list(original.size),generation=dict(method='Built-in imagegen original transparent hero and individually edited eyelids; fixed camera, root-pinned local hair/cloth deformation; original silver wing and diagonal slash compositing.'),sheet_sha256=digest(out/'sheet.png'),sheet_size=list(sheet.size),frame_sha256=[digest(out/'frames'/f'frame_{k:04d}.png') for k in range(19)],frame_metrics=metrics,mov_roundtrip=mov,targets=targets,installed=False,status='prepared_for_review_not_bink_encoded',composition=dict(mode='irregular_vertical_closeup',framing=cfg['framing'],intentional_canvas_crop=True),alignment=dict(method='one constant uniform camera; fixed face/body; only local materials and eye patches'),local_motion=dict(validation='motion_validation.json'),warnings=[],bink_encoding=dict(format='Bink 1',fps_override=15,alpha='include straight alpha',audio=False,source='frames/frame_0000.png (numbered sequence)'))
    save(out/'manifest.json',manifest)
    print(json.dumps(dict(buff=cfg['output'],frames=19,mov_roundtrip=mov,eye_report=eye_report)))


def cutins(preview=False):
    """Resample completed real Grok videos to all 10 families/15 official targets."""
    import av
    s=scope();src={};records=[]
    selected=['weapon'] if preview else FAMILIES
    for name in selected:
        prepared=sorted((OUT/'video'/f'{name}_neo'/'frames').glob('frame_*.png'))
        if prepared:
            src[name]=[Image.open(p).convert('RGBA') for p in prepared]
            continue
        path=OUT/'video'/f'{name}_neo'/'source.mp4'
        if not path.is_file():
            # Shared tool records the actual downloaded basename in job.json.
            candidates=list((OUT/'video'/f'{name}_neo').glob('*.mp4'))
            if len(candidates)!=1:raise FileNotFoundError(f'Need paid source video for {name}; root submits only')
            path=candidates[0]
        with av.open(str(path)) as c:src[name]=[f.to_image().convert('RGB') for f in c.decode(video=0)]
        if len(src[name])<8:raise ValueError('Cutin needs genuine continuous video, not static placeholders')
    overlays=json.loads((DESIGN/'illustrations_v04_static.json').read_text('utf-8'))['overlays']
    for row in s['cutin']:
        name=family(row['path'])
        if name not in selected:continue
        count=row['source_entry']['frame_count'];g=geometry(row);size=(g['cw'],g['ch'])
        stem=Path(row['path']).stem;d=OUT/'cutin'/stem;d.mkdir(parents=True,exist_ok=True);paths=[]
        indices=np.rint(np.linspace(0,len(src[name])-1,count)).astype(int).tolist()
        for k,j in enumerate(indices):
            keyed=src[name][j] if src[name][j].mode=='RGBA' else key_magenta(src[name][j]);page=keyed.resize(size,Image.Resampling.LANCZOS);p=d/f'frame_{k:04d}.png';page.save(p);paths.append(p.relative_to(ROOT).as_posix())
        overlays.append(overlay(row,paths));records.append(dict(path=row['path'],family=name,frames=count,canvas=list(size),video_indices=indices,source_video=next(iter((OUT/'video'/f'{name}_neo').glob('*.mp4'))).relative_to(ROOT).as_posix()))
    suffix='_preview' if preview else ''
    pending=[r['path'] for r in s['cutin'] if family(r['path']) not in selected]
    save(OUT/f'cutin_manifest{suffix}.json',dict(status='partial_workbench_preview' if preview else 'prepared_for_visual_review',entries=records,pending_paths=pending,source='Continuous generated Grok source video; uniformly resampled for neo/nonneo families; tagged aliases separately preserve official contracts. No static stand-ins.'))
    cfg=package_config(overlays)
    if preview:
        cfg.update(title='GPT 龙娘 v04_preview · 一觉与拔刀切入预览（其余四源片待补）',output='output/gpt_dragon_slayer_v04_preview',npk_name='A_GPTDragon_FSlayer_v04_preview.NPK',pending_paths=pending,completion_status='partial_workbench_preview',coverage=dict(awakening_paths=12,cutin_paths=len(records),cutin_families=2,pending_cutin_paths=len(pending),pending_source_videos=4),note='Root-authorized review candidate only. Five new one-awakening families cover all12 static paths; one real3s Grok video covers swordmaster neo+majesty variants. Remaining12 cutin paths retain source assets and are explicitly pending. No final v04 release, no installation.')
    save(DESIGN/f'illustrations_v04{suffix}.json',cfg);print(json.dumps(dict(awakening=len(s['awakening']),cutins=len(records),overlays=len(overlays),pending_paths=pending)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['static','buff','cutins','cutins-preview']);a=p.parse_args()
    {'static':static,'buff':buff,'cutins':cutins,'cutins-preview':lambda:cutins(True)}[a.command]()
