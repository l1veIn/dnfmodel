"""Publish only four Claude chest-crossing poses from reviewed new artwork.

The two complete shoulder/elbow/wrist chains must be approved visually first.
This script only places the art and makes bounded local hand calibrations; it
will refuse a bad pose that would require a large automatic stretch.
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
from kit.source import armed, layer_world

WORK = ROOT / "output/validation/claude_pose_correction_2026-11-09/hold_cross"
BEFORE, STAGE = WORK / "before", WORK / "staged"
CLIP = P.out / "clips/clip_064_067"
CONFIG = ROOT / "design/claude_gunner/hold_cross_repair.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(x):
    x = np.clip(x, 0, 1)
    return x*x*(3-2*x)


def original(slot):
    image = Image.new("RGBA", (500, 500))
    for layer in P.order:
        image.alpha_composite(layer_world(layer, slot))
    return image


def palm(image, box):
    x0,y0,x1,y1 = box
    roi = np.asarray(image)[y0:y1,x0:x1].astype(np.int16)
    skin = ((roi[...,0]>170)&(roi[...,0]-roi[...,1]>26)&(roi[...,0]-roi[...,1]<85)
            &(roi[...,1]-roi[...,2]>8)&(roi[...,3]>128))
    yy,xx = np.nonzero(skin)
    if len(xx)<30:
        raise ValueError(f"Reviewed closed fist is absent from ROI {box}")
    return np.array([xx.mean()+x0,yy.mean()+y0])


def read_art(path, canvas):
    image = Image.open(path).convert("RGBA")
    if image.size != tuple(canvas):
        if abs(image.width/image.height-canvas[0]/canvas[1])>.015:
            raise ValueError("Art canvas aspect changed; review coordinates before fitting")
        image = image.resize(canvas, Image.Resampling.LANCZOS)
    square = Image.new("RGBA", (max(canvas),max(canvas)))
    square.paste(image,(0,0))
    return square


def raster(image, size, palette):
    color,alpha = art.downscale(image,(size,size))
    return art.finish(art.sharpen(art.grade(color)),alpha,palette)


def choose_size(image,palette,height):
    box = image.getchannel("A").point(lambda a:255 if a>128 else 0).getbbox()
    guess = round(image.height*height/(box[3]-box[1]))
    candidates=[]
    for size in range(guess-4,guess+5):
        b=raster(image,size,palette).getbbox()
        candidates.append((abs(b[3]-b[1]-height),abs(size-guess),size))
    error,_,size=min(candidates)
    if error>1:
        raise ValueError("Art cannot match the original head/sole height")
    return size


def origin(image,size,palette,centers,targets):
    box=raster(image,size,palette).getbbox()
    left=round(np.mean([target[0]-center[0]*size/image.width for center,target in zip(centers,targets)]))
    return left,333-box[3]


def place(image,size,palette,xy):
    world=Image.new("RGBA",(500,500))
    world.paste(raster(image,size,palette),xy)
    return world


def calibrate(image,size,xy,centers,targets,cfg):
    src=np.asarray(image).astype(np.float32)
    yy,xx=np.mgrid[:image.height,:image.width].astype(np.float32)
    factor=size/image.width
    x0,y0,x1,y1=cfg["face_protection"]
    protected=((xx>=x0)&(xx<x1)&(yy>=y0)&(yy<y1))|(yy>=cfg["fixed_lower_body_from_y"])
    distance=ndimage.distance_transform_edt(~protected)
    dx=np.zeros_like(xx);dy=np.zeros_like(yy);records=[]
    for n,(center,target) in enumerate(zip(centers,targets)):
        found=np.asarray(xy)+center*factor
        delta=np.asarray(target)-found
        gap=float(np.linalg.norm(delta))
        if gap>cfg["max_hand_calibration_px"]:
            raise ValueError(f"Hand {n} needs {gap:.2f}px calibration: revise the artwork, not the body")
        radius=(18 if n==0 else 14)/factor;inner=4/factor
        weight=smooth((radius-np.hypot(xx-center[0],yy-center[1]))/(radius-inner))
        weight*=smooth(distance/(5/factor));weight[protected]=0
        dx+=weight*delta[0]/factor;dy+=weight*delta[1]/factor
        records.append(dict(target=np.asarray(target).tolist(),found=found.tolist(),gap=gap,
                            source_fist_center=center.tolist(),correction_world=delta.tolist(),state="交叉臂局部校准"))
    dxy,dxx=np.gradient(dx);dyy,dyx=np.gradient(dy)
    jacobian=(1-dxx)*(1-dyy)-dxy*dyx
    if float(jacobian.min())<=.4:
        raise ValueError(f"Hand calibration would compress/fold art: min J={jacobian.min()}")
    sx,sy=xx.copy(),yy.copy()
    for _ in range(5):
        sx=xx-ndimage.map_coordinates(dx,[sy,sx],order=1,mode="nearest")
        sy=yy-ndimage.map_coordinates(dy,[sy,sx],order=1,mode="nearest")
    premult=src.copy();premult[...,:3]*=src[...,3:]/255
    out=np.stack([ndimage.map_coordinates(premult[...,c],[sy,sx],order=1,mode="constant") for c in range(4)],2)
    out[...,:3]/=np.maximum(out[...,3:]/255,1e-3)
    active=np.abs(dx)+np.abs(dy)>.001
    result=np.clip(np.where(active[...,None],out,src),0,255).astype(np.uint8)
    result[protected]=src[protected].astype(np.uint8)
    return Image.fromarray(result),records,float(jacobian.min()),protected


def build(apply=False,settled_only=False):
    cfg=json.loads(CONFIG.read_text("utf-8"));palette=Image.open(ROOT/cfg["palette"]).copy()
    if not (BEFORE/"native_sha256.json").is_file():
        raise ValueError("The pre-repair native snapshot must exist before staging or publication")
    report=json.loads((BEFORE/"selection.json").read_text("utf-8"))
    report["sheet"]="hold_crossed_arms";report["repair"]=CONFIG.relative_to(ROOT).as_posix()
    key=read_art(ROOT/cfg["key_art"],cfg["canvas"])
    centers=[palm(key,box) for box in cfg["palm_rois"]["settled"]]
    target65=[np.asarray(t[:2]) for t in hands.sprite_hands(65)]
    key_size=choose_size(key,palette,123);key_origin=origin(key,key_size,palette,centers,target65)
    slots=list(range(65,68)) if settled_only else list(range(64,68))
    if apply and settled_only:
        raise ValueError("Publish a complete four-frame action, never a mixed old/new pose")
    for sub in ("hd","hdfit","native_frames"):(STAGE/sub).mkdir(parents=True,exist_ok=True)
    results=[];images=[]
    for slot in slots:
        if slot==64:
            base=read_art(ROOT/cfg["smear_art"],cfg["canvas"])
            own_centers=[palm(base,box) for box in cfg["palm_rois"]["smear"]]
            size=choose_size(base,palette,122)
            targets=[np.asarray(t[:2]) for t in hands.sprite_hands(slot)]
            xy=origin(base,size,palette,own_centers,targets)
        else:
            base=key.copy();own_centers=centers;size=key_size;xy=key_origin
            targets=[np.asarray(t[:2]) for t in hands.sprite_hands(slot)]
        fitted,records,jmin,protected=calibrate(base,size,xy,own_centers,targets,cfg)
        ungrafted=place(fitted,size,palette,xy);frame=hands.graft(ungrafted,slot,palette)
        base.save(STAGE/f"hd/{slot:04d}.png");fitted.save(STAGE/f"hdfit/{slot:04d}.png");frame.save(STAGE/f"native_frames/{slot:04d}.png")
        row=next(row for row in report["frames"] if row["slot"]==slot)
        scale=size/report["window"][2];base_left,base_top=art.placement(report["window"],scale)
        row.update(video_frame=f"chest_cross:{slot-64}",scale=scale,offset=[xy[0]-base_left,xy[1]-base_top],track=[0,0],
                   hands=[{**record,"gap":round(record["gap"],1)} for record in records])
        row["offset_before_ground"]=row["offset"].copy()
        box,source_box=frame.getbbox(),original(slot).getbbox()
        contacts=[]
        for target in targets:
            x,y=np.round(target).astype(int);roi=np.asarray(frame)[y-2:y+3,x-2:x+3,3]
            contacts.append(int((roi>128).sum()))
        results.append(dict(slot=slot,source_bbox=source_box,new_bbox=box,source_height=source_box[3]-source_box[1],
                            new_height=box[3]-box[1],size=size,origin=xy,hands=records,min_inverse_jacobian=jmin,
                            protected_source_pixels=int(protected.sum()),grip_solid_pixels_5x5=contacts,
                            native_sha256=sha(STAGE/f"native_frames/{slot:04d}.png")))
        images.append(frame)
    (STAGE/"selection.json").write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',"utf-8")
    board=Image.new("RGB",(len(slots)*480,2*620),(65,72,87));draw=ImageDraw.Draw(board)
    for n,(slot,frame) in enumerate(zip(slots,images)):
        for row,(label,img) in enumerate((("original",armed(original(slot),slot)),("crossed",armed(frame,slot)))):
            draw.text((n*480+8,row*620+8),f"Game {slot+1} {label}",fill="white")
            part=img.crop((185,195,305,340)).resize((480,580),Image.Resampling.NEAREST);board.paste(part,(n*480,row*620+28),part)
    board.save(WORK/("settled_contact.png" if settled_only else "crossed_contact.png"))
    if apply:
        for slot in slots:
            for sub in ("hd","hdfit","native_frames"):
                dest=(P.out/sub if sub=="native_frames" else CLIP/sub)/f"{slot:04d}.png"
                temp=dest.with_suffix(".crossed.tmp");shutil.copyfile(STAGE/sub/f"{slot:04d}.png",temp);temp.replace(dest)
        temp=(CLIP/"selection.json").with_suffix(".crossed.tmp");shutil.copyfile(STAGE/"selection.json",temp);temp.replace(CLIP/"selection.json")
    artifacts={"key_art":cfg["key_art"],"palette":cfg["palette"],"config":CONFIG.relative_to(ROOT).as_posix()}
    if not settled_only:artifacts["smear_art"]=cfg["smear_art"]
    summary=dict(applied=apply,settled_only=settled_only,key_art=cfg["key_art"],smear_art=cfg["smear_art"],frames=results,
                 source_sha256={name:sha(ROOT/path) for name,path in artifacts.items()},installed=False,ingame_verified=False)
    (WORK/("settled_report.json" if settled_only else "repair_report.json")).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',"utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--apply",action="store_true");parser.add_argument("--settled-only",action="store_true")
    args=parser.parse_args();build(args.apply,args.settled_only)
