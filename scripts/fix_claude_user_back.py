"""Stage/apply only tools53-55 from a new authoritative rear-view drawing.

No old artwork is composited into the drawing. Application copies the exact
reviewed stage and checks that all 140 other native frames remain byte-identical.
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
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
os.environ['PATCH_ID']='claude_gunner'
sys.path.insert(0,str(ROOT/'.claude/skills/dnf-character-patch/scripts'))
from kit import art,hands
from kit.config import P
from kit.source import layer_world,armed

WORK=ROOT/'output/validation/claude_user_back_reference_2026-11-09'
STAGE=WORK/'staged'
CLIP=P.out/'clips/clip_052_059'
CONFIG=ROOT/'design/claude_gunner/user_back_repair.json'
SLOTS=(53,54,55)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text('utf-8'))
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
def smooth(t):t=np.clip(t,0,1);return t*t*(3-2*t)

def scope_check():
    baseline=load(WORK/'scope_before.json');unchanged=[]
    assert {p.name for p in (P.out/'native_frames').glob('*.png')}==set(baseline['all_native_sha256']),'Native frame inventory changed'
    for name,digest in baseline['all_native_sha256'].items():
        if int(Path(name).stem) in SLOTS:continue
        assert sha(P.out/'native_frames'/name)==digest,f'Unowned native changed: {name}'
        unchanged.append(name)
    for name,digest in baseline['same_clip_hd_hdfit_sha256'].items():
        if int(Path(name).stem) not in SLOTS:assert sha(CLIP/name)==digest,f'Unowned clip image changed: {name}'
    baseline_rows={r['slot']:r for r in baseline['selection']['frames']}
    current_rows=load(CLIP/'selection.json')['frames']
    assert len(current_rows)==len(baseline_rows) and {r['slot'] for r in current_rows}==set(baseline_rows),'Selection slot inventory changed'
    for row in current_rows:
        if row['slot'] not in SLOTS:assert row==baseline_rows[row['slot']],f"Unowned selection changed: {row['slot']}"
    assert len(unchanged)==140
    return unchanged

def normalize(path):
    raw=Image.open(path).convert('RGBA')
    contained=ImageOps.contain(raw,(576,576),Image.Resampling.LANCZOS)
    image=Image.new('RGBA',(576,576));image.paste(contained,((576-contained.width)//2,(576-contained.height)//2))
    a=np.asarray(image).copy();a[a[...,3]<8]=0
    return Image.fromarray(a),dict(input_size=list(raw.size),contained_size=list(contained.size),canvas=[576,576])

def native(image,size,palette,origin):
    rgb,alpha=art.downscale(image,(size,size))
    small=art.finish(art.sharpen(art.grade(rgb)),alpha,palette)
    world=Image.new('RGBA',(500,500));world.paste(small,tuple(origin))
    return world

def source(slot):
    image=Image.new('RGBA',(500,500))
    for layer in P.order:image.alpha_composite(layer_world(layer,slot))
    return image

def source_soles(slot):
    mask=np.zeros((500,500),bool)
    for layer in P.order:
        if layer.startswith('shoes/'):mask|=np.asarray(layer_world(layer,slot))[...,3]>128
    result=[]
    for x0,x1 in ((0,240),(240,500)):
        yy,xx=np.nonzero(mask[:,x0:x1]);bottom=int(yy.max())+1;band=yy>=bottom-3
        result.append([float(xx[band].mean()+x0),bottom])
    return result

def graft_lower_hand_only(world,slot,palette):
    """Upper source skin mask includes the old face profile; never copy it."""
    rgba=np.asarray(world).copy();source_pixels=np.asarray(layer_world(P.body,slot))
    mask=hands.sprite_hands(slot)[1][2]
    pixels=source_pixels[mask,:3]
    quantized=Image.fromarray(pixels.reshape(-1,1,3),'RGB').quantize(palette=palette,dither=Image.Dither.NONE).convert('RGB')
    rgba[mask,:3]=np.asarray(quantized).reshape(-1,3);rgba[mask,3]=255
    # The calibrated generated upper fist and new head are retained exactly.
    high=hands.sprite_hands(slot)[0][2]
    np.testing.assert_array_equal(rgba[high],np.asarray(world)[high])
    return Image.fromarray(rgba)

def sole(world,guess):
    a=np.asarray(world)[...,3]>128;x,y=np.rint(guess).astype(int)
    x0,x1=max(0,x-9),min(500,x+10);y0,y1=max(0,y-10),min(500,y+4)
    yy,xx=np.nonzero(a[y0:y1,x0:x1]);assert len(xx),'Missing boot near supplied sole landmark'
    bottom=int(yy.max()+y0)+1;band=yy>=yy.max()-2
    return np.array([float(xx[band].mean()+x0),bottom])

def warp(image,dx,dy,limit):
    dxdy,dxdx=np.gradient(dx);dydy,dydx=np.gradient(dy)
    jac=(1+dxdx)*(1+dydy)-dxdy*dydx
    if jac.min()<limit:raise ValueError(f'Local field compresses/folds artwork: {jac.min():.3f}')
    y,x=np.mgrid[:576,:576].astype(np.float32);sx=x.copy();sy=y.copy()
    for _ in range(15):
        c=[sy,sx];ex=sx+ndimage.map_coordinates(dx,c,order=1,mode='nearest')-x;ey=sy+ndimage.map_coordinates(dy,c,order=1,mode='nearest')-y
        j00=1+ndimage.map_coordinates(dxdx,c,order=1,mode='nearest');j01=ndimage.map_coordinates(dxdy,c,order=1,mode='nearest')
        j10=ndimage.map_coordinates(dydx,c,order=1,mode='nearest');j11=1+ndimage.map_coordinates(dydy,c,order=1,mode='nearest');det=j00*j11-j01*j10
        sx-=np.clip((j11*ex-j01*ey)/det,-20,20);sy-=np.clip((j00*ey-j10*ex)/det,-20,20)
    sxdy,sxdx=np.gradient(sx);sydy,sydx=np.gradient(sy);inverse=sxdx*sydy-sxdy*sydx
    residual=np.hypot(sx+ndimage.map_coordinates(dx,[sy,sx],order=1,mode='nearest')-x,sy+ndimage.map_coordinates(dy,[sy,sx],order=1,mode='nearest')-y)
    if inverse.min()<limit or residual.max()>.1:raise ValueError('Invalid inverse of local field')
    src=np.asarray(image).astype(np.float32);pre=src.copy();pre[...,:3]*=src[...,3:]/255
    out=np.stack([ndimage.map_coordinates(pre[...,c],[sy,sx],order=1,mode='constant') for c in range(4)],2)
    out[...,:3]/=np.maximum(out[...,3:]/255,1e-3)
    active=np.abs(dx)+np.abs(dy)>.001
    result=np.clip(np.where(active[...,None],out,src),0,255).astype(np.uint8)
    return Image.fromarray(result),dict(min_forward_jacobian=float(jac.min()),min_inverse_jacobian=float(inverse.min()),max_inverse_residual=float(residual.max()))

def local_move(image,moves,protected,limit):
    y,x=np.mgrid[:576,:576].astype(np.float32);dx=np.zeros_like(x);dy=np.zeros_like(y)
    feather=ndimage.distance_transform_edt(~protected)
    for center,delta,radius in moves:
        cx,cy=np.rint(center).astype(int)
        center_weight=float(smooth(feather[cy,cx]/30))
        if np.linalg.norm(delta)>.01 and center_weight<.98:
            raise ValueError(f'Protected boundary too close to endpoint: weight={center_weight:.3f}; refine its local protection region')
        w=smooth((radius-np.hypot(x-center[0],y-center[1]))/(radius-12))*smooth(feather/30)
        dx+=w*delta[0];dy+=w*delta[1]
    fitted,stats=warp(image,dx,dy,limit)
    a=np.asarray(fitted).copy();a[protected]=np.asarray(image)[protected]
    return Image.fromarray(a),{**stats,'protected_max_rgba_difference':0}

def stage():
    unchanged=scope_check();config=load(CONFIG);lm=config['landmarks'];limits=config['limits']
    assert config.get('raw') and lm['head_top_y'] is not None and len(lm['soles'] or [])==2 and len(lm['grips'] or [])==2,'Supply new raw and normalized576 head/sole/grip landmarks first'
    raw_path=ROOT/config['raw'];image,normalization=normalize(raw_path)
    palette=Image.open(ROOT/'output/validation/claude_idle_feet_fix/palette_original.png').copy()
    size0=round(576*109/(lm['soles'][0][1]-lm['head_top_y']))
    # Match the visible native head-to-left-sole height, independently of raw
    # margins and arbitrary generator image resolution.
    options=[]
    for size in range(size0-3,size0+4):
        test=native(image,size,palette,(0,0));box=test.getbbox()
        options.append((abs((box[3]-box[1])-109),abs(size-size0),size,box))
    error,_,size,box=min(options)
    assert error<=1,'New drawing head/left-sole envelope cannot match original scale'
    origin=[round(source_soles(53)[0][0]-lm['soles'][0][0]*size/576),330-box[3]]
    first=native(image,size,palette,origin);actual_left=sole(first,np.array(origin)+np.array(lm['soles'][0])*size/576)
    origin[0]+=round(source_soles(53)[0][0]-actual_left[0])
    report=load(CLIP/'selection.json');metrics=[];worlds=[]
    y,x=np.mgrid[:576,:576]
    for sub in ['hd','hdfit','native_frames','before_graft']:(STAGE/sub).mkdir(parents=True,exist_ok=True)
    image.save(WORK/'normalized_new_raw.png')
    for slot in SLOTS:
        goals=source_soles(slot);base=native(image,size,palette,origin);moves=[];feet=[]
        for point,goal in zip(lm['soles'],goals):
            guess=np.array(origin)+np.array(point)*size/576;actual=sole(base,guess);delta=np.array(goal)-actual
            if np.linalg.norm(delta)>limits['max_boot_move_native']:raise ValueError(f'New drawing boot too far; redraw instead: {delta}')
            moves.append((point,delta*576/size,80));feet.append(dict(found=actual.tolist(),target=goal,delta=delta.tolist()))
        # Foot corrections cannot reach the waist, skirt bow or upper skirt.
        boot_protect=y<min(p[1] for p in lm['soles'])-90
        hd,boot_guard=local_move(image,moves,boot_protect,limits['min_jacobian'])
        arm_protect=np.zeros((576,576),bool)
        if lm.get('arm_protect_below_y') is not None:arm_protect|=y>=lm['arm_protect_below_y']
        for x0,y0,x1,y1 in lm.get('arm_protected_boxes',[]):arm_protect[y0:y1,x0:x1]=True
        arm_moves=[];hand_metrics=[]
        for point,target in zip(lm['grips'],hands.sprite_hands(slot)):
            found=np.array(origin)+np.array(point)*size/576;delta=np.array(target[:2])-found
            if np.linalg.norm(delta)>limits['max_hand_move_native']:raise ValueError(f'New drawing grip too far; redraw instead: {delta}')
            arm_moves.append((point,delta*576/size,90));hand_metrics.append(dict(found=found.tolist(),target=list(target[:2]),gap_before=float(np.linalg.norm(delta)),delta=delta.tolist()))
        fitted,arm_guard=local_move(hd,arm_moves,arm_protect,limits['min_jacobian'])
        world=native(fitted,size,palette,origin);pre=np.asarray(world).copy();world.save(STAGE/'before_graft'/f'{slot:04d}.png');world=graft_lower_hand_only(world,slot,palette)
        contacts=[]
        for number,target in enumerate(hands.sprite_hands(slot)):
            tx,ty=np.rint(target[:2]).astype(int)
            contacts.append(dict(target=list(target[:2]),graft_applied=number==1,graft_policy='generated upper fist retained: source high mask contains old face profile' if number==0 else 'source lower hand only',solid_5x5=int((np.asarray(world)[ty-2:ty+3,tx-2:tx+3,3]>128).sum()),solid_5x5_before_graft=int((pre[ty-2:ty+3,tx-2:tx+3,3]>128).sum()),solid_3x3_before_graft=int((pre[ty-1:ty+2,tx-1:tx+2,3]>128).sum()),coverage_before_graft=float((pre[...,3][target[2]]>128).mean())))
        for sub,im in [('hd',hd),('hdfit',fitted),('native_frames',world)]:im.save(STAGE/sub/f'{slot:04d}.png')
        row=next(r for r in report['frames'] if r['slot']==slot);scale=size/report['window'][2];anchor=art.placement(report['window'],scale)
        row.update(video_frame=f'user_back_reference:{slot}',scale=scale,offset=[origin[0]-anchor[0],origin[1]-anchor[1]],track=[0,0],hands=[dict(target=m['target'],found=m['found'],gap=round(m['gap_before'],1),state='new rear-art local fit') for m in hand_metrics]);row['offset_before_ground']=row['offset'].copy()
        metrics.append(dict(slot=slot,user_frame=slot+1,bbox=list(world.getbbox()),source_bbox=list(source(slot).getbbox()),feet=feet,hands=hand_metrics,contacts=contacts,boot_guard=boot_guard,arm_guard=arm_guard,native_sha256=sha(STAGE/'native_frames'/f'{slot:04d}.png'),stage_hashes={sub:sha(STAGE/sub/f'{slot:04d}.png') for sub in ['hd','hdfit','native_frames']}));worlds.append(world)
    write(STAGE/'selection.json',report)
    board=Image.new('RGB',(1320,1060),(55,63,80));d=ImageDraw.Draw(board)
    for i,slot in enumerate(SLOTS):
        for r,(label,im) in enumerate([('Original pose',armed(source(slot),slot)),('New rear design',armed(worlds[i],slot))]):
            crop=im.crop((195,210,295,335)).resize((400,500),Image.Resampling.NEAREST);board.paste(crop,(i*440+20,r*530+25),crop);d.text((i*440+10,r*530+8),f'User{slot+1} {label}',fill='white')
    board.save(WORK/'staged_armed_contact.png')
    data=dict(applied=False,raw=config['raw'],raw_sha256=sha(raw_path),config_sha256=sha(CONFIG),selection_sha256=sha(STAGE/'selection.json'),normalization=normalization,size=size,origin=origin,frames=metrics,unchanged_other_native_count=len(unchanged),packaged=False,installed=False)
    write(WORK/'stage_report.json',data);validate(False);print(json.dumps(data,ensure_ascii=False,indent=2))

def validate(applied):
    unchanged=scope_check();report=load(WORK/'stage_report.json');checks=[]
    assert sha(STAGE/'selection.json')==report['selection_sha256'],'Reviewed staged selection changed'
    for frame in report['frames']:
        slot=frame['slot'];path=P.out/'native_frames'/f'{slot:04d}.png' if applied else STAGE/'native_frames'/f'{slot:04d}.png'
        for sub,digest in frame['stage_hashes'].items():assert sha(STAGE/sub/f'{slot:04d}.png')==digest,'Reviewed stage image changed'
        im=Image.open(path).convert('RGBA');a=np.asarray(im)[...,3];box=im.getbbox()
        assert im.size==(500,500) and set(np.unique(a)).issubset({0,255})
        assert abs(box[1]-221)<=1 and box[3]==330 and abs(box[3]-box[1]-109)<=1
        labels,_=ndimage.label(a>128,np.ones((3,3)));areas=np.bincount(labels.ravel())[1:];assert int((areas>=4).sum())==1
        soles=[]
        for goal in source_soles(slot):
            found=sole(im,goal);assert abs(found[1]-goal[1])<=1 and abs(found[0]-goal[0])<=1.5
            soles.append(found.tolist())
        for c in frame['contacts']:
            tx,ty=np.rint(c['target']).astype(int);assert (a[ty-2:ty+3,tx-2:tx+3]>128).sum()>=23
            # The source near-weapon skin mask can include part of the old
            # head/ear. Test actual grip occupancy on the new drawing instead
            # of requiring it to reproduce the original head's skin contour.
            assert c['solid_5x5_before_graft']>=23 and c['solid_3x3_before_graft']==9,'Generated fist does not occupy the grip before source-hand graft'
        if applied:
            assert sha(path)==frame['native_sha256']
            assert sha(path)!=load(WORK/'scope_before.json')['all_native_sha256'][path.name]
        checks.append(dict(slot=slot,bbox=list(box),soles=soles,one_major_component=True,native_sha256=sha(path)))
    result=dict(passed=True,applied=applied,frames=checks,unchanged_other_native_count=len(unchanged),unchanged_other_native_sha256={n:sha(P.out/'native_frames'/n) for n in unchanged},packaged=False,installed=False)
    write(WORK/('validation_applied.json' if applied else 'validation_staged.json'),result)
    return result

def apply():
    scope_check();report=load(WORK/'stage_report.json');assert report['config_sha256']==sha(CONFIG) and report['raw_sha256']==sha(ROOT/report['raw']),'Stage inputs changed; restage before review'
    validate(False);current=load(CLIP/'selection.json');rows={r['slot']:r for r in load(STAGE/'selection.json')['frames']}
    for slot in SLOTS:
        for sub,folder in [('hd',CLIP/'hd'),('hdfit',CLIP/'hdfit'),('native_frames',P.out/'native_frames')]:
            target=folder/f'{slot:04d}.png';tmp=target.with_suffix('.user-back.tmp');shutil.copyfile(STAGE/sub/target.name,tmp);tmp.replace(target)
    current['frames']=[copy.deepcopy(rows[r['slot']]) if r['slot'] in SLOTS else r for r in current['frames']]
    (CLIP/'selection.json').write_text(json.dumps(current,ensure_ascii=False,indent=1)+'\n','utf-8')
    result=validate(True);report['applied']=True;write(WORK/'stage_report.json',report);print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--validate',action='store_true');a=p.parse_args()
    if a.apply:apply()
    elif a.validate:print(json.dumps(validate(False),ensure_ascii=False,indent=2))
    else:stage()
