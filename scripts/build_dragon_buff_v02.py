"""Local layered dragon buff v02. Draft first; freeze only an approved draft.

No network, generation calls, encoding or game writes. Commands:
  draft REVISION       -> new unencoded native +335px QA sample
  freeze REVISION      -> copy the root-reviewed sample to the standard preview
  register             -> workbench registration after separate Bink verification
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
from PIL import Image, ImageDraw, ImageFilter

from buff_portrait import ROOT, digest, write_mov
from build_buff_alive import fixed_camera, make_fields, displacement, warp_local
from build_dragon_illustrations import eye_states

CONFIG=ROOT/'design/gpt_dragon_slayer_v03/buff_v02.json'
VERSION=ROOT/'output/dragon_buff_v02'
SIZE=(470,668)
UI_SIZE=(335,476)
SS=3


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def load():
    cfg=json.loads(CONFIG.read_text('utf-8'))
    if [cfg[x] for x in ('frames','width','height','fps')]!=[19,470,668,15]:
        raise ValueError('The game contract is 19 frames,470x668,15fps')
    for name in ('figure_opacity','blink_sequence','slash_core_width','charge_strength','burst_strength'):
        if len(cfg[name])!=19:raise ValueError(name+' must explicitly cover all19 frames')
    for name in ('dragon','slash'):
        for key in ('opacity','scale','rotation','reveal'):
            if len(cfg[name][key])!=19:raise ValueError(name+'.'+key+' must cover all19 frames')
    return cfg


def frozen_files():
    """Enforce that this worker never mutates the original buff or approved sprite base."""
    files=[ROOT/'design/gpt_dragon_slayer_v03/buff_v01.json',ROOT/'scripts/build_dragon_illustrations.py']
    files+=list((ROOT/'output/dragon_buff_v01').rglob('*'))
    files+=list((ROOT/'output/gpt_dragon_slayer_v03/native_frames').rglob('*'))
    files+=list((ROOT/'output/gpt_dragon_slayer_v03').glob('*.NPK'))
    files+=list((ROOT/'output/gpt_dragon_slayer_v04_preview').glob('*.NPK'))
    return {str(p.relative_to(ROOT)):digest(p) for p in files if p.is_file()}


def verify_frozen(before):
    for path,sha in before.items():
        if digest(ROOT/path)!=sha:raise ValueError('Frozen file changed: '+path)


def alpha_gain(image,value,mask=None):
    a=np.array(image);factor=value if mask is None else value*mask
    a[:,:,3]=np.rint(a[:,:,3]*factor).clip(0,255).astype(np.uint8)
    return Image.fromarray(a)


def tint_alpha(alpha,rgb):
    result=Image.new('RGBA',SIZE,(*rgb,0));result.putalpha(alpha);return result


def face_mask(cfg):
    yy,xx=np.mgrid[:668,:470].astype(np.float32)
    c=cfg['face_protection'];cx,cy=c['center'];rx,ry=c['radii']
    distance=np.sqrt(((xx-cx)/rx)**2+((yy-cy)/ry)**2)
    feather=c['soft_edge']/max(rx,ry)
    m=np.clip((1+feather-distance)/feather,0,1)
    return m*m*(3-2*m)


def place(image,spec,k):
    """One premultiplied affine per effect, independent of the locked portrait camera."""
    scale=spec['target_width']/image.width*spec['scale'][k]
    theta=math.radians(spec['rotation'][k]);ct,st=math.cos(theta),math.sin(theta)
    cx,cy=spec.get('center_path',[spec['center']]*19)[k];sx,sy=image.width/2,image.height/2
    affine=(ct/scale,st/scale,sx-(ct*cx+st*cy)/scale,
            -st/scale,ct/scale,sy-(-st*cx+ct*cy)/scale)
    return image.convert('RGBa').transform(SIZE,Image.Transform.AFFINE,affine,Image.Resampling.BICUBIC,fillcolor=0).convert('RGBA')


def layer(image,spec,k,kind):
    result=place(image,spec,k);yy,xx=np.mgrid[:668,:470]
    reveal=spec['reveal'][k]
    if kind=='dragon':
        # Shape expands from the upper-left dragon head through its wings and tail.
        rank=np.sqrt(((xx-100)/490)**2+((yy-100)/760)**2)
        ripple=.026*np.sin(yy/39+xx/45)
        mask=np.clip((reveal*1.6-rank+ripple)/.12,0,1)
    else:
        rank=np.clip((.64*xx+.36*(668-yy))/540,0,1)
        mask=np.clip((reveal-rank)/.16+.5,0,1)
    return alpha_gain(result,spec['opacity'][k],mask)


def hi_image():
    im=Image.new('RGBA',(470*SS,668*SS));return im,ImageDraw.Draw(im)


def pts(points):return [(round(x*SS),round(y*SS)) for x,y in points]


def ellipse(d,box,fill=None,outline=None,width=1):
    d.ellipse(tuple(round(x*SS) for x in box),fill=fill,outline=outline,width=max(1,round(width*SS)))


def finish(im):return im.resize(SIZE,Image.Resampling.LANCZOS)


def bezier_band(points,width,progress=1):
    p=np.array(points,dtype=np.float32);t=np.linspace(0,max(.001,progress),180)[:,None]
    q=(1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3]
    tangent=np.gradient(q,axis=0);normal=np.column_stack([-tangent[:,1],tangent[:,0]])
    normal/=np.maximum(np.linalg.norm(normal,axis=1,keepdims=True),1e-8)
    profile=np.sin(np.linspace(0,math.pi,len(q)))**.65
    half=normal*(width*profile[:,None]/2)
    return np.vstack([q+half,(q-half)[::-1]]).tolist()


def fx_point(point,spec,k):
    scale=spec['target_width']/1024*spec['scale'][k]
    theta=math.radians(spec['rotation'][k]);ct,st=math.cos(theta),math.sin(theta)
    dx,dy=point[0]-512,point[1]-768;cx,cy=spec['center']
    return cx+scale*(ct*dx-st*dy),cy+scale*(st*dx+ct*dy)


def charge(k,strength,cfg):
    im,d=hi_image()
    if strength<=0:return finish(im)
    # Precise dragon-eye glint and wing-edge charge, never a spotlight on the girl.
    cx,cy=fx_point((467,360),cfg['dragon'],k)
    length=3+strength*7;height=1+strength*2
    q=[(cx-length,cy-height),(cx+length,cy+height*.15),(cx+length*.15,cy+height),(cx-length*.6,cy+height*.2)]
    d.polygon(pts(q),fill=(253,245,255,255))
    for j,source in enumerate([[(475,86),(655,35),(890,125),(995,187)],[(913,313),(975,539),(1005,743)]]):
        points=[fx_point(p,cfg['dragon'],k) for p in source]
        length=max(2,round(len(points)*min(1,.42+k*.16)))
        d.line(pts(points[:length]),fill=(125,63,224,round(strength*220)),width=round((6+strength*4)*SS),joint='curve')
        d.line(pts(points[:length]),fill=(242,227,255,round(strength*235)),width=round((1.3+strength*1.6)*SS),joint='curve')
    return finish(im)


def burst(k,strength):
    im,d=hi_image()
    if strength<=0:return finish(im)
    cx,cy=237,437;age=max(0,k-5);radius=22+age*29
    # Broken expanding shock front and filled wedges, materially different every frame.
    for ring in range(2):
        r=radius-ring*19
        if r<1:continue
        segments=15
        for j in range(segments):
            a=j*math.tau/segments+age*.045;span=.22 if j%3 else .31
            outer=[(cx+math.cos(a+t)*(r+5+strength*6),cy+math.sin(a+t)*(r+5+strength*6)*.72) for t in np.linspace(0,span,12)]
            inner=[(cx+math.cos(a+t)*(r-3),cy+math.sin(a+t)*(r-3)*.72) for t in np.linspace(span,0,12)]
            d.polygon(pts(outer+inner),fill=(221,209,255,round(strength*(210-ring*55))))
    for j in range(12):
        a=j*math.tau/12+.12
        r0=radius*.62;r1=radius+34+22*math.sin(j*2.1)
        q=[(cx+math.cos(a)*r0,cy+math.sin(a)*r0*.7),
           (cx+math.cos(a+.025)*r1,cy+math.sin(a+.025)*r1*.7),
           (cx+math.cos(a+.09)*(radius*.83),cy+math.sin(a+.09)*(radius*.83)*.7)]
        d.polygon(pts(q),fill=(155,125,241,round(strength*175)))
    return finish(im)


def slash_core(k,width):
    im,d=hi_image()
    if width<=0:return finish(im)
    p=[(-90,653),(58,424),(343,417),(526,160)]
    progress=[0,0,0,0,0,0,.38,.7,1,1,1,1,1,1,1,1,1,1,1][k]
    for factor,rgb,a in [(2.1,(75,49,158),155),(1.5,(148,112,246),205),(1,(218,203,255),240),(.52,(255,254,255),255)]:
        d.polygon(pts(bezier_band(p,width*factor,progress)),fill=(*rgb,a))
    return finish(im)


def embers(k):
    im,d=hi_image()
    if k<5:return finish(im)
    for j in range(64):
        birth=5+(j*11)%9;age=k-birth
        if age<0:continue
        a=(j*2.3999632297)+.24;speed=6+(j*13)%17
        radial=18+(j*37)%67+speed*age
        x=240+math.cos(a)*radial+((j*29)%39-19);y=438+math.sin(a)*radial*.8-age*2.7+((j*43)%35-17)
        if not -20<x<490 or not -20<y<688:continue
        length=(6+j%9)*max(.18,1-age/18)
        thickness=(2.2+j%4)*max(.25,1-age/18)
        alpha=max(0,236-age*10)
        tx,ty=math.cos(a),math.sin(a);nx,ny=-ty,tx
        q=[(x+tx*length,y+ty*length),(x+nx*thickness,y+ny*thickness),(x-tx*length*.65,y-ty*length*.65),(x-nx*thickness,y-ny*thickness)]
        d.polygon(pts(q),fill=(239,231,255,alpha))
        # A tapering violet trail separates fast shards from small static glitter.
        trail=[(x+nx*thickness*.5,y+ny*thickness*.5),(x-tx*(length+age*2),y-ty*(length+age*2)),(x-nx*thickness*.5,y-ny*thickness*.5)]
        d.polygon(pts(trail),fill=(146,109,239,round(alpha*.65)))
    return finish(im)


def glow(layer,radius,gain=1):
    a=layer.getchannel('A').filter(ImageFilter.GaussianBlur(radius));a=a.point(lambda x:round(min(255,x*gain)))
    return tint_alpha(a,(126,94,220))


def compose(*images):
    result=Image.new('RGBA',SIZE)
    for im in images:result=Image.alpha_composite(result,im)
    return result


def effects(cfg,dragon,slash,k,face):
    aura=layer(dragon,cfg['dragon'],k,'dragon')
    charge_layer=charge(k,cfg['charge_strength'][k],cfg);shock=burst(k,cfg['burst_strength'][k])
    behind=compose(glow(aura,9,.6),aura,glow(charge_layer,12,.8),charge_layer,shock)
    cut=layer(slash,cfg['slash'],k,'slash');core=slash_core(k,cfg['slash_core_width'][k]);ash=embers(k)
    # Separate floating shards from the blade itself; no repeated purple chip/teeth
    # pattern is stamped over the clean silver core during its single transit.
    cut_alpha=np.asarray(cut.getchannel('A').filter(ImageFilter.GaussianBlur(2)),dtype=np.float32)/255
    ash=alpha_gain(ash,1,1-cut_alpha)
    # Only the dragon's left head/jaw can pass in front of peripheral hair.
    # Its eye and teeth remain readable; the human face stays in a separate plane.
    yy,xx=np.mgrid[:668,:470]
    head_distance=np.sqrt(((xx-131)/104)**2+((yy-194)/100)**2)
    head_window=np.clip((1.2-head_distance)/.32,0,1)
    head_front=alpha_gain(aura,1.36 if k>=12 else .94,head_window)
    foreground=compose(head_front,glow(cut,9,.72),cut,glow(core,7,.6),core,ash)
    # Soft elliptical exclusion preserves face readability without a rectangular hole.
    foreground=alpha_gain(foreground,1,1-face*.985)
    return behind,foreground


def validate_asset(path):
    image=Image.open(path).convert('RGBA');a=np.array(image)[:,:,3]
    if min(image.size)<512:raise ValueError('FX input too small: '+str(path))
    if not np.any(a<8) or not np.any(a>200):raise ValueError('FX requires actual transparent and opaque shapes')
    return image


def checker(size,tile=20):
    yy,xx=np.mgrid[:size[1],:size[0]];pattern=((yy//tile+xx//tile)%2)[...,None]
    rgb=np.array([174,178,190])+pattern*np.array([39,39,39]);return Image.fromarray(rgb.astype(np.uint8)).convert('RGBA')


def preview_artifacts(out,frames,blink):
    durations=[round((k+1)*1000/15)-round(k*1000/15) for k in range(19)]
    small=[im.resize(UI_SIZE,Image.Resampling.LANCZOS) for im in frames]
    frames[0].save(out/'preview.webp',save_all=True,append_images=frames[1:],duration=durations,lossless=True,loop=0,exact=True)
    small[0].save(out/'preview_335.webp',save_all=True,append_images=small[1:],duration=durations,lossless=True,loop=0,exact=True)
    sheet=Image.new('RGBA',(470*4,668*5));native=Image.new('RGB',(470*4,692*5),'#232333');cn=ImageDraw.Draw(native)
    contact=Image.new('RGB',(335*4,500*5),'#232333');cs=ImageDraw.Draw(contact)
    for k,(im,thumb) in enumerate(zip(frames,small)):
        sheet.alpha_composite(im,(k%4*470,k//4*668))
        xy=(k%4*470,k//4*692+24);native.paste(im,xy,im);cn.text((xy[0]+5,xy[1]-18),f'{k+1:02d}  {blink[k]}',fill='white')
        xy=(k%4*335,k//4*500+24);contact.paste(thumb,xy,thumb);cs.text((xy[0]+5,xy[1]-18),f'{k+1:02d}  {blink[k]}  335px',fill='white')
    sheet.save(out/'sheet.png');native.save(out/'contact_native.jpg',quality=96);contact.save(out/'contact_335.jpg',quality=96)
    proof=Image.new('RGB',(335*3,500*4),'white');dp=ImageDraw.Draw(proof)
    for row,k in enumerate([3,7,9,16]):
        for col,bg in enumerate([Image.new('RGBA',UI_SIZE,'#11131c'),Image.new('RGBA',UI_SIZE,'#d9dce3'),checker(UI_SIZE)]):
            cell=Image.alpha_composite(bg,small[k]);xy=(col*335,row*500+24);proof.paste(cell.convert('RGB'),xy);dp.text((xy[0]+5,xy[1]-18),f'Frame{k+1} / 335x476',fill='black')
    proof.save(out/'alpha_backgrounds_335.jpg',quality=96)
    return durations


def revision_path(name):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',name):raise ValueError('Simple explicit revision name required')
    return VERSION/'drafts'/name


def draft(name):
    cfg=load();out=revision_path(name)
    if out.exists():raise FileExistsError('Choose a new sample revision; existing drafts are preserved')
    frozen=frozen_files();base_cfg=json.loads((ROOT/cfg['character_config']).read_text('utf-8'))
    original=Image.open(ROOT/cfg['source']).convert('RGBA');states,eye_report,eye_mask=eye_states(original,base_cfg)
    base_cfg['framing']=dict(base_cfg['framing'])
    original_target=base_cfg['framing']['target'];offset=cfg.get('portrait_fixed_offset',[0,0])
    base_cfg['framing']['target']=[original_target[0]+offset[0]/470,original_target[1]+offset[1]/668]
    dragon=validate_asset(ROOT/cfg['dragon']['source']);slash=validate_asset(ROOT/cfg['slash']['source'])
    base,camera=fixed_camera(original,SIZE,base_cfg['framing']);fields,protected,_=make_fields(base_cfg,original,base,camera)
    face=face_mask(cfg);yy,xx=np.mgrid[:668,:470];band=np.clip((xx-35)/18,0,1)*np.clip((447-xx)/18,0,1)*np.clip((667-yy)/59,0,1)
    frames=[];fx_frames=[];metrics=[];out.mkdir(parents=True);(out/'frames').mkdir();(out/'fx_frames').mkdir()
    previous=None
    for k in range(19):
        state=cfg['blink_sequence'][k];state_base,_=fixed_camera(states[state],SIZE,base_cfg['framing'])
        dx,dy,regions=displacement(fields,k,19,max_displacement=2.4);local=warp_local(state_base,dx,dy,protected)
        changed=np.max(np.abs(np.asarray(local).astype(np.int16)-np.asarray(state_base).astype(np.int16)),axis=2)>0
        if np.any(changed&protected):raise ValueError('Protected portrait pixels drifted')
        reveal=cfg['figure_opacity'][k]
        figure=alpha_gain(local,1,reveal*band)
        behind,front=effects(cfg,dragon,slash,k,face);fx=compose(behind,front)
        frame=compose(behind,figure,front)
        frame.save(out/'frames'/f'frame_{k:04d}.png');fx.save(out/'fx_frames'/f'frame_{k:04d}.png')
        a=np.array(fx);delta=None if previous is None else np.max(np.abs(a.astype(np.int16)-previous.astype(np.int16)),axis=2)
        roi=np.array(front)[:,:,3][(face>.98)]
        metrics.append(dict(frame=k,blink=state,beat=next(b['name'] for b in cfg['beats'] if b['frames'][0]<=k<=b['frames'][1]),camera_translation=[0,0],camera_scale=1,portrait_protected_changed_pixels=0,local_max_displacement=float(np.hypot(dx,dy).max()),fx_alpha_pixels_gt64=int(np.count_nonzero(a[:,:,3]>64)),fx_white_core_pixels=int(np.count_nonzero((a[:,:,:3].min(axis=2)>215)&(a[:,:,3]>160))),fx_changed_pixels_gt12=0 if delta is None else int(np.count_nonzero(delta>12)),foreground_face_alpha_max=int(roi.max()),dragon_scale=cfg['dragon']['scale'][k],slash_width=cfg['slash_core_width'][k],local_regions=regions))
        previous=a;frames.append(frame);fx_frames.append(fx)
    durations=preview_artifacts(out,frames,cfg['blink_sequence'])
    shutil.copy2(ROOT/cfg['source'],out/'source.png');base.save(out/'static_base.png');eye_mask.save(out/'eye_mask.png')
    sha_inputs={str(p.relative_to(ROOT)):digest(p) for p in [CONFIG,ROOT/cfg['character_config'],ROOT/cfg['source'],ROOT/cfg['dragon']['source'],ROOT/cfg['slash']['source'],ROOT/base_cfg['eyes']['half'],ROOT/base_cfg['eyes']['closed']]}
    target_manifest=json.loads((ROOT/'output/dragon_buff_v01/preview/manifest.json').read_text('utf-8'))
    manifest=dict(title=cfg['title'],frames=19,size=[470,668],fps=15,duration_seconds=19/15,preview_duration_ms=sum(durations),source_reference=cfg['reference'],source_raw_sha256=digest(ROOT/cfg['source']),source_illustration='source.png',source_size=list(original.size),sheet_sha256=digest(out/'sheet.png'),sheet_size=[1880,3340],frame_sha256=[digest(out/'frames'/f'frame_{k:04d}.png') for k in range(19)],targets=target_manifest['targets'],installed=False,status='unencoded_unfrozen_effect_draft',generation=dict(method='Root-generated independent alpha dragon and thick slash art; temporally shaped energy accumulation, dragon reveal, single silver slash, expanding shock-front and moving embers. Existing transparent character and true eyelid patch only.'),frame_metrics=metrics,inputs_sha256=sha_inputs,review=dict(revision=name,native_contact='contact_native.jpg',actual_ui_contact='contact_335.jpg',actual_ui_preview='preview_335.webp',transparent_background_proof='alpha_backgrounds_335.jpg',approval='pending'),composition=dict(mode='giant_dragon_and_single_crescent',intentional_canvas_crop=True),warnings=[],bink_encoding=dict(format='Bink1',fps_override=15,alpha='include straight alpha',audio=False,source='frames/frame_0000.png (numbered sequence)'))
    save(out/'manifest.json',manifest)
    report=dict(locked_portrait_camera=True,protected_pixels_changed=0,face_foreground_max_alpha=max(x['foreground_face_alpha_max'] for x in metrics),eyes=eye_report,actual_workbench_size=list(UI_SIZE),fx_unique_frames=len({digest(out/'fx_frames'/f'frame_{k:04d}.png') for k in range(19)}),frozen_before_sha256=frozen,frame_metrics=metrics,encoded=False,visual_review='pending')
    verify_frozen(frozen);save(out/'motion_validation.json',report)
    save(out/'config_snapshot.json',cfg)
    print(json.dumps(dict(draft=str(out.relative_to(ROOT)),frames=19,fx_unique_frames=report['fx_unique_frames'],face_foreground_max_alpha=report['face_foreground_max_alpha'],encoded=False),ensure_ascii=False))


def freeze(name):
    """This explicit command is reserved for root after its visual review."""
    cfg=load();src=revision_path(name);out=ROOT/cfg['output']
    if out.exists():raise FileExistsError('Standard preview already frozen; do not overwrite')
    manifest=json.loads((src/'manifest.json').read_text('utf-8'))
    for path,sha in manifest['inputs_sha256'].items():
        if digest(ROOT/path)!=sha:raise ValueError('Reviewed sample input changed: '+path)
    for k,sha in enumerate(manifest['frame_sha256']):
        if digest(src/'frames'/f'frame_{k:04d}.png')!=sha:raise ValueError('Reviewed sample frame changed')
    frozen=frozen_files();shutil.copytree(src,out)
    # Preserve the selected build implementation and the root-provided FX record.
    code_snapshot={}
    for path in [Path(__file__).resolve(),ROOT/'scripts/buff_portrait.py',ROOT/'scripts/build_buff_alive.py',ROOT/'scripts/build_dragon_illustrations.py']:
        target=out/'frozen_code'/path.name;target.parent.mkdir(exist_ok=True);shutil.copy2(path,target)
        code_snapshot[path.relative_to(ROOT).as_posix()]=dict(snapshot=target.relative_to(out).as_posix(),sha256=digest(target))
    fx_snapshot={}
    for name in ('dragon','slash'):
        original_fx=ROOT/cfg[name]['source'];target=out/'frozen_inputs'/original_fx.name;target.parent.mkdir(exist_ok=True);shutil.copy2(original_fx,target)
        fx_snapshot[name]=dict(original=cfg[name]['source'],snapshot=target.relative_to(out).as_posix(),sha256=digest(target))
    record=VERSION/'generation_record.json';shutil.copy2(record,out/'generation_record_snapshot.json')
    frames=[Image.open(out/'frames'/f'frame_{k:04d}.png').convert('RGBA') for k in range(19)]
    roundtrip=write_mov(frames,out/'portrait_rgba.mov',15)
    manifest.update(status='prepared_for_review_not_bink_encoded',mov_roundtrip=roundtrip)
    manifest['provenance']=dict(builder_code=code_snapshot,raw_fx=fx_snapshot,generation_record=dict(original=record.relative_to(ROOT).as_posix(),snapshot='generation_record_snapshot.json',sha256=digest(record)),selected_config_snapshot='config_snapshot.json')
    manifest['review'].update(approval='root_selected_this_draft_for_freeze',draft_manifest_sha256=digest(src/'manifest.json'))
    save(out/'manifest.json',manifest);verify_frozen(frozen)
    save(out/'freeze_record.json',dict(revision=name,draft_manifest_sha256=digest(src/'manifest.json'),manifest_sha256=digest(out/'manifest.json'),frame_sha256=manifest['frame_sha256'],mov_roundtrip=roundtrip,encoded=False))
    print(json.dumps(dict(frozen=str(out.relative_to(ROOT)),mov_roundtrip=roundtrip,encoded=False)))


def register():
    cfg=load();out=ROOT/cfg['output'];manifest=json.loads((out/'manifest.json').read_text('utf-8'));report=json.loads((out/'encoding_report.json').read_text('utf-8'))
    if report.get('verified') is not True or report['source_manifest_sha256']!=digest(out/'manifest.json') or report['source_frames_sha256']!=manifest['frame_sha256'] or report['sha256']!=digest(out/'portrait.bik'):
        raise ValueError('Encode/verify frozen sample before registration')
    path=ROOT/'design/gpt_dragon_slayer_v03/workbench/buff.json';old=json.loads(path.read_text('utf-8'))
    assets=[a for a in old['assets'] if a.get('version')!='v02']
    for a in assets:
        if a['id']=='portrait':a['id']='portrait_v01';a['purpose']='用户反馈特效过弱，保留v01旧版对照；新版见v02白龙降临，未安装'
    assets.insert(0,dict(id='portrait',name='龙娘 buff · 白龙降临 / 银月断空',version='v02',purpose='巨大银白龙影压场、单次银月斩爆与流散余烬，保留眨眼/衣发微动；工作台候选，未安装',manifest=cfg['output']+'/manifest.json',encoding_report=cfg['output']+'/encoding_report.json'))
    save(path,dict(assets=assets));print(json.dumps(dict(registered=True,encoded=True,installed=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['draft','freeze','register']);p.add_argument('revision',nargs='?');a=p.parse_args()
    if a.command!='register' and not a.revision:p.error('draft/freeze need an explicit sample revision')
    {'draft':lambda:draft(a.revision),'freeze':lambda:freeze(a.revision),'register':register}[a.command]()
