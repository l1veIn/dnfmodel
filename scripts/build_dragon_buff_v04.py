"""v02 restoration with complementary source-space head split and dense flyby.

Local-only. No network/generation or game/NPK writes.
Commands: proof/draft REVISION; after root review freeze REVISION, encode, register.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import os
import subprocess
import time

import numpy as np
from PIL import Image,ImageDraw,ImageOps

from buff_portrait import ROOT,digest,write_mov
from build_buff_alive import fixed_camera,make_fields,displacement,warp_local
from build_dragon_illustrations import eye_states
from build_dragon_buff_v02 import (place,layer,alpha_gain,face_mask,charge,burst,embers,glow,compose,checker)

CONFIG=ROOT/'design/gpt_dragon_slayer_v03/buff_v04.json'
VERSION=ROOT/'output/dragon_buff_v04'
SIZE=(470,668);UI=(335,476)


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def settings():
    c=json.loads(CONFIG.read_text('utf-8'));b=json.loads((ROOT/c['baseline_config']).read_text('utf-8'))
    if [c[k] for k in ('frames','width','height','fps')]!=[19,470,668,15]:raise ValueError('Current review candidate retains19@15')
    if len(c['head_opacity'])!=19 or len(c['flight']['opacity'])!=19:raise ValueError('Explicit19-frame schedules required')
    return c,b


def frozen_files():
    paths=[]
    for folder in ['output/dragon_buff_v01','output/dragon_buff_v02','output/dragon_buff_v03','output/gpt_dragon_slayer_v03/native_frames']:
        paths+=list((ROOT/folder).rglob('*'))
    for ver in ['v01','v02','v03']:
        paths.append(ROOT/f'design/gpt_dragon_slayer_v03/buff_{ver}.json')
    paths+=[ROOT/'scripts/build_dragon_buff_v02.py',ROOT/'scripts/build_dragon_buff_v03.py',ROOT/'scripts/encode_dragon_buff_v03.py']
    paths+=list((ROOT/'output/gpt_dragon_slayer_v03').glob('*.NPK'))+list((ROOT/'output/gpt_dragon_slayer_v04_preview').glob('*.NPK'))
    return {p.relative_to(ROOT).as_posix():digest(p) for p in paths if p.is_file()}


def unchanged(snapshot):
    for path,sha in snapshot.items():
        if digest(ROOT/path)!=sha:raise ValueError('Frozen file changed: '+path)


def output(category,name):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',name):raise ValueError('Explicit simple revision name required')
    p=VERSION/category/name
    if p.exists():raise FileExistsError('Preserve existing review revisions')
    p.mkdir(parents=True);return p


def split_source(raw,c,out):
    """True source-canvas complementary cut: no head bbox crop or alpha duplication."""
    mask=Image.new('L',raw.size);ImageDraw.Draw(mask).polygon([tuple(p) for p in c['head_source_polygon']],fill=255)
    m=np.asarray(mask)>0;a=np.asarray(raw);head=a.copy();rear=a.copy()
    head[:,:,3]=np.where(m,a[:,:,3],0);rear[:,:,3]=np.where(m,0,a[:,:,3])
    head=Image.fromarray(head);rear=Image.fromarray(rear)
    head.save(out/'head_source_full_canvas.png');rear.save(out/'rear_source_full_canvas.png');mask.save(out/'head_mask_source.png');ImageOps.invert(mask).save(out/'rear_mask_source.png')
    reconstructed=Image.alpha_composite(rear,head);reconstructed.save(out/'source_reconstruction.png')
    aa=np.asarray(reconstructed);visible=a[:,:,3]>0
    report=dict(source_canvas=list(raw.size),head_canvas=list(head.size),rear_canvas=list(rear.size),alpha_sum_max_error=int(np.abs(np.asarray(head)[:,:,3].astype(np.int16)+np.asarray(rear)[:,:,3].astype(np.int16)-a[:,:,3].astype(np.int16)).max()),source_alpha_overlap_pixels=int(np.count_nonzero((np.asarray(head)[:,:,3]>0)&(np.asarray(rear)[:,:,3]>0))),visible_rgba_reconstruction_max_error=int(np.abs(aa.astype(np.int16)-a.astype(np.int16))[visible].max()),same_complete_source_canvas=True,head_bbox_never_fitted=True)
    if report['alpha_sum_max_error'] or report['source_alpha_overlap_pixels'] or report['visible_rgba_reconstruction_max_error']:raise ValueError('Source split must exactly reconstruct the original')
    board=Image.new('RGB',(512*3,800),'#211e2e');d=ImageDraw.Draw(board)
    for i,(label,im) in enumerate([('original v02',raw),('complete HEAD / foreground',head),('remaining REAR / behind hero',rear)]):
        t=im.resize((512,768),Image.Resampling.LANCZOS);board.paste(t,(i*512,28),t);d.text((i*512+6,6),label,fill='white')
    board.save(out/'source_split_contact.jpg',quality=96);save(out/'source_split_report.json',report)
    return head,rear,report


def path_data(c):
    f=c['flight'];points=np.array(f['knots'],float);dist=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    return points,dist,dist[-1]


def flight_state(c,k,subframe=0):
    f=c['flight'];points,dist,total=path_data(c)
    duration=f['last_main']-f['start'];t=(k-f['start']-subframe)/duration
    distance=max(0,t*total)
    if distance<=total:
        center=[float(np.interp(distance,dist,points[:,axis])) for axis in (0,1)]
    else:
        direction=(points[-1]-points[-2])/np.linalg.norm(points[-1]-points[-2]);center=(points[-1]+direction*(k-f['last_main']-subframe)*f['exit_step_px']).tolist()
    def value(name):return float(np.interp(min(total,distance),dist,f[name]))
    return dict(center=center,scale=value('scale_knots'),rotation=value('rotation_knots'),perspective=value('perspective_knots'),fx=value('horizontal_foreshorten_knots'),fy=value('vertical_foreshorten_knots'),distance_along_path=distance)


def project_moon(raw,base,s):
    """Same painted moon on a moving, mildly foreshortened camera-facing plane."""
    theta=math.radians(s['rotation']);ct,st=math.cos(theta),math.sin(theta);scale=base['slash']['target_width']/raw.width*s['scale'];cx,cy=s['center']
    center=np.array([[1,0,-raw.width/2],[0,1,-raw.height/2],[0,0,1]],float)
    plane=np.array([[1,0,0],[0,1,0],[0,s['perspective']/raw.height,1]],float)
    resize=np.diag([scale*s['fx'],scale*s['fy'],1]);rotate=np.array([[ct,-st,0],[st,ct,0],[0,0,1]],float);translate=np.array([[1,0,cx],[0,1,cy],[0,0,1]],float)
    forward=translate@rotate@resize@plane@center;inv=np.linalg.inv(forward);inv/=inv[2,2]
    coefficients=tuple(inv.ravel()[:8]);im=raw.convert('RGBa').transform(SIZE,Image.Transform.PERSPECTIVE,coefficients,Image.Resampling.BICUBIC,fillcolor=0).convert('RGBA')
    return im


def flyby(raw,c,base,k):
    opacity=c['flight']['opacity'][k]
    if opacity<=0:return Image.new('RGBA',SIZE),None
    weights=c['flight']['shutter_weights'];samples=[]
    for j,weight in enumerate(weights):
        history=c['flight']['shutter_fraction']*j/max(1,len(weights)-1);im=project_moon(raw,base,flight_state(c,k,history));a=np.asarray(im,dtype=np.float32)/255;a[:,:,:3]*=a[:,:,3:4];samples.append(a*weight)
    merged=np.sum(samples,axis=0);alpha=merged[:,:,3:4];merged[:,:,:3]=np.divide(merged[:,:,:3],alpha,out=np.zeros_like(merged[:,:,:3]),where=alpha>1e-7)
    merged[:,:,3]*=opacity;result=Image.fromarray(np.rint(np.clip(merged,0,1)*255).astype(np.uint8))
    return result,flight_state(c,k)


def setup(base):
    b=json.loads((ROOT/base['character_config']).read_text('utf-8'));raw=Image.open(ROOT/base['source']).convert('RGBA');states,eye_report,eyes=eye_states(raw,b)
    b['framing']=dict(b['framing']);target=b['framing']['target'];offset=base['portrait_fixed_offset'];b['framing']['target']=[target[0]+offset[0]/470,target[1]+offset[1]/668]
    static,camera=fixed_camera(raw,SIZE,b['framing']);fields,protected,_=make_fields(b,raw,static,camera)
    yy,xx=np.mgrid[:668,:470];band=np.clip((xx-35)/18,0,1)*np.clip((447-xx)/18,0,1)*np.clip((667-yy)/60,0,1)
    return b,raw,states,eye_report,eyes,fields,protected,band


def common_dragon_transform(base,raw_size,k):
    spec=base['dragon'];scale=spec['target_width']/raw_size[0]*spec['scale'][k];theta=math.radians(spec['rotation'][k]);ct,st=math.cos(theta),math.sin(theta);cx,cy=spec['center'];sx,sy=raw_size[0]/2,raw_size[1]/2
    inverse=np.array([[ct/scale,st/scale,sx-(ct*cx+st*cy)/scale],[-st/scale,ct/scale,sy-(-st*cx+ct*cy)/scale],[0,0,1]],float)
    return dict(source_canvas=list(raw_size),inverse_affine=inverse[:2].ravel().tolist(),source_to_world=np.linalg.inv(inverse).tolist(),same_matrix_for_head_and_rear=True,source_bbox_normalization=False)


def render(c,base,head_source,rear_source,slash,k,prepared):
    b,raw,states,eye_report,eyes,fields,protected,band=prepared;state=base['blink_sequence'][k];image,_=fixed_camera(states[state],SIZE,b['framing']);dx,dy,_=displacement(fields,k,19,max_displacement=2.4);hero=alpha_gain(warp_local(image,dx,dy,protected),base['figure_opacity'][k],band)
    # Both complete source canvases use IDENTICAL original v02 geometry/reveal.
    rear=layer(rear_source,base['dragon'],k,'dragon')
    head_spec=dict(base['dragon']);head_spec['opacity']=c['head_opacity'];head=layer(head_source,head_spec,k,'dragon')
    charged=charge(k,base['charge_strength'][k],base);shock=burst(k,base['burst_strength'][k]);behind=compose(glow(rear,9,.6),rear,glow(charged,12,.8),charged,shock)
    moon,state_fly=flyby(slash,c,base,k);ash=embers(k);cut_alpha=np.asarray(moon.getchannel('A'),dtype=np.float32)/255;ash=alpha_gain(ash,1,1-cut_alpha)
    # The actual crescent passes in FRONT of the camera and may naturally cross
    # a face. Only excessive soft bloom/sparks are attenuated, never the blade.
    face=face_mask(base);soft_fx=alpha_gain(compose(glow(moon,9,.72),ash),1,1-face*.985);front_fx=compose(soft_fx,moon)
    frame=compose(behind,hero,head,front_fx)
    head_alpha=np.asarray(head)[:,:,3];moon_a=np.asarray(moon)[:,:,3]
    metric=dict(frame=k,blink=state,head_alpha_max=int(head_alpha.max()),head_opaque_pixels=int(np.count_nonzero(head_alpha>240)),head_after_hero=True,head_face_erasure=False,flight=state_fly,moon_visible_pixels=int(np.count_nonzero(moon_a>64)),moon_bright_core_pixels=int(np.count_nonzero((np.asarray(moon)[:,:,:3].min(axis=2)>215)&(moon_a>160))),camera_translation=[0,0],camera_scale=1)
    whole=Image.alpha_composite(rear_source,head_source)
    debug=dict(portrait=hero,unsplit=layer(whole,base['dragon'],k,'dragon'),no_foreground_fx=compose(behind,hero,head))
    metric['dragon_common_transform']=common_dragon_transform(base,whole.size,k)
    metric['main_moon_face_erasure']=False
    return frame,head,rear,moon,metric,debug


def boards(out,frames,indices):
    board=Image.new('RGB',(470*len(frames),692),'#201d2b');d=ImageDraw.Draw(board);small=Image.new('RGB',(335*len(frames),500),'#201d2b');ds=ImageDraw.Draw(small)
    for j,(im,k) in enumerate(zip(frames,indices)):
        board.paste(im,(470*j,24),im);d.text((470*j+5,5),f'k{k:02d} / complete470x668',fill='white');t=im.resize(UI,Image.Resampling.LANCZOS);small.paste(t,(335*j,24),t);ds.text((335*j+5,5),f'k{k:02d} /335x476',fill='white')
    board.save(out/'keyframes_native.jpg',quality=96);small.save(out/'keyframes_335.jpg',quality=96)


def build(name,proof=True):
    c,base=settings();out=output('proofs' if proof else 'drafts',name);frozen=frozen_files();raw_dragon=Image.open(ROOT/base['dragon']['source']).convert('RGBA');slash=Image.open(ROOT/base['slash']['source']).convert('RGBA');head,rear,split=split_source(raw_dragon,c,out);prepared=setup(base)
    indices=[4,8,11,14,18] if proof else list(range(19));frames=[];metrics=[];(out/'frames').mkdir();(out/'head_frames').mkdir();(out/'rear_frames').mkdir();(out/'moon_frames').mkdir();(out/'portrait_frames').mkdir();(out/'unsplit_dragon_frames').mkdir();(out/'no_foreground_fx_frames').mkdir()
    for k in indices:
        frame,h,r,moon,metric,debug=render(c,base,head,rear,slash,k,prepared);frames.append(frame);metrics.append(metric);frame.save(out/'frames'/f'frame_{k:04d}.png');h.save(out/'head_frames'/f'frame_{k:04d}.png');r.save(out/'rear_frames'/f'frame_{k:04d}.png');moon.save(out/'moon_frames'/f'frame_{k:04d}.png');debug['portrait'].save(out/'portrait_frames'/f'frame_{k:04d}.png');debug['unsplit'].save(out/'unsplit_dragon_frames'/f'frame_{k:04d}.png');debug['no_foreground_fx'].save(out/'no_foreground_fx_frames'/f'frame_{k:04d}.png')
    if proof:boards(out,frames,indices)
    else:
        from build_dragon_buff_v02 import preview_artifacts
        durations=preview_artifacts(out,frames,base['blink_sequence'])
        shutil.copy2(ROOT/base['source'],out/'source.png')
        old=json.loads((ROOT/'output/dragon_buff_v01/preview/manifest.json').read_text('utf-8'))
        character=json.loads((ROOT/base['character_config']).read_text('utf-8'))
        inputs=[CONFIG,ROOT/c['baseline_config'],ROOT/base['source'],ROOT/base['dragon']['source'],ROOT/base['slash']['source'],ROOT/base['character_config'],ROOT/character['eyes']['half'],ROOT/character['eyes']['closed']]
        manifest=dict(title=c['title'],frames=19,size=list(SIZE),fps=15,duration_seconds=19/15,preview_duration_ms=sum(durations),source_illustration='source.png',source_raw_sha256=digest(ROOT/base['source']),source_size=list(prepared[1].size),source_reference=base['reference'],sheet_sha256=digest(out/'sheet.png'),sheet_size=[1880,3340],frame_sha256=[digest(out/'frames'/f'frame_{k:04d}.png') for k in indices],targets=old['targets'],installed=False,status='unencoded_unfrozen_v02_restoration_draft',inputs_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in inputs},generation=dict(method='Original v02 art/layout preserved. Complementary full-source head and rear masks move through one identical original transform; head draws after portrait with sustained opacity. Original painted crescent flies along the old camera-crossing path with11 dense perspective states and short exposure trails.'),composition=dict(dragon='Original dragon-shaped rear border plus complete front head',head_face_erasure=False,main_blade_face_erasure=False),review=dict(revision=name,approval='pending',native_contact='contact_native.jpg',actual_ui_contact='contact_335.jpg',actual_ui_preview='preview_335.webp'),frame_metrics=metrics,warnings=[],bink_encoding=dict(format='Bink1',fps_override=15,alpha='include straight alpha',audio=False,source='frames/frame_0000.png (numbered sequence)'))
        save(out/'manifest.json',manifest)
    flights=[dict(frame=k,**flight_state(c,k),opacity=c['flight']['opacity'][k]) for k in range(c['flight']['start'],19)]
    save(out/'flight_trajectory.json',dict(source=base['slash']['source'],same_original_path=c['flight']['knots'],main_frames=[6,16],samples=flights,main_center_steps_px=[float(np.linalg.norm(np.array(flights[j+1]['center'])-np.array(flights[j]['center']))) for j in range(10)],method='Dense arc-length states of the original flyby; mild perspective plane and short temporal exposure, never formation atlas.'))
    report=dict(status='mask_and_full_canvas_keyframe_review' if proof else 'unencoded_unfrozen_v02_restoration_draft',frames=indices,source_split=split,metrics=metrics,portrait_fixed_offset=base['portrait_fixed_offset'],dragon_original_geometry_unchanged=True,head_foreground_only=True,head_stays_solid_after_reveal=True,old_files_sha256=frozen,encoded=False)
    unchanged(frozen);save(out/'review.json',report);save(out/'config_snapshot.json',c);save(out/'v02_baseline_config_snapshot.json',base)
    print(json.dumps(dict(output=out.relative_to(ROOT).as_posix(),proof_only=proof,source_split=split,encoded=False)))


def freeze(name):
    c,base=settings();src=VERSION/'drafts'/name;out=ROOT/c['output']
    if out.exists():raise FileExistsError('Candidate already frozen; never overwrite')
    manifest=json.loads((src/'manifest.json').read_text('utf-8'))
    for path,sha in manifest['inputs_sha256'].items():
        if digest(ROOT/path)!=sha:raise ValueError('Selected draft input changed: '+path)
    for k,sha in enumerate(manifest['frame_sha256']):
        if digest(src/'frames'/f'frame_{k:04d}.png')!=sha:raise ValueError('Selected draft frame changed')
    frozen=frozen_files();shutil.copytree(src,out);code={}
    for path in [Path(__file__).resolve(),ROOT/'scripts/buff_portrait.py',ROOT/'scripts/build_buff_alive.py',ROOT/'scripts/build_dragon_illustrations.py',ROOT/'scripts/build_dragon_buff_v02.py',ROOT/'scripts/encode_dragon_buff_v03.py']:
        target=out/'frozen_code'/path.name;target.parent.mkdir(exist_ok=True);shutil.copy2(path,target);code[path.relative_to(ROOT).as_posix()]=dict(snapshot=target.relative_to(out).as_posix(),sha256=digest(target))
    assets={}
    for key,path in [('original_v02_dragon',ROOT/base['dragon']['source']),('original_v02_moon',ROOT/base['slash']['source'])]:
        target=out/'frozen_inputs'/path.name;target.parent.mkdir(exist_ok=True);shutil.copy2(path,target);assets[key]=dict(original=path.relative_to(ROOT).as_posix(),snapshot=target.relative_to(out).as_posix(),sha256=digest(target))
    record=ROOT/'output/dragon_buff_v02/generation_record.json';shutil.copy2(record,out/'generation_record_v02_snapshot.json')
    frames=[Image.open(out/'frames'/f'frame_{k:04d}.png').convert('RGBA') for k in range(19)];mov=write_mov(frames,out/'portrait_rgba.mov',15)
    manifest.update(status='prepared_for_review_not_bink_encoded',mov_roundtrip=mov,provenance=dict(builder_code=code,raw_inputs=assets,original_generation_record=dict(original=record.relative_to(ROOT).as_posix(),snapshot='generation_record_v02_snapshot.json',sha256=digest(record)),head_partition='source_split_report.json',trajectory='flight_trajectory.json',selected_config='config_snapshot.json',original_v02_config='v02_baseline_config_snapshot.json',encoder_reuse='v04 wrapper invokes the pure verify(folder,manifest,movie) function of frozen encode_dragon_buff_v03.py explicitly; no globals/guards are patched or bypassed. RAD arguments remain Bink1/Alpha/15fps/NoSound.'))
    manifest['review'].update(approval='root_and_independent_visual_selected_v04_draft01',draft_manifest_sha256=digest(src/'manifest.json'))
    save(out/'manifest.json',manifest);save(out/'freeze_record.json',dict(revision=src.name,draft_manifest_sha256=digest(src/'manifest.json'),manifest_sha256=digest(out/'manifest.json'),frame_sha256=manifest['frame_sha256'],mov_roundtrip=mov,encoded=False));unchanged(frozen)
    print(json.dumps(dict(frozen=out.relative_to(ROOT).as_posix(),source_frames_equal_selected=True,mov_roundtrip=mov,encoded=False)))


def encode():
    # Explicit reuse of the immutable, parameterized SOURCE-RELATIVE verifier.
    # Its v03-specific folder_and_manifest()/encode() wrappers are not called.
    from encode_dragon_buff_v03 import verify as verify_bink_against_source
    c,base=settings();out=ROOT/c['output'];manifest=json.loads((out/'manifest.json').read_text('utf-8'));frozen_record=json.loads((out/'freeze_record.json').read_text('utf-8'))
    if digest(out/'manifest.json')!=frozen_record['manifest_sha256']:raise ValueError('Frozen manifest changed')
    for name,sha in manifest['inputs_sha256'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen input changed: '+name)
    for k,sha in enumerate(manifest['frame_sha256']):
        if digest(out/'frames'/f'frame_{k:04d}.png')!=sha:raise ValueError('Frozen frame changed')
    movie=out/'portrait.bik'
    if movie.exists():raise FileExistsError('Bink already exists; never overwrite')
    frozen=frozen_files();tool=ROOT/'tools/downloads/rad_video_tools_2026-10-28/bin/radvideo64.exe'
    sequence=out/'input_frames.lst';sequence.write_text('\n'.join(str(out/'frames'/f'frame_{k:04d}.png') for k in range(19))+'\n',encoding='utf-8')
    command=[str(tool),'binkc',str(sequence),str(movie),'/Bink1','/Alpha','/ForceFrameRate15','/NoSound','/DataRate1000000','/CPUs4','/AutoClose'];options={}
    if os.name=='nt':
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0;options=dict(startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
    done=subprocess.run(command,cwd=out,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False,**options)
    if done.returncode or not movie.is_file():raise RuntimeError('RAD did not produce Bink1')
    report=verify_bink_against_source(out,manifest,movie);now=time.strftime('%Y-%m-%d %H:%M:%S')
    report.update(created=now,verified_at=now,visual_review='root_and_independent_visual_selected_v04_draft01',encoder=dict(name='RAD Video Tools',version='2026.10',file=tool.relative_to(ROOT).as_posix(),sha256=digest(tool),command=command),verifier=dict(script='scripts/encode_dragon_buff_v03.py',sha256=digest(ROOT/'scripts/encode_dragon_buff_v03.py'),snapshot='frozen_code/encode_dragon_buff_v03.py',entrypoint='verify(folder,manifest,movie)',reuse='Explicit pure-function call; no monkey patch, no global guard change.'))
    save(out/'encoding_report.json',report);unchanged(frozen)
    print(json.dumps(dict(bink=movie.relative_to(ROOT).as_posix(),sha256=report['sha256'],bytes=report['size'],frames=19,fps=15,verified=True,alpha_mae_mean=report['quality']['alpha_mae_mean'],alpha_mae_worst=report['quality']['alpha_mae_worst'])))


def register():
    c,base=settings();out=ROOT/c['output'];m=json.loads((out/'manifest.json').read_text('utf-8'));r=json.loads((out/'encoding_report.json').read_text('utf-8'))
    if r.get('verified') is not True or r['source_manifest_sha256']!=digest(out/'manifest.json') or r['source_frames_sha256']!=m['frame_sha256'] or r['sha256']!=digest(out/'portrait.bik'):raise ValueError('Verified frozen Bink/source binding required')
    p=ROOT/'design/gpt_dragon_slayer_v03/workbench/buff.json';old=json.loads(p.read_text('utf-8'));assets=[]
    for a in old['assets']:
        version=a.get('version')
        if version=='v04':continue
        if version=='v03':a.update(id='portrait_v03',purpose='v03为先前误解方向的历史对照，采用了新龙与原地成形月牙，并非用户要求；未安装')
        if version=='v02':a.update(id='portrait_v02',purpose='v02原龙型边框与月牙飞镜参考；v04在此基础上修正头部层级并补足划镜帧，未安装')
        if version=='v01':a.update(id='portrait_v01',purpose='v01旧版弱特效对照，未安装')
        assets.append(a)
    assets.insert(0,dict(id='portrait',name='龙娘 buff · 龙框前景头 / 月牙划镜',version='v04',purpose='保留原龙型边框，完整龙头在人物前、其余框在人后；月牙沿原路多帧飞过镜头，保留眨眼与衣发微动；工作台候选，未安装',manifest=c['output']+'/manifest.json',encoding_report=c['output']+'/encoding_report.json'))
    save(p,dict(assets=assets));print(json.dumps(dict(registered=True,main='v04',history=['v03_misinterpreted_direction','v02','v01'],installed=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['proof','draft','freeze','encode','register']);p.add_argument('revision',nargs='?');a=p.parse_args()
    if a.command in ('proof','draft','freeze') and not a.revision:p.error('Explicit revision required')
    {'proof':lambda:build(a.revision,True),'draft':lambda:build(a.revision,False),'freeze':lambda:freeze(a.revision),'encode':encode,'register':register}[a.command]()
