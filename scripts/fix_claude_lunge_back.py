"""Publish only the three rear-facing lunge frames (tools 53--55).

Uses a newly drawn back view, measured head/sole placement, and local arm/foot
fields. No general final pass, no NPK build/installation, no paid generation.
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

ROOT = Path(__file__).resolve().parents[1]
os.environ["PATCH_ID"] = "claude_gunner"
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit import art, hands
from kit.config import P
from kit.source import layer_world, armed

WORK = ROOT / "output/validation/claude_pose_correction_2026-11-09/lunge_back"
BEFORE, STAGE = WORK / "before", WORK / "staged"
CLIP = P.out / "clips/clip_052_059"
RAW = P.parts / "raw/lunge_back_repair_v6_patch_0.png"
SLOTS = (53, 54, 55)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(x):
    x = np.clip(x, 0, 1)
    return x*x*(3-2*x)


def prepare_cape_patch():
    """Adopt generated rear garments while locking old head/grips/boots."""
    old=np.asarray(Image.open(P.parts/'raw/lunge_back_repair_v5_0.png').convert('RGBA').resize((576,576),Image.Resampling.LANCZOS)).copy()
    new=np.asarray(Image.open(P.parts/'raw/lunge_back_repair_v6_0.png').convert('RGBA').resize((576,576),Image.Resampling.LANCZOS)).copy()
    y,x=np.mgrid[:576,:576]
    keep=(y<235)|(y>=520)|((y>=490)&((x<160)|(x>365)))|((x<228)&(y<333))|((x>342)&(y<241))
    a=old.astype(np.int16)
    orange=(a[...,0]>180)&(a[...,0]-a[...,1]>45)&(a[...,1]-a[...,2]>40)&(a[...,1]<195)&(a[...,3]>128)&(x>225)&(x<335)&(y>=235)&(y<395)
    labels,_=ndimage.label(orange,np.ones((3,3)))
    sizes=np.bincount(labels.ravel());sizes[0]=0
    # Largest connected orange patch is the long hair, excluding the old cape
    # flower and distant hip flower. Preserve its contour over the new cape.
    keep|=ndimage.binary_dilation(labels==sizes.argmax(),iterations=3)
    allowed=(y>=235)&(y<520)&(x>=110)&(x<435)
    keep|=~allowed
    result=np.where(keep[...,None],old,new).astype(np.uint8)
    np.testing.assert_array_equal(result[keep],old[keep])
    Image.fromarray(result).save(RAW)
    Image.fromarray((keep*255).astype(np.uint8)).save(WORK/'references/v6_clothing_protected_mask.png')
    board=Image.new('RGB',(1152,576),(54,61,75));d=ImageDraw.Draw(board)
    for i,im in enumerate((Image.fromarray(old),Image.fromarray(new),Image.fromarray(result))):
        crop=im.crop((180,225,405,485)).resize((346,400),Image.Resampling.NEAREST)
        board.paste(crop,(i*384+19,80),crop)
        d.text((i*384+15,35),['v5 before','v6 generated','v6 protected clothing edit'][i],fill='white')
    board.save(WORK/'cape_local_before_after.png')
    return dict(kept_pixels=int(keep.sum()),protected_max_rgba_difference=0,edit='Broad rear shoulder cape, no chest flower; asymmetric rear waist/skirt folds and partly hidden far hip ornament')


def original(slot):
    image=Image.new("RGBA",(500,500))
    for layer in P.order:
        image.alpha_composite(layer_world(layer,slot))
    return image


def small(image,size,palette):
    rgb,alpha=art.downscale(image,(size,size))
    return art.finish(art.sharpen(art.grade(rgb)),alpha,palette)


def shoe_targets(slot):
    mask=np.zeros((500,500),bool)
    for layer in P.order:
        if layer.startswith("shoes/"):
            mask |= np.asarray(layer_world(layer,slot))[...,3]>128
    result=[]
    for x0,x1 in ((0,240),(240,500)):
        yy,xx=np.nonzero(mask[:,x0:x1]);bottom=int(yy.max())+1
        band=yy>=bottom-3
        result.append([float(xx[band].mean()+x0),bottom])
    return result


def place(image,size,palette,slot):
    sprite=small(image,size,palette)
    a=np.asarray(sprite)[...,3]>128
    box=sprite.getbbox()
    yy,xx=np.nonzero(a[box[3]-3:,:size//2])
    left=round(shoe_targets(slot)[0][0]-xx.mean())
    top=shoe_targets(slot)[0][1]-box[3]
    world=Image.new("RGBA",(500,500));world.paste(sprite,(left,top))
    return world,(left,top)


def warp(image,dx,dy):
    dxdy,dxdx=np.gradient(dx);dydy,dydx=np.gradient(dy)
    forward=(1+dxdx)*(1+dydy)-dxdy*dydx
    if float(forward.min())<0.28:
        raise ValueError(f"Local correction would fold/compress the drawing: forward={forward.min():.3f}")
    y,x=np.mgrid[:image.height,:image.width].astype(np.float32)
    sx,sy=x.copy(),y.copy()
    # Newton inverse of the forward field; x-u(x) is only a first-order
    # approximation and can create artificial folds near a bent wrist.
    for _ in range(15):
        coords=[sy,sx]
        ex=sx+ndimage.map_coordinates(dx,coords,order=1,mode="nearest")-x
        ey=sy+ndimage.map_coordinates(dy,coords,order=1,mode="nearest")-y
        j00=1+ndimage.map_coordinates(dxdx,coords,order=1,mode="nearest")
        j01=ndimage.map_coordinates(dxdy,coords,order=1,mode="nearest")
        j10=ndimage.map_coordinates(dydx,coords,order=1,mode="nearest")
        j11=1+ndimage.map_coordinates(dydy,coords,order=1,mode="nearest")
        det=j00*j11-j01*j10
        sx-=np.clip((j11*ex-j01*ey)/det,-30,30)
        sy-=np.clip((j00*ey-j10*ex)/det,-30,30)
    sxdy,sxdx=np.gradient(sx);sydy,sydx=np.gradient(sy)
    inverse=sxdx*sydy-sxdy*sydx
    residual=np.hypot(sx+ndimage.map_coordinates(dx,[sy,sx],order=1,mode="nearest")-x,
                      sy+ndimage.map_coordinates(dy,[sy,sx],order=1,mode="nearest")-y)
    if float(inverse.min())<0.28 or float(residual.max())>0.1:
        raise ValueError(f"Inverse field failed: jacobian={inverse.min():.3f}, residual={residual.max():.3f}")
    source=np.asarray(image).astype(np.float32);pre=source.copy();pre[...,:3]*=source[...,3:]/255
    out=np.stack([ndimage.map_coordinates(pre[...,c],[sy,sx],order=1,mode="constant") for c in range(4)],2)
    out[...,:3]/=np.maximum(out[...,3:]/255,1e-3)
    active=np.abs(dx)+np.abs(dy)>0.001
    result=np.clip(np.where(active[...,None],out,source),0,255).astype(np.uint8)
    return Image.fromarray(result),dict(min_forward_jacobian=float(forward.min()),min_inverse_jacobian=float(inverse.min()),max_inverse_residual_px=float(residual.max()))


def palm(image,box):
    x0,y0,x1,y1=box
    a=np.asarray(image)[y0:y1,x0:x1].astype(np.int16)
    mask=(a[...,3]>128)&(a[...,0]>170)&(a[...,0]-a[...,1]>26)&(a[...,0]-a[...,1]<85)&(a[...,1]-a[...,2]>8)
    labels,count=ndimage.label(mask,np.ones((3,3)))
    sizes=np.bincount(labels.ravel());sizes[0]=0
    if not count or sizes.max()<30:raise ValueError("Missing drawn fist")
    yy,xx=np.nonzero(labels==sizes.argmax())
    return np.array([xx.mean()+x0,yy.mean()+y0])


def fit_feet(image,size,palette,slot):
    world,(left,top)=place(image,size,palette,slot)
    a=np.asarray(world)[...,3]>128
    yy,xx=np.nonzero(a[310:340,240:305]);bottom=int(yy.max()+311)
    band=yy>=yy.max()-2
    center=float(xx[band].mean()+240)
    goal=shoe_targets(slot)[1]
    delta=np.array([goal[0]-center,goal[1]-bottom])
    y,x=np.mgrid[:image.height,:image.width].astype(np.float32)
    w=smooth((x-250)/140)*smooth((y-370)/130)
    corrected,guard=warp(image,w*delta[0]*576/size,w*delta[1]*576/size)
    return corrected,dict(right_boot_world_shift=delta.tolist(),targets=shoe_targets(slot),**guard)


def fit_arms(image,size,palette,slot):
    _,origin=place(image,size,palette,slot)
    targets=hands.sprite_hands(slot)
    # Fists only: the lower forearm is a larger skin component than its fist.
    # Including it would misidentify the forearm center as the grip point.
    rois=((345,207,380,237),(195,298,225,323))
    y,x=np.mgrid[:image.height,:image.width].astype(np.float32)
    dx,dy=np.zeros_like(x),np.zeros_like(y);records=[]
    for n,(roi,target) in enumerate(zip(rois,targets)):
        center=palm(image,roi)
        world=np.array(origin)+center*size/576
        delta=np.array(target[:2])-world
        if np.linalg.norm(delta)>10:raise ValueError(f"Arm needs redraw instead of a large warp: {delta}")
        dist=np.hypot(x-center[0],y-center[1])
        w=smooth((120-dist)/98)
        if n==0:
            w*=smooth((x-255)/80)*(1-smooth((y-240)/80))
        else:
            w*=(1-smooth((x-225)/80))*smooth((y-225)/70)*(1-smooth((y-325)/50))
        dx+=w*delta[0]*576/size;dy+=w*delta[1]*576/size
        records.append(dict(target=list(target[:2]),found=world.tolist(),gap=float(np.linalg.norm(delta)),correction_world=delta.tolist(),palm_hd=center.tolist()))
    fitted,guard=warp(image,dx,dy)
    # The rear head/crown core and whole lower gown/boots are never part of an
    # arm fit. A far raised fist may correctly overlap the outside head edge.
    protected=(y<180)|((x<325)&(y<235))|(y>=355)
    a=np.asarray(fitted).copy();a[protected]=np.asarray(image)[protected]
    fitted=Image.fromarray(a)
    np.testing.assert_array_equal(np.asarray(fitted)[protected],np.asarray(image)[protected])
    return fitted,records,guard,protected


def build(apply=False):
    if apply:
        raise SystemExit(
            "This back pose was rejected and superseded. "
            "Run scripts/fix_claude_user_back.py --apply instead."
        )
    cape_edit=prepare_cape_patch()
    palette=Image.open(ROOT/"output/validation/claude_idle_feet_fix/palette_original.png").copy()
    source=Image.open(RAW).convert("RGBA").resize((576,576),Image.Resampling.LANCZOS)
    before=json.loads((BEFORE/"selection.json").read_text("utf-8"))
    current=json.loads((CLIP/"selection.json").read_text("utf-8"))
    preserved={r["slot"]:copy.deepcopy(r) for r in current["frames"] if r["slot"] not in SLOTS}
    size=165
    for sub in ("hd","hdfit","native_frames"):(STAGE/sub).mkdir(parents=True,exist_ok=True)
    metrics=[];frames=[];hd_frames=[]
    for slot in SLOTS:
        base,feet=fit_feet(source.copy(),size,palette,slot)
        fitted,arm_records,guard,protected=fit_arms(base,size,palette,slot)
        world,(left,top)=place(fitted,size,palette,slot)
        pre=np.asarray(world).copy()
        world=hands.graft(world,slot,palette)
        row=next(r for r in current["frames"] if r["slot"]==slot)
        scale=size/current["window"][2];origin=art.placement(current["window"],scale)
        row.update(video_frame=f"lunge_back_repair:{slot}",scale=scale,offset=[left-origin[0],top-origin[1]],track=[0,0],
                   hands=[{**record,"gap":round(record["gap"],1),"state":"背面局部校准"} for record in arm_records])
        row["offset_before_ground"]=row["offset"].copy()
        base.save(STAGE/f"hd/{slot:04d}.png");fitted.save(STAGE/f"hdfit/{slot:04d}.png");world.save(STAGE/f"native_frames/{slot:04d}.png")
        source_box=original(slot).getbbox();new_box=world.getbbox()
        if abs((new_box[3]-new_box[1])-(source_box[3]-source_box[1]))>1:raise ValueError("Head/sole height differs")
        contacts=[]
        for hand in hands.sprite_hands(slot):
            x,y=map(lambda z:int(round(z)),hand[:2]);contacts.append(dict(target=list(hand[:2]),solid_5x5=int((np.asarray(world)[y-2:y+3,x-2:x+3,3]>128).sum()),coverage_before_graft=float((pre[...,3][hand[2]]>128).mean())))
        metrics.append(dict(slot=slot,user_frame=slot+1,source_bbox=source_box,new_bbox=new_box,source_height=source_box[3]-source_box[1],new_height=new_box[3]-new_box[1],feet=feet,hands=arm_records,contacts=contacts,protected_arm_pixels=int(protected.sum()),protected_max_rgba_difference=0,**guard,native_sha256=sha(STAGE/f"native_frames/{slot:04d}.png")))
        frames.append(world);hd_frames.append(fitted)
    for row in current["frames"]:
        if row["slot"] not in SLOTS:assert row==preserved[row["slot"]]
    (STAGE/"selection.json").write_text(json.dumps(current,ensure_ascii=False,indent=1)+"\n","utf-8")
    board=Image.new("RGB",(3*440,2*530),(60,67,84));d=ImageDraw.Draw(board)
    for i,slot in enumerate(SLOTS):
        for r,(label,image) in enumerate((("Original",armed(original(slot),slot)),("Back repair",armed(frames[i],slot)))):
            crop=image.crop((195,210,295,335)).resize((400,500),Image.Resampling.NEAREST);board.paste(crop,(i*440+20,r*530+25),crop);d.text((i*440+8,r*530+7),f"User{slot+1} {label}",fill="white")
    board.save(WORK/"repaired_contact.png")
    if apply:
        for slot in SLOTS:
            for sub,folder in (("hd",CLIP/"hd"),("hdfit",CLIP/"hdfit"),("native_frames",P.out/"native_frames")):
                target=folder/f"{slot:04d}.png";temporary=target.with_suffix(".back-repair.tmp");shutil.copyfile(STAGE/sub/target.name,temporary);temporary.replace(target)
        (CLIP/"selection.json").write_bytes((STAGE/"selection.json").read_bytes())
    result=dict(applied=apply,source_raw=RAW.relative_to(ROOT).as_posix(),generation="built-in image_gen",orientation="Rear 3/4: broad back shoulder cape, back hair/corset, rotated asymmetric rear skirt, no front chest decorations",cape_edit=cape_edit,slots=list(SLOTS),frames=metrics,installed=False)
    (WORK/"repair_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n","utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--apply",action="store_true");build(parser.parse_args().apply)
