"""v05 blade-only motion study: fixed screen slash with a moving leading edge.

No network/generation or game/NPK writes. Review motion and full draft first;
freeze/encode/register are explicit commands reserved for the selected candidate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import os
import subprocess
import time

import numpy as np
from PIL import Image,ImageDraw
from scipy.spatial import cKDTree

from buff_portrait import ROOT,digest,write_mov
from build_dragon_buff_v02 import alpha_gain,face_mask,embers,compose

CONFIG=ROOT/'design/gpt_dragon_slayer_v03/buff_v05.json'
VERSION=ROOT/'output/dragon_buff_v05'
SIZE=(470,668);UI=(335,476)


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def settings():
    c=json.loads(CONFIG.read_text('utf-8'))
    if [c[k] for k in ('frames','width','height','fps')]!=[19,470,668,15]:raise ValueError('Current study is19x470x668@15')
    return c


def frozen_files(c):
    v04=ROOT/c['locked_v04'];review=json.loads((v04/'review.json').read_text('utf-8'));result=dict(review['old_files_sha256'])
    paths=list(v04.rglob('*'))+[ROOT/'scripts/build_dragon_buff_v04.py',ROOT/'design/gpt_dragon_slayer_v03/buff_v04.json']
    result.update({p.relative_to(ROOT).as_posix():digest(p) for p in paths if p.is_file()});return result


def unchanged(snapshot):
    for name,sha in snapshot.items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen file changed: '+name)


def lock_base(c):
    """Copy approved actor/dragon/background RGBA without ever rebuilding them."""
    out=VERSION/'base_locked';record_path=out/'base_lock.json'
    if record_path.exists():
        record=json.loads(record_path.read_text('utf-8'))
        for row in record['frames']:
            if digest(ROOT/row['source'])!=row['sha256'] or digest(ROOT/row['copy'])!=row['sha256']:raise ValueError('Locked v04 base changed')
            if digest(ROOT/row['fixed_sparks'])!=row['fixed_sparks_sha256']:raise ValueError('Locked sparks changed')
        return record
    out.mkdir(parents=True);(out/'frames').mkdir();(out/'fixed_sparks').mkdir()
    v04=ROOT/c['locked_v04'];baseline=json.loads((v04/'v02_baseline_config_snapshot.json').read_text('utf-8'));face=face_mask(baseline);rows=[]
    for k in range(19):
        source=v04/'no_foreground_fx_frames'/f'frame_{k:04d}.png';target=out/'frames'/source.name;shutil.copy2(source,target)
        if not np.array_equal(np.asarray(Image.open(source)),np.asarray(Image.open(target))):raise ValueError('Base copy changed RGBA')
        # Keep the original non-blade sparks in an immutable separate plane. Their
        # original v04 suppression/face-light control and timing remain unchanged.
        old_moon=Image.open(v04/'moon_frames'/source.name).convert('RGBA');old_alpha=np.asarray(old_moon.getchannel('A'),dtype=np.float32)/255
        sparks=alpha_gain(alpha_gain(embers(k),1,1-old_alpha),1,1-face*.985);spark_path=out/'fixed_sparks'/source.name;sparks.save(spark_path)
        rows.append(dict(frame=k,source=source.relative_to(ROOT).as_posix(),copy=target.relative_to(ROOT).as_posix(),sha256=digest(source),rgba_max_difference=0,byte_copy=True,fixed_sparks=spark_path.relative_to(ROOT).as_posix(),fixed_sparks_sha256=digest(spark_path)))
    record=dict(source_v04_manifest_sha256=digest(v04/'manifest.json'),frames=rows,actor_or_dragon_rerendered=False,source_base_rgba_difference=0,sparks_recipe='Frozen v02 embers(k), multiplied by (1-original_v04_moon_alpha) and original face-control. This non-blade layer is generated once then SHA-locked.',sparks_helper_sha256=digest(ROOT/'scripts/build_dragon_buff_v02.py'))
    save(record_path,record);return record


def curve_geometry(c):
    p=np.asarray(c['path'],dtype=np.float64);t=np.linspace(0,1,2049)[:,None]
    points=(1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3]
    arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))];s=arc/arc[-1]
    tangent=np.gradient(points,axis=0);tangent/=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-8)
    ss=c['supersampling'];yy,xx=np.mgrid[:668*ss,:470*ss].astype(np.float32);xx=(xx+.5)/ss;yy=(yy+.5)/ss;grid=np.column_stack([xx.ravel(),yy.ravel()]);distance,index=cKDTree(points).query(grid,workers=2)
    nearest_s=s[index].reshape(xx.shape).astype(np.float32);distance=distance.reshape(xx.shape).astype(np.float32)
    return dict(points=points,s=s,tangent=tangent,arc_length=float(arc[-1]),nearest_s=nearest_s,distance=distance,xx=xx,yy=yy)


def palette(c):
    a=np.asarray(Image.open(ROOT/c['material_reference']).convert('RGBA'));rgb=a[:,:,:3].astype(float);alpha=a[:,:,3]
    core=(alpha>170)&(rgb.min(axis=2)>225);violet=(alpha>160)&(rgb[:,:,2]>rgb[:,:,0]*1.25)&(rgb[:,:,2]>rgb[:,:,1]*1.8)&(rgb[:,:,0]>55)
    dark=(alpha>128)&(rgb.max(axis=2)<125)&(rgb[:,:,2]>rgb[:,:,0])
    result={}
    for name,mask,fallback in [('silver',core,[253,247,255]),('violet',violet,[128,45,239]),('ink',dark,[43,16,89])]:result[name]=np.median(rgb[mask],axis=0).tolist() if np.count_nonzero(mask)>20 else fallback
    return result


def smooth(x):
    x=np.clip(x,0,1);return x*x*(3-2*x)


def curve_point(geometry,s):
    p=np.array([np.interp(s,geometry['s'],geometry['points'][:,axis]) for axis in (0,1)])
    tangent=np.array([np.interp(s,geometry['s'],geometry['tangent'][:,axis]) for axis in (0,1)]);tangent/=np.linalg.norm(tangent)
    return p,tangent


def render_ribbon(c,v,geometry,colours,k):
    progress=np.asarray(v['tip_progress'],float);times=np.arange(19,dtype=float)
    # Each SCREEN location acquires one immutable passage time. It is never moved.
    passed=np.interp(geometry['nearest_s'],progress,times).astype(np.float32);age=k-passed;active=age>=0
    life=v['core_life_frames'];remaining=np.clip(1-age/life,0,1);born=smooth(np.maximum(age,0)/.18)
    width=born*remaining**.78*(.55+.45*np.clip(np.sin(np.pi*geometry['nearest_s']),0,1)**1.5)
    # Fixed, smoothly irregular material edge, with no periodic triangle teeth.
    knots=np.linspace(0,1,19);edge_noise=np.random.default_rng(2305).uniform(-.045,.045,len(knots))
    width*=1+np.interp(geometry['nearest_s'],knots,edge_noise)
    brightness=remaining**.8*np.exp(-np.maximum(age,0)/max(life*1.7,.1))*active
    d=geometry['distance'];cross=d/np.maximum(v['violet_half_width']*width,.0001)
    rim_alpha=smooth((1.12-cross)/.24)*brightness
    core=np.exp(-np.minimum(80,(d/np.maximum(v['core_half_width']*width,.0001))**4))*brightness
    lateral=np.clip((cross-.32)/.68,0,1)
    violet=np.asarray(colours['violet'],np.float32)/255;ink=np.asarray(colours['ink'],np.float32)/255;silver=np.asarray(colours['silver'],np.float32)/255
    colour=violet[None,None,:]*(1-lateral[:,:,None])+ink[None,None,:]*lateral[:,:,None]
    core_mix=np.clip(core/np.maximum(brightness,1e-6),0,1);colour=colour*(1-core_mix[:,:,None])+silver[None,None,:]*core_mix[:,:,None]
    fog_life=v['mist_life_frames'];fog_remaining=np.clip(1-age/fog_life,0,1);fog_width=v['glow_half_width']*(1+.14*np.maximum(age,0))
    fog_alpha=np.exp(-.5*(d/np.maximum(fog_width,.001))**2)*fog_remaining**2.3*.28*active*smooth(np.maximum(age,0)/.18)
    alpha=rim_alpha+fog_alpha*(1-rim_alpha);premul=colour*rim_alpha[:,:,None]+violet[None,None,:]*fog_alpha[:,:,None]*(1-rim_alpha[:,:,None])
    tip_s=progress[k];tip=None
    if 0<=tip_s<=1:
        p,tangent=curve_point(geometry,tip_s);tip=p.tolist()
        # The tip is ONLY the same ribbon's tapered leading edge, not a separate
        # oval/star/sprite; recording this point does not paint a projectile.
    rgb=np.divide(premul,alpha[:,:,None],out=np.zeros_like(premul),where=alpha[:,:,None]>1e-7);rgba=np.dstack([rgb,alpha]);image=Image.fromarray(np.rint(np.clip(rgba,0,1)*255).astype(np.uint8)).resize(SIZE,Image.Resampling.LANCZOS)
    path_s=np.linspace(0,1,101);pass_times=np.interp(path_s,progress,times);path_age=k-pass_times;path_remaining=np.clip(1-path_age/life,0,1);path_width=smooth(np.maximum(path_age,0)/.18)*path_remaining**.78*(.55+.45*np.clip(np.sin(np.pi*path_s),0,1)**1.5)
    a=np.asarray(image)
    metric=dict(frame=k,tip_progress=float(tip_s),tip_position=tip,white_core_pixels=int(np.count_nonzero((a[:,:,:3].min(axis=2)>210)&(a[:,:,3]>100))),visible_pixels=int(np.count_nonzero(a[:,:,3]>32)),stationary_path_age=path_age.tolist(),stationary_path_width_factor=path_width.tolist(),sprite_translation=None,sprite_rotation=None)
    return image,metric


def study_boards(out,frames,metrics,label):
    durations=[round((k+1)*1000/15)-round(k*1000/15) for k in range(19)];small=[im.resize(UI,Image.Resampling.LANCZOS) for im in frames]
    frames[0].save(out/'slash_only.webp',save_all=True,append_images=frames[1:],duration=durations,lossless=True,loop=0,exact=True);small[0].save(out/'slash_only_335.webp',save_all=True,append_images=small[1:],duration=durations,lossless=True,loop=0,exact=True)
    contact=Image.new('RGB',(335*4,500*5),'#151321');d=ImageDraw.Draw(contact)
    for k,im in enumerate(small):xy=(335*(k%4),500*(k//4)+24);contact.paste(im,xy,im);d.text((xy[0]+5,xy[1]-18),f'k{k:02d} / {label}',fill='white')
    contact.save(out/'contact_335.jpg',quality=96)
    keys=[7,8,9,10,12];board=Image.new('RGB',(470*5,692),'#151321');dr=ImageDraw.Draw(board)
    for col,k in enumerate(keys):board.paste(frames[k],(470*col,24),frames[k]);dr.text((470*col+5,5),f'k{k:02d} / fixed screen slash',fill='white')
    board.save(out/'keyframes_native.jpg',quality=96)


def motion(name,selected=None):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',name):raise ValueError('Explicit simple revision required')
    c=settings();out=VERSION/'motion_studies'/name
    if out.exists():raise FileExistsError('Preserve previous motion reviews')
    frozen=frozen_files(c);lock=lock_base(c);geometry=curve_geometry(c);colours=palette(c);out.mkdir(parents=True)
    np.savez_compressed(out/'fixed_screen_path.npz',points=geometry['points'],arc_s=geometry['s'],tangent=geometry['tangent'])
    records={}
    for variant,v in c['variants'].items():
        if selected and selected!=variant:continue
        d=out/variant;d.mkdir();(d/'frames').mkdir();frames=[];metrics=[]
        for k in range(19):
            im,metric=render_ribbon(c,v,geometry,colours,k);im.save(d/'frames'/f'frame_{k:04d}.png');frames.append(im);metrics.append(metric)
        study_boards(d,frames,metrics,variant.upper());path_s=np.linspace(0,1,101)
        record=dict(label=v['label'],frames=19,size=list(SIZE),fps=15,path_fixed_in_screen=True,shape_entity_affine_motion=False,path_control_points=c['path'],sampled_path_s=path_s.tolist(),sampled_path_positions=[[float(np.interp(s,geometry['s'],geometry['points'][:,axis])) for axis in (0,1)] for s in path_s],pass_time_at_sample=np.interp(path_s,v['tip_progress'],np.arange(19)).tolist(),core_life_frames=v['core_life_frames'],mist_life_frames=v['mist_life_frames'],frame_metrics=metrics,frame_sha256=[digest(d/'frames'/f'frame_{k:04d}.png') for k in range(19)],encoded=False)
        save(d/'motion_record.json',record);records[variant]=dict(record=(d/'motion_record.json').relative_to(ROOT).as_posix(),frames_sha256=record['frame_sha256'])
    save(out/'study_record.json',dict(status='blade_only_speed_trail_review',base_lock='output/dragon_buff_v05/base_locked/base_lock.json',source_base_rgba_unchanged=True,actor_or_dragon_rerendered=False,path_fixed_in_screen=True,palette_from_original_v02=colours,material_reference=c['material_reference'],material_sha256=digest(ROOT/c['material_reference']),config_sha256=digest(CONFIG),variants=records,encoded=False));save(out/'config_snapshot.json',c)
    unchanged(frozen);save(out/'protected_files.json',frozen);print(json.dumps(dict(motion_study=out.relative_to(ROOT).as_posix(),variants=list(records),blade_only=True,source_base_rgba_difference=0,encoded=False),ensure_ascii=False))


def draft(name,motion_name,variant):
    c=settings();study=VERSION/'motion_studies'/motion_name;study_record=json.loads((study/'study_record.json').read_text('utf-8'))
    if study_record['config_sha256']!=digest(CONFIG):raise ValueError('Motion study config changed; review a new blade-only study')
    source=study/variant;motion_record=json.loads((source/'motion_record.json').read_text('utf-8'));lock=lock_base(c);frozen=frozen_files(c);out=VERSION/'drafts'/name
    if out.exists():raise FileExistsError('Preserve selected draft revisions')
    out.mkdir(parents=True)
    for folder in ['frames','base_frames','fixed_sparks_frames','slash_frames','no_slash_scene_frames']:(out/folder).mkdir()
    frames=[];bindings=[]
    for k,row in enumerate(lock['frames']):
        slash_path=source/'frames'/f'frame_{k:04d}.png'
        if digest(slash_path)!=motion_record['frame_sha256'][k]:raise ValueError('Reviewed motion PNG changed')
        base_path=ROOT/row['copy'];sparks_path=ROOT/row['fixed_sparks'];base=Image.open(base_path).convert('RGBA');sparks=Image.open(sparks_path).convert('RGBA');slash=Image.open(slash_path).convert('RGBA')
        scene=compose(base,sparks);frame=compose(scene,slash);frame.save(out/'frames'/f'frame_{k:04d}.png');scene.save(out/'no_slash_scene_frames'/f'frame_{k:04d}.png');frames.append(frame)
        for path,folder in [(base_path,'base_frames'),(sparks_path,'fixed_sparks_frames'),(slash_path,'slash_frames')]:shutil.copy2(path,out/folder/f'frame_{k:04d}.png')
        if not np.array_equal(np.asarray(Image.open(ROOT/row['source'])),np.asarray(Image.open(out/'base_frames'/f'frame_{k:04d}.png'))):raise ValueError('Approved actor/dragon source base changed')
        bindings.append(dict(frame=k,original_v04_base=row['source'],base_sha256=row['sha256'],base_rgba_max_difference=0,fixed_sparks_sha256=row['fixed_sparks_sha256'],selected_motion_sha256=motion_record['frame_sha256'][k]))
    from build_dragon_buff_v02 import preview_artifacts
    v04=ROOT/c['locked_v04'];original=json.loads((v04/'manifest.json').read_text('utf-8'));baseline=json.loads((v04/'v02_baseline_config_snapshot.json').read_text('utf-8'));durations=preview_artifacts(out,frames,baseline['blink_sequence']);shutil.copy2(v04/'source.png',out/'source.png')
    inputs=[CONFIG,study/'study_record.json',source/'motion_record.json',VERSION/'base_locked/base_lock.json',ROOT/c['material_reference'],v04/'manifest.json',v04/'source.png']
    for row in lock['frames']:inputs.extend([ROOT/row['copy'],ROOT/row['fixed_sparks']])
    inputs.extend(source/'frames'/f'frame_{k:04d}.png' for k in range(19))
    manifest=dict(title=c['title'],frames=19,size=list(SIZE),fps=15,duration_seconds=19/15,preview_duration_ms=sum(durations),source_illustration='source.png',source_raw_sha256=original['source_raw_sha256'],source_size=original['source_size'],source_reference=original['source_reference'],sheet_sha256=digest(out/'sheet.png'),sheet_size=[1880,3340],frame_sha256=[digest(out/'frames'/f'frame_{k:04d}.png') for k in range(19)],targets=original['targets'],installed=False,status='unencoded_unfrozen_fixed_slash_draft',inputs_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in inputs},generation=dict(method='Only the blade changed. Each approved v04 no-blade actor/dragon/background frame is copied byte-for-byte; fixed sparks are locked separately. New blade is a stationary screen Bezier distance-field ribbon illuminated at each location pass_time, aging/narrowing in place; no projectile sprite or separate tip orb.'),composition=dict(locked_v04_base=True,actor_or_dragon_rerendered=False,base_rgba_max_difference=0,blade_face_erasure=False),review=dict(motion_study=motion_name,variant=variant,revision=name,approval='pending'),warnings=[],bink_encoding=dict(format='Bink1',fps_override=15,alpha='include straight alpha',audio=False,source='frames/frame_0000.png (numbered sequence)'))
    save(out/'manifest.json',manifest);save(out/'base_binding.json',dict(frames=bindings,actor_or_dragon_rerendered=False,base_rgba_max_difference=0));save(out/'selected_motion_record.json',motion_record);save(out/'config_snapshot.json',c);unchanged(frozen);save(out/'protected_files.json',frozen)
    print(json.dumps(dict(draft=out.relative_to(ROOT).as_posix(),variant=variant,base_rgba_difference=0,actor_or_dragon_rerendered=False,encoded=False)))


def freeze(name):
    c=settings();src=VERSION/'drafts'/name;out=ROOT/c['output']
    if out.exists():raise FileExistsError('Standard candidate already frozen')
    manifest=json.loads((src/'manifest.json').read_text('utf-8'))
    for path,sha in manifest['inputs_sha256'].items():
        if digest(ROOT/path)!=sha:raise ValueError('Selected source changed: '+path)
    for k,sha in enumerate(manifest['frame_sha256']):
        if digest(src/'frames'/f'frame_{k:04d}.png')!=sha:raise ValueError('Selected draft PNG changed')
    frozen=frozen_files(c);lock_base(c);shutil.copytree(src,out);code={}
    for path in [Path(__file__).resolve(),ROOT/'scripts/buff_portrait.py',ROOT/'scripts/build_dragon_buff_v02.py',ROOT/'scripts/encode_dragon_buff_v03.py']:
        target=out/'frozen_code'/path.name;target.parent.mkdir(exist_ok=True);shutil.copy2(path,target);code[path.relative_to(ROOT).as_posix()]=dict(snapshot=target.relative_to(out).as_posix(),sha256=digest(target))
    reference=ROOT/c['material_reference'];target=out/'frozen_inputs'/reference.name;target.parent.mkdir(exist_ok=True);shutil.copy2(reference,target)
    component_sha={}
    for folder in ['base_frames','fixed_sparks_frames','slash_frames','no_slash_scene_frames']:
        component_sha[folder]=[digest(out/folder/f'frame_{k:04d}.png') for k in range(19)]
    shutil.copy2(VERSION/'base_locked/base_lock.json',out/'base_lock_snapshot.json')
    selected=VERSION/'motion_studies'/manifest['review']['motion_study'];shutil.copy2(selected/'fixed_screen_path.npz',out/'fixed_screen_path.npz');shutil.copy2(selected/'study_record.json',out/'motion_study_snapshot.json')
    frames=[Image.open(out/'frames'/f'frame_{k:04d}.png').convert('RGBA') for k in range(19)];mov=write_mov(frames,out/'portrait_rgba.mov',15)
    manifest.update(status='prepared_for_review_not_bink_encoded',mov_roundtrip=mov,provenance=dict(builder_code=code,material_reference=dict(original=c['material_reference'],snapshot='frozen_inputs/'+reference.name,sha256=digest(reference)),locked_base='base_lock_snapshot.json',base_binding='base_binding.json',component_sha256=component_sha,motion='selected_motion_record.json',fixed_path='fixed_screen_path.npz',selected_config='config_snapshot.json',encoder_reuse='Explicit pure verify(folder,manifest,movie) from frozen encode_dragon_buff_v03.py, with no global/guard monkey patch. Existing local RAD Bink1/Alpha/15fps/NoSound.'))
    manifest['review'].update(approval='root_and_independent_visual_selected_v05_draft02',draft_manifest_sha256=digest(src/'manifest.json'))
    save(out/'manifest.json',manifest);save(out/'freeze_record.json',dict(revision=src.name,draft_manifest_sha256=digest(src/'manifest.json'),manifest_sha256=digest(out/'manifest.json'),frame_sha256=manifest['frame_sha256'],mov_roundtrip=mov,encoded=False));unchanged(frozen)
    print(json.dumps(dict(frozen=out.relative_to(ROOT).as_posix(),base_rgba_difference=0,source_frames_equal_selected=True,mov_roundtrip=mov,encoded=False)))


def encode():
    from encode_dragon_buff_v03 import verify as verify_bink_against_source
    c=settings();out=ROOT/c['output'];manifest=json.loads((out/'manifest.json').read_text('utf-8'));record=json.loads((out/'freeze_record.json').read_text('utf-8'))
    if digest(out/'manifest.json')!=record['manifest_sha256']:raise ValueError('Frozen manifest changed')
    for path,sha in manifest['inputs_sha256'].items():
        if digest(ROOT/path)!=sha:raise ValueError('Frozen input changed: '+path)
    for k,sha in enumerate(manifest['frame_sha256']):
        if digest(out/'frames'/f'frame_{k:04d}.png')!=sha:raise ValueError('Frozen frame changed')
    movie=out/'portrait.bik'
    if movie.exists():raise FileExistsError('Bink already exists; never overwrite')
    frozen=frozen_files(c);tool=ROOT/'tools/downloads/rad_video_tools_2026-10-28/bin/radvideo64.exe';sequence=out/'input_frames.lst';sequence.write_text('\n'.join(str(out/'frames'/f'frame_{k:04d}.png') for k in range(19))+'\n',encoding='utf-8')
    command=[str(tool),'binkc',str(sequence),str(movie),'/Bink1','/Alpha','/ForceFrameRate15','/NoSound','/DataRate1000000','/CPUs4','/AutoClose'];options={}
    if os.name=='nt':
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0;options=dict(startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
    completed=subprocess.run(command,cwd=out,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False,**options)
    if completed.returncode or not movie.is_file():raise RuntimeError('RAD did not produce Bink1')
    report=verify_bink_against_source(out,manifest,movie);now=time.strftime('%Y-%m-%d %H:%M:%S')
    report.update(created=now,verified_at=now,visual_review='root_and_independent_visual_selected_v05_draft02',encoder=dict(name='RAD Video Tools',version='2026.10',file=tool.relative_to(ROOT).as_posix(),sha256=digest(tool),command=command),verifier=dict(script='scripts/encode_dragon_buff_v03.py',sha256=digest(ROOT/'scripts/encode_dragon_buff_v03.py'),snapshot='frozen_code/encode_dragon_buff_v03.py',entrypoint='verify(folder,manifest,movie)',reuse='Explicit pure-function call; no monkey patch or global guard changes.'))
    save(out/'encoding_report.json',report);unchanged(frozen);print(json.dumps(dict(bink=movie.relative_to(ROOT).as_posix(),sha256=report['sha256'],bytes=report['size'],frames=19,fps=15,verified=True,alpha_mae_mean=report['quality']['alpha_mae_mean'],alpha_mae_worst=report['quality']['alpha_mae_worst'])))


def register():
    c=settings();out=ROOT/c['output'];m=json.loads((out/'manifest.json').read_text('utf-8'));r=json.loads((out/'encoding_report.json').read_text('utf-8'))
    if r.get('verified') is not True or r['source_manifest_sha256']!=digest(out/'manifest.json') or r['source_frames_sha256']!=m['frame_sha256'] or r['sha256']!=digest(out/'portrait.bik'):raise ValueError('Verified frozen Bink/source binding required')
    p=ROOT/'design/gpt_dragon_slayer_v03/workbench/buff.json';old=json.loads(p.read_text('utf-8'));assets=[]
    for a in old['assets']:
        if a.get('version')=='v05':continue
        if a.get('version')=='v04':a.update(id='portrait_v04',purpose='v04已认可的龙头/人物/龙框保留作参考；该版刀光有投掷读感，v05仅改刀光，未安装')
        assets.append(a)
    assets.insert(0,dict(id='portrait',name='龙娘 buff · 刀锋掠屏 / 短暂斩痕',version='v05',purpose='保留已确认龙头与人物；刀光一击划过并留下短暂斩痕，随后原位变细淡去；工作台候选，未安装',manifest=c['output']+'/manifest.json',encoding_report=c['output']+'/encoding_report.json'))
    save(p,dict(assets=assets));print(json.dumps(dict(registered=True,main='v05',history=['v04','v03','v02','v01'],installed=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['motion','draft','freeze','encode','register']);p.add_argument('revision',nargs='?');p.add_argument('--variant');p.add_argument('--motion',dest='motion_name');a=p.parse_args()
    if a.command in ('motion','draft','freeze') and not a.revision:p.error('Explicit revision required')
    if a.command=='draft' and (not a.variant or not a.motion_name):p.error('draft requires reviewed --motion and --variant')
    {'motion':lambda:motion(a.revision,a.variant),'draft':lambda:draft(a.revision,a.motion_name,a.variant),'freeze':lambda:freeze(a.revision),'encode':encode,'register':register}[a.command]()
