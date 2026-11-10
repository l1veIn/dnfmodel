"""Draft-only spatially coherent foreground dragon and real12-cell FX sequence.

No generation/network, encoding, package/game writes, registration or freezing.
First review: layout REVISION. Only after root reviews the full-canvas layout:
  draft REVISION --layout APPROVED_LAYOUT_REVISION
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageOps

from buff_portrait import ROOT,digest,write_mov
from build_buff_alive import fixed_camera,make_fields,displacement,warp_local
from build_dragon_illustrations import eye_states
from build_dragon_buff_v02 import preview_artifacts,compose,alpha_gain,checker

VERSION=ROOT/'output/dragon_buff_v03'
CONFIG=ROOT/'design/gpt_dragon_slayer_v03/buff_v03.json'
SIZE=(470,668)
UI=(335,476)


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def cfg():
    c=json.loads(CONFIG.read_text('utf-8'))
    if [c[k] for k in ('frames','width','height','fps')]!=[19,470,668,15]:raise ValueError('Fixed game contract required')
    if any(len(c[k])!=19 for k in ('figure_opacity','blink_sequence')):raise ValueError('Explicit19-frame character schedule required')
    fx=c['slash_sequence']
    if (fx['columns'],fx['rows'],fx['count'])!=(3,4,12):raise ValueError('Expected root-supplied3x4 action sheet')
    if len(fx['frame_cells'])!=19:raise ValueError('Explicit19-frame shape mapping required')
    return c


def path_for(category,name):
    if category not in ('layouts','drafts','fx_reviews') or not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',name):raise ValueError('Explicit safe revision required')
    p=VERSION/category/name
    if p.exists():raise FileExistsError('Preserve existing review revisions; select a new name')
    return p


def frozen_files():
    files=[]
    for folder in ['output/dragon_buff_v01','output/dragon_buff_v02','output/gpt_dragon_slayer_v03/native_frames']:
        files+=list((ROOT/folder).rglob('*'))
    files+=[ROOT/'design/gpt_dragon_slayer_v03/buff_v01.json',ROOT/'design/gpt_dragon_slayer_v03/buff_v02.json',ROOT/'scripts/build_dragon_buff_v02.py']
    files+=list((ROOT/'output/gpt_dragon_slayer_v03').glob('*.NPK'))
    files+=list((ROOT/'output/gpt_dragon_slayer_v04_preview').glob('*.NPK'))
    return {p.relative_to(ROOT).as_posix():digest(p) for p in files if p.is_file()}


def unchanged(snapshot):
    for name,sha in snapshot.items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen file changed: '+name)


def load_alpha(path):
    im=Image.open(path).convert('RGBA');a=np.asarray(im)[:,:,3]
    if not np.any(a<8) or not np.any(a>180):raise ValueError('Input requires actual alpha and substantial shapes: '+str(path))
    return im


def setup(c):
    b=json.loads((ROOT/c['character_config']).read_text('utf-8'))
    original=load_alpha(ROOT/c['source']);states,eye_report,eyes=eye_states(original,b)
    b['framing']=dict(b['framing']);target=b['framing']['target'];offset=c['portrait_fixed_offset']
    b['framing']['target']=[target[0]+offset[0]/470,target[1]+offset[1]/668]
    base,camera=fixed_camera(original,SIZE,b['framing']);fields,protected,_=make_fields(b,original,base,camera)
    return b,original,states,eye_report,eyes,base,fields,protected


def place_dragon(raw,spec):
    """One fixed transform of the COMPLETE connected foreground object."""
    scale=spec['target_width']/raw.width;theta=math.radians(spec['angle']);ct,st=math.cos(theta),math.sin(theta)
    sx,sy=spec['source_anchor'][0]*raw.width,spec['source_anchor'][1]*raw.height;cx,cy=spec['position']
    affine=(ct/scale,st/scale,sx-(ct*cx+st*cy)/scale,-st/scale,ct/scale,sy-(-st*cx+ct*cy)/scale)
    return raw.convert('RGBa').transform(SIZE,Image.Transform.AFFINE,affine,Image.Resampling.BICUBIC,fillcolor=0).convert('RGBA')


def portrait_matte():
    yy,xx=np.mgrid[:668,:470]
    return np.clip((xx-31)/16,0,1)*np.clip((458-xx)/14,0,1)*np.clip((667-yy)/59,0,1)


def contact_shadow(hero,dragon,spec):
    """Only a real foreground silhouette can cast its narrow shadow onto the hero."""
    a=dragon.getchannel('A');dilation=max(3,2*round(spec['dilation_px']/2)+1)
    blurred=a.filter(ImageFilter.MaxFilter(dilation)).filter(ImageFilter.GaussianBlur(spec['radius_px']))
    amount=np.clip(np.asarray(blurred,dtype=np.float32)-np.asarray(a,dtype=np.float32),0,255)
    amount*=np.asarray(hero.getchannel('A'),dtype=np.float32)/255*spec['opacity']
    shadow=Image.new('RGBA',SIZE,(*spec['rgb'],0));shadow.putalpha(Image.fromarray(np.rint(amount).astype(np.uint8)))
    return shadow


def scene(hero,dragon,c):
    # No head sub-mask, no human-face exclusion and no arbitrary back/front split.
    return compose(hero,contact_shadow(hero,dragon,c['dragon']['contact_shadow']),dragon)


def geometry_signature(c):
    data=dict(portrait_fixed_offset=c['portrait_fixed_offset'],dragon={k:v for k,v in c['dragon'].items() if k!='opacity'},source_sha256=digest(ROOT/c['source']),dragon_sha256=digest(ROOT/c['dragon']['source']))
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def face_overlap(dragon,c):
    yy,xx=np.mgrid[:668,:470];g=c['face_geometry_check'];cx,cy=g['center'];rx,ry=g['radii']
    mask=((xx-cx)/rx)**2+((yy-cy)/ry)**2<1
    a=np.asarray(dragon)[:,:,3]
    return dict(opaque_dragon_pixels_on_human_face=int(np.count_nonzero((a>180)&mask)),face_region_used_for_check_only=True,no_face_hole_or_dragon_head_window=True)


def background_proof(image,out):
    im=image.resize(UI,Image.Resampling.LANCZOS);board=Image.new('RGB',(335*3,500),'white');d=ImageDraw.Draw(board)
    for col,bg in enumerate([Image.new('RGBA',UI,'#11131c'),Image.new('RGBA',UI,'#d9dce3'),checker(UI)]):
        board.paste(Image.alpha_composite(bg,im).convert('RGB'),(col*335,24));d.text((col*335+5,4),'Fixed layout /335x476',fill='black')
    board.save(out/'three_backgrounds_335.jpg',quality=96)


def layout(name):
    c=cfg();out=path_for('layouts',name);frozen=frozen_files();b,original,states,eye_report,eyes,base,fields,protected=setup(c)
    dragon_raw=load_alpha(ROOT/c['dragon']['source']);dragon=place_dragon(dragon_raw,c['dragon']);hero=alpha_gain(base,1,portrait_matte());frame=scene(hero,dragon,c)
    out.mkdir(parents=True);frame.save(out/'layout_native.png');frame.resize(UI,Image.Resampling.LANCZOS).save(out/'layout_335.png');hero.save(out/'portrait_layer.png');dragon.save(out/'complete_foreground_dragon.png');contact_shadow(hero,dragon,c['dragon']['contact_shadow']).save(out/'physical_contact_shadow.png');background_proof(frame,out)
    record=dict(status='static_no_blade_layout_pending_root_review',geometry_sha256=geometry_signature(c),source_sha256=digest(ROOT/c['source']),dragon_source_sha256=digest(ROOT/c['dragon']['source']),config_sha256=digest(CONFIG),no_blade=True,dragon_layer='one_complete_connected_foreground_z_layer',portrait_camera_fixed=True,spatial_check=face_overlap(dragon,c),frozen_files_sha256=frozen)
    unchanged(frozen);save(out/'layout_record.json',record);save(out/'config_snapshot.json',c)
    print(json.dumps(dict(layout=out.relative_to(ROOT).as_posix(),no_blade=True,spatial_check=record['spatial_check']),ensure_ascii=False))


def extract_cells(c,out):
    """Uniform grid extraction; preserve shared frame rectangle and energy anchor."""
    spec=c['slash_sequence'];raw=load_alpha(ROOT/spec['source']);cells=[];records=[]
    (out/'fx_cells').mkdir()
    for k in range(12):
        col,row=k%3,k//3;box=(round(col*raw.width/3),round(row*raw.height/4),round((col+1)*raw.width/3),round((row+1)*raw.height/4))
        cell=raw.crop(box);page=ImageOps.contain(cell,SIZE,Image.Resampling.LANCZOS);canvas=Image.new('RGBA',SIZE);canvas.alpha_composite(page,((470-page.width)//2,(668-page.height)//2))
        a=np.asarray(canvas)[:,:,3];edge=int(max(a[0].max(),a[-1].max(),a[:,0].max(),a[:,-1].max()))
        canvas.save(out/'fx_cells'/f'cell_{k:02d}.png');cells.append(canvas)
        records.append(dict(cell=k,raw_rectangle=list(box),shared_whole_cell_mapping=True,alpha_bbox=canvas.getbbox(),edge_max_alpha=edge,sha256=digest(out/'fx_cells'/f'cell_{k:02d}.png')))
    save(out/'fx_extraction.json',dict(source=spec['source'],source_sha256=digest(ROOT/spec['source']),raw_size=list(raw.size),target_frame=list(SIZE),cells=records,normalized_by='one common full-cell contain transform; no per-shape crop/recenter/rotation'))
    return cells


def tail(cell,amount,dissolve):
    # Only the already-fragmented last drawn cell dissolves; main motion is all12 real shapes.
    yy,xx=np.mgrid[:668,:470];noise=(np.sin(xx*.131+yy*.093)*.5+.5)*.6+(np.sin(xx*.037-yy*.157)*.5+.5)*.4
    mask=np.clip((noise-dissolve)/.16,0,1)
    return alpha_gain(cell,amount,mask)


def cells_review(name):
    c=cfg();out=path_for('fx_reviews',name);frozen=frozen_files();out.mkdir(parents=True);cells=extract_cells(c,out)
    native=Image.new('RGB',(470*3,692*4),'#191725');dn=ImageDraw.Draw(native)
    small=Image.new('RGB',(335*3,500*4),'#191725');ds=ImageDraw.Draw(small)
    for k,im in enumerate(cells):
        xy=(k%3*470,k//3*692+24);native.paste(im,xy,im);dn.text((xy[0]+5,xy[1]-18),f'cell{k:02d} / shared full canvas',fill='white')
        thumb=im.resize(UI,Image.Resampling.LANCZOS);xy=(k%3*335,k//3*500+24);small.paste(thumb,xy,thumb);ds.text((xy[0]+5,xy[1]-18),f'cell{k:02d} /335x476',fill='white')
    native.save(out/'contact_native.jpg',quality=96);small.save(out/'contact_335.jpg',quality=96)
    frames=[im.resize(UI,Image.Resampling.LANCZOS) for im in cells];durations=[round((k+1)*1000/15)-round(k*1000/15) for k in range(12)]
    frames[0].save(out/'sequence_335.webp',save_all=True,append_images=frames[1:],duration=durations,lossless=True,loop=0,exact=True)
    unchanged(frozen);print(json.dumps(dict(fx_review=out.relative_to(ROOT).as_posix(),source_cells=12,global_mapping='258x508 whole cells contained to339x668 at x65; no recenter',encoded=False)))


def draft(name,layout_name):
    c=cfg();approved=VERSION/'layouts'/layout_name/'layout_record.json'
    record=json.loads(approved.read_text('utf-8'))
    if record['geometry_sha256']!=geometry_signature(c):raise ValueError('Static spatial layout changed; review a fresh no-blade layout first')
    out=path_for('drafts',name);frozen=frozen_files();b,original,states,eye_report,eyes,base,fields,protected=setup(c)
    dragon=place_dragon(load_alpha(ROOT/c['dragon']['source']),c['dragon']);out.mkdir(parents=True);(out/'frames').mkdir();cells=extract_cells(c,out)
    frames=[];metrics=[];matte=portrait_matte();tail_by_frame={x['frame']:x for x in c['slash_sequence']['tail_cells']}
    for k in range(19):
        state=c['blink_sequence'][k];state_base,_=fixed_camera(states[state],SIZE,b['framing']);dx,dy,regions=displacement(fields,k,19,max_displacement=2.4);local=warp_local(state_base,dx,dy,protected)
        diff=np.max(np.abs(np.asarray(local).astype(np.int16)-np.asarray(state_base).astype(np.int16)),axis=2)>0
        if np.any(diff&protected):raise ValueError('Protected character geometry drifted')
        hero=alpha_gain(local,c['figure_opacity'][k],matte);front_dragon=alpha_gain(dragon,c['dragon']['opacity'][k]);cell=c['slash_sequence']['frame_cells'][k]
        fx=Image.new('RGBA',SIZE) if cell is None else cells[cell]
        if k in tail_by_frame:
            t=tail_by_frame[k];fx=tail(cells[t['cell']],t['opacity'],t['dissolve'])
        frame=compose(scene(hero,front_dragon,c),fx);frame.save(out/'frames'/f'frame_{k:04d}.png');frames.append(frame)
        metrics.append(dict(frame=k,blink=state,fx_source_cell=cell,fx_placement='identical full-canvas anchor; no frame translation/rotation',camera_translation=[0,0],camera_scale=1,portrait_protected_changed_pixels=0,local_max_displacement=float(np.hypot(dx,dy).max())))
    durations=preview_artifacts(out,frames,c['blink_sequence']);shutil.copy2(ROOT/c['source'],out/'source.png');eyes.save(out/'eye_mask.png')
    previous=json.loads((ROOT/'output/dragon_buff_v01/preview/manifest.json').read_text('utf-8'))
    inputs=[CONFIG,ROOT/c['source'],ROOT/c['dragon']['source'],ROOT/c['slash_sequence']['source'],ROOT/b['eyes']['half'],ROOT/b['eyes']['closed']]
    manifest=dict(title=c['title'],frames=19,size=list(SIZE),fps=15,duration_seconds=19/15,preview_duration_ms=sum(durations),source_illustration='source.png',source_raw_sha256=digest(ROOT/c['source']),source_reference=c['reference'],source_size=list(original.size),sheet_sha256=digest(out/'sheet.png'),sheet_size=[1880,3340],frame_sha256=[digest(out/'frames'/f'frame_{k:04d}.png') for k in range(19)],targets=previous['targets'],installed=False,status='unencoded_unfrozen_continuous_shape_draft',generation=dict(method='Root-supplied connected foreground dragon; real12-cell drawn energy action sequence with a shared fixed frame; original character, true eyelid edits and local hair/cloth motion.'),review=dict(layout=layout_name,revision=name,approval='pending',actual_ui_preview='preview_335.webp',actual_ui_contact='contact_335.jpg'),inputs_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in inputs},frame_metrics=metrics,composition=dict(dragon='single_complete_foreground_object',human_face='fixed upper right, no alpha hole'),warnings=[],bink_encoding=dict(format='Bink1',fps_override=15,alpha='include straight alpha',audio=False,source='frames/frame_0000.png (numbered sequence)'))
    unchanged(frozen);save(out/'manifest.json',manifest);save(out/'config_snapshot.json',c);save(out/'motion_validation.json',dict(eyes=eye_report,protected_pixels_changed=0,spatial_check=face_overlap(dragon,c),frozen_files_sha256=frozen,encoded=False,frame_metrics=metrics))
    print(json.dumps(dict(draft=out.relative_to(ROOT).as_posix(),true_source_shapes=12,no_crescent_sprite_motion=True,encoded=False),ensure_ascii=False))


def freeze(name):
    c=cfg();src=VERSION/'drafts'/name;out=ROOT/c['output']
    if out.exists():raise FileExistsError('Standard candidate already frozen; do not overwrite')
    manifest=json.loads((src/'manifest.json').read_text('utf-8'))
    for name,sha in manifest['inputs_sha256'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Selected draft input changed: '+name)
    for k,sha in enumerate(manifest['frame_sha256']):
        if digest(src/'frames'/f'frame_{k:04d}.png')!=sha:raise ValueError('Selected draft PNG changed')
    frozen=frozen_files();shutil.copytree(src,out)
    code={}
    for path in [Path(__file__).resolve(),ROOT/'scripts/encode_dragon_buff_v03.py',ROOT/'scripts/buff_portrait.py',ROOT/'scripts/build_buff_alive.py',ROOT/'scripts/build_dragon_illustrations.py',ROOT/'scripts/build_dragon_buff_v02.py']:
        target=out/'frozen_code'/path.name;target.parent.mkdir(exist_ok=True);shutil.copy2(path,target)
        code[path.relative_to(ROOT).as_posix()]=dict(snapshot=target.relative_to(out).as_posix(),sha256=digest(target))
    assets={}
    for key,path in [('dragon',ROOT/c['dragon']['source']),('slash_action_sheet',ROOT/c['slash_sequence']['source'])]:
        target=out/'frozen_inputs'/path.name;target.parent.mkdir(exist_ok=True);shutil.copy2(path,target);assets[key]=dict(original=path.relative_to(ROOT).as_posix(),snapshot=target.relative_to(out).as_posix(),sha256=digest(target))
    generation=VERSION/'generation_record.json';shutil.copy2(generation,out/'generation_record_snapshot.json')
    frames=[Image.open(out/'frames'/f'frame_{k:04d}.png').convert('RGBA') for k in range(19)];mov=write_mov(frames,out/'portrait_rgba.mov',15)
    manifest.update(status='prepared_for_review_not_bink_encoded',mov_roundtrip=mov,provenance=dict(builder_code=code,raw_inputs=assets,generation_record=dict(original=generation.relative_to(ROOT).as_posix(),snapshot='generation_record_snapshot.json',sha256=digest(generation)),selected_config='config_snapshot.json',actual_shape_extraction='fx_extraction.json'))
    manifest['review'].update(approval='root_and_independent_visual_selected_draft01',draft_manifest_sha256=digest(src/'manifest.json'))
    save(out/'manifest.json',manifest);save(out/'freeze_record.json',dict(revision=src.name,draft_manifest_sha256=digest(src/'manifest.json'),manifest_sha256=digest(out/'manifest.json'),frame_sha256=manifest['frame_sha256'],mov_roundtrip=mov,encoded=False))
    unchanged(frozen);print(json.dumps(dict(frozen=out.relative_to(ROOT).as_posix(),source_frames_equal_selected=True,mov_roundtrip=mov,encoded=False)))


def register():
    c=cfg();out=ROOT/c['output'];m=json.loads((out/'manifest.json').read_text('utf-8'));r=json.loads((out/'encoding_report.json').read_text('utf-8'))
    if r.get('verified') is not True or r['source_manifest_sha256']!=digest(out/'manifest.json') or r['source_frames_sha256']!=m['frame_sha256'] or r['sha256']!=digest(out/'portrait.bik'):raise ValueError('Verified frozen Bink binding required')
    p=ROOT/'design/gpt_dragon_slayer_v03/workbench/buff.json';old=json.loads(p.read_text('utf-8'));assets=[]
    for a in old['assets']:
        if a.get('version')=='v03':continue
        if a.get('version')=='v02':a.update(id='portrait_v02',purpose='v02旧版对照：用户反馈龙与人物的空间关系、月牙入场需改进；未安装')
        if a.get('version')=='v01':a['id']='portrait_v01'
        assets.append(a)
    assets.insert(0,dict(id='portrait',name='龙娘 buff · 近景龙影 / 连续月刃',version='v03',purpose='连通龙头颈统一前景、真实12形态月刃连续形成/扫过/解体，保留真眨眼与衣发微动；工作台候选，未安装',manifest=c['output']+'/manifest.json',encoding_report=c['output']+'/encoding_report.json'))
    save(p,dict(assets=assets));print(json.dumps(dict(registered=True,main='v03',history=['v02','v01'],installed=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['layout','draft','cells','freeze','register']);p.add_argument('revision',nargs='?');p.add_argument('--layout',dest='layout_name');a=p.parse_args()
    if a.command!='register' and not a.revision:p.error('Explicit revision required')
    if a.command=='draft' and not a.layout_name:p.error('draft requires an explicit root-reviewed --layout')
    {'layout':lambda:layout(a.revision),'draft':lambda:draft(a.revision,a.layout_name),'cells':lambda:cells_review(a.revision),'freeze':lambda:freeze(a.revision),'register':register}[a.command]()
