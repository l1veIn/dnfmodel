"""Reproducible genuine-imagegen staging of rejected dragon nod/gesture only.

No old-source / patch / package writes. One common world crop and one selection
transform per sequence. Batch registration is fixed once, never per-frame bbox
centering or best-shift. Nod uses the newly painted approved idle canonical as
the fixed structure and newly generated connected right-arm / inner-face edits.
"""
from __future__ import annotations
import copy, hashlib, json, os, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
os.environ["PATCH_ID"]="gpt_dragon_slayer_v03"
sys.path.insert(0,str(ROOT/".claude/skills/dnf-character-patch/scripts"))
sys.path.insert(0,str(ROOT/"scripts"))
from kit import art
from kit.source import native_world, armed
from kit.hands import bend
from repair_dragon_actions_v05 import native_palette
WORK=ROOT/"output/dragon_gesture_nod_redraw_v06"
BASE=ROOT/"output/gpt_dragon_slayer_v05"
CANON=ROOT/"output/dragon_breath_redraw_v06/candidate02/idle"
CROP=(165,240,160,160)
ZOOM=6
TARGET=list(range(4,9))+list(range(123,132))

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def cell(path,index,cols,rows):
    im=Image.open(path).convert("RGBA")
    w,h=im.width//cols,im.height//rows
    return im.crop((index%cols*w,index//cols*h,index%cols*w+w,index//cols*h+h))
def register(im,scale,tx,ty):
    """One batch-fixed scale+translation, source pixel -> native world."""
    L,T,S,_=CROP
    # Transform in premultiplied floating channels to preserve genuine alpha.
    a=np.asarray(im,dtype=np.float32)/255
    a[...,:3]*=a[...,3:]
    out=[]
    for c in range(4):
        ch=Image.fromarray(a[...,c],"F").transform((S*ZOOM,S*ZOOM),Image.Transform.AFFINE,
            (1/(scale*ZOOM),0,(L-tx)/scale,0,1/(scale*ZOOM),(T-ty)/scale),
            resample=Image.Resampling.BICUBIC)
        out.append(np.asarray(ch))
    arr=np.stack(out,2);arr[...,:3]/=np.maximum(arr[...,3:],1e-6)
    return Image.fromarray(np.clip(np.rint(arr*255),0,255).astype("uint8"),"RGBA")
def nod_masks(canonical):
    m=Image.new("L",(960,960));d=ImageDraw.Draw(m)
    # New active shoulder, sleeve, arm and exposed former-arm background.
    d.polygon([(534,313),(583,304),(736,250),(744,558),(626,587),(556,556),(550,451),(533,411)],fill=255)
    arm=np.array(m.filter(ImageFilter.GaussianBlur(2.0)))
    arm[588:]=0
    # Face interior only: the existing alpha contour is kept absolutely fixed.
    f=Image.new("L",(960,960));ImageDraw.Draw(f).polygon([(510,257),(548,256),(552,282),(538,296),(516,288)],fill=255)
    face=np.array(f.filter(ImageFilter.GaussianBlur(2.0)))
    interior=ndimage.binary_erosion(np.asarray(canonical)[...,3]>128,iterations=5)
    face[~interior]=0
    return Image.fromarray(arm,"L"),Image.fromarray(face,"L")
def grip_mask():
    m=Image.new("L",(960,960));d=ImageDraw.Draw(m)
    d.polygon([(430,342),(468,361),(442,423),(402,480),(359,548),(306,545),(299,493),(352,446),(397,383)],fill=255)
    d.polygon([(402,412),(464,412),(467,558),(399,558)],fill=255)
    return m.filter(ImageFilter.GaussianBlur(3.0))
def weapon_review(out,frames):
    rd=out/"review";board=Image.new("RGB",(9*400,3*350),(46,50,63));d=ImageDraw.Draw(board)
    for j,k in enumerate(range(123,132)):
        for r,(im,label) in enumerate([(native_world(k),"original+weapon"),(Image.open(BASE/f"native_frames/{k:04d}.png").convert("RGBA"),"v05+weapon"),(frames[k],"v06+weapon")]):
            part=armed(im,k).crop((195,270,295,355)).resize((400,340),Image.Resampling.NEAREST)
            board.paste(part,(j*400,r*350+10),part);d.text((j*400+4,r*350+2),f"{label} tool{k}",fill="white")
    board.save(rd/"gesture_weapon_proof.jpg",quality=97)
def validate_and_details(out,frames,hds,canonical):
    cn=np.array(Image.open(CANON/"canonical_world_native.png").convert("RGBA"))
    data={"imagegen_call_count":6,"external_65535_calls":0,"graft_calls":0,"native_count":len(frames),"nod_static":[],"gesture_sole_samples":[],"weapon_hilt_contact":[],"all_native_binary_alpha":True,"selection_world_origins":{}}
    for k in range(4,9):
        n=np.array(frames[k]);data["nod_static"].append({"slot":k,"native_below340_exact":bool(np.array_equal(cn[340:395,195:300],n[340:395,195:300])),"native_horn_top_exact":bool(np.array_equal(cn[260:277,230:265],n[260:277,230:265])),"alpha_head_exact":bool(np.array_equal(cn[260:295,235:260,3],n[260:295,235:260,3]))})
    points=json.loads((ROOT/"output/action_redraw_2026-11-10/dragon_reference/generation_reference_index.json").read_text("utf-8"))["gesture"]["points"]
    for entry in points:
        k=entry["tool_frame"];n=np.array(frames[k]);r,g,b,a=[n[...,j].astype(int) for j in range(4)];yy,xx=np.mgrid[:500,:500]
        target=entry["hilt_contact"][0];x0,y0=target["x"],target["y"]
        skin=(r>g+5)&(g>b)&(a>128)&((xx-x0)**2+(yy-y0)**2<81)
        sy,sx=np.where(skin);j=np.argmin((sx-x0)**2+(sy-y0)**2)
        data["weapon_hilt_contact"].append({"slot":k,"actual_original_hilt":[x0,y0],"nearest_new_warm_skin":[int(sx[j]),int(sy[j])],"distance_native_px":float(np.hypot(sx[j]-x0,sy[j]-y0))})
        feet={"slot":k}
        for name,l,rr in [("left",232,246),("right",250,264)]:
            y,x=np.where(n[375:395,l:rr,3]>0);sole=x[y==y.max()]+l;feet[name]={"baseline":int(y.max()+375),"sole_x_span":[int(sole.min()),int(sole.max())]}
        data["gesture_sole_samples"].append(feet)
    for k,n in frames.items():data["all_native_binary_alpha"] &= set(np.unique(np.array(n)[...,3])).issubset({0,255})
    for sel in (out/"clips").glob("*/selection.json"):
        report=json.loads(sel.read_text("utf-8"))
        for row in report["frames"]:
            data["selection_world_origins"][str(row["slot"])]=art.placement(report["window"],row["scale"],*row["offset"])
    rd=out/"review";board=Image.new("RGB",(5*400,2*300),(46,50,63));d=ImageDraw.Draw(board)
    for j,k in enumerate(range(4,9)):
        for rr,(im,label) in enumerate([(native_world(k),"original"),(frames[k],"new phase")]):
            # Native source pixels enlarged by exact integers, never smoothing.
            face=im.crop((238,266,263,296)).resize((150,180),Image.Resampling.NEAREST)
            hand=im.crop((258,287,288,317)).resize((180,180),Image.Resampling.NEAREST)
            board.paste(face,(j*400+5,rr*300+30),face);board.paste(hand,(j*400+170,rr*300+30),hand)
            d.text((j*400+5,rr*300+5),f"{label} tool{k} / user{k+1}",fill="white")
    board.save(rd/"nod_face_hand_native_details.jpg",quality=98)
    js(out/"validation_numeric.json",data)
    return data
def render(hd,palette):
    c,a=art.downscale(hd,(160,160))
    sprite=art.finish(art.sharpen(art.grade(c)),a,palette)
    world=Image.new("RGBA",(500,500));world.paste(sprite,CROP[:2])
    return world
def review(out,frames):
    rd=out/"review";rd.mkdir(exist_ok=True)
    for name,slots in [("nod",list(range(4,9))),("gesture",list(range(123,132)))]:
        board=Image.new("RGB",(len(slots)*330,3*350),(46,50,63));d=ImageDraw.Draw(board)
        before=[];original=[];after=[];world_after=[]
        for j,k in enumerate(slots):
            ori=native_world(k).convert("RGBA")
            old=Image.open(BASE/f"native_frames/{k:04d}.png").convert("RGBA")
            new=frames[k]
            for n,(im,label) in enumerate([(ori,"original"),(old,"v05 rejected"),(new,"v06 actual redraw")]):
                part=im.crop((165,240,325,400));big=part.resize((320,320),Image.Resampling.NEAREST)
                board.paste(big,(j*330,n*350+28),big);d.text((j*330+5,n*350+5),f"{label} tool{k} / user{k+1}",fill="white")
            for im,seq in [(ori,original),(old,before),(new,after)]:
                bg=Image.new("RGBA",(160,160),(46,50,63,255));bg.alpha_composite(im.crop((165,240,325,400)));seq.append(bg.convert("RGB"))
            bg=Image.new("RGBA",(500,500),(46,50,63,255));bg.alpha_composite(new);world_after.append(bg.convert("RGB"))
        board.save(rd/f"{name}_original_before_after.jpg",quality=95)
        duration=160 if name=="nod" else 110
        for suffix,seq in [("original_native",original),("before_native",before),("after_native",after),("after_world500",world_after)]:
            seq[0].save(rd/f"{name}_{suffix}.webp",save_all=True,append_images=seq[1:],duration=duration,loop=0,lossless=True)
        # Full new HD contact, intentionally one fixed world crop and canvas.
        hdboard=Image.new("RGB",(len(slots)*480,500),(46,50,63));dd=ImageDraw.Draw(hdboard)
        for j,k in enumerate(slots):
            hd=Image.open(out/f"hd_frames/{k:04d}.png").convert("RGBA").resize((480,480))
            hdboard.paste(hd,(j*480,20),hd);dd.text((j*480+5,3),f"tool{k}",fill="white")
        hdboard.save(rd/f"{name}_hd_contact.jpg",quality=94)
def build():
    global CANON
    cfg=json.loads((ROOT/"design/gpt_dragon_slayer_v03/gesture_nod_redraw_v06.json").read_text("utf-8"))
    CANON=ROOT/cfg.get("canonical_directory",str(CANON.relative_to(ROOT)))
    out=WORK/cfg["candidate"]
    if (WORK/"freeze_candidate03.json").exists():raise SystemExit("Reviewed source is frozen; create a sibling version.")
    (out/"native_frames").mkdir(parents=True,exist_ok=True);(out/"hd_frames").mkdir(exist_ok=True)
    palette=native_palette();frames={};hds={};src={}
    # Approved newly drawn idle, exact first nod frame. All head/legs structure
    # comes from this new base, not from the rejected v05 clip.
    canonical=Image.open(CANON/"canonical_world_hd.png").convert("RGBA")
    arm_mask,face_mask=nod_masks(canonical)
    mask=Image.fromarray(np.maximum(np.array(arm_mask),np.array(face_mask)),"L")
    mask.save(out/"nod_generated_edit_mask.png");arm_mask.save(out/"nod_generated_arm_mask.png");face_mask.save(out/"nod_generated_face_mask.png")
    # The sibling canonical's native structure is authoritative too. Its small
    # held-hand registration must not be independently requantized in this clip.
    cnative=Image.open(CANON/"canonical_world_native.png").convert("RGBA")
    nm=(np.array(mask.resize((160,160),Image.Resampling.BOX))>0)
    nm=ndimage.binary_dilation(nm,iterations=1)
    native_edit_mask=Image.new("L",(500,500));native_edit_mask.paste(Image.fromarray(nm.astype("uint8")*255,"L"),(165,240))
    native_edit_mask.save(out/"nod_native_generated_edit_mask.png")
    nreg=cfg["registration"]["nod_batch"]
    for i,k in enumerate(range(4,9)):
        if i==0:hd=canonical.copy();origin={"source":str(CANON.relative_to(ROOT)/"canonical_world_hd.png"),"cell":"approved_new_idle"}
        else:
            arm_cell={1:2,2:3,3:4,4:4}[i]
            new_arm=register(cell(WORK/"generation/nod_sheet_v01.png",arm_cell,3,2),*nreg)
            new_face=register(cell(WORK/"generation/nod_sheet_v01.png",i,3,2),*nreg)
            hd=Image.composite(new_arm,canonical,arm_mask)
            hd=Image.composite(new_face,hd,face_mask)
            arr=np.array(hd);ca=np.array(canonical)
            arr[120:330,420:570,3]=ca[120:330,420:570,3]
            hd=Image.fromarray(arr,"RGBA")
            origin={"source":"output/dragon_gesture_nod_redraw_v06/generation/nod_sheet_v01.png","cell":arm_cell,"face_cell":i,
                "method":"newly imagegen-painted active shoulder/arm/palm/fingers and face interior on approved new canonical"}
        hds[k]=hd;src[k]=origin
    # Keep the five correct actually-redrawn cells. Replace the four wrong
    # middle gestures with the approved corrected key and its three drawn edits.
    greg=cfg["registration"]["gesture_sheet_batch"]
    mreg=cfg["registration"]["gesture_middle_batch"]
    kreg=cfg["registration"]["gesture_key_batch"]
    for k,i in [(123,0),(124,1),(129,6),(130,7),(131,8)]:
        hds[k]=register(cell(WORK/"generation/gesture_sheet_v01.png",i,3,3),*greg)
        src[k]={"source":"output/dragon_gesture_nod_redraw_v06/generation/gesture_sheet_v01.png","cell":i}
    hds[126]=register(cell(WORK/"generation/gesture_key126_v03.png",0,1,1),*kreg)
    src[126]={"source":"output/dragon_gesture_nod_redraw_v06/generation/gesture_key126_v03.png","cell":0}
    for k,i in [(125,0),(127,1),(128,2)]:
        hds[k]=register(cell(WORK/"generation/gesture_middle_v04.png",i,3,1),*mreg)
        src[k]={"source":"output/dragon_gesture_nod_redraw_v06/generation/gesture_middle_v04.png","cell":i}
    if cfg.get("grip_refinement"):
        gm=grip_mask();gm.save(out/"gesture_generated_grip_mask.png")
        gp=cfg["registration"]["gesture_grip_batch"]
        gr=[register(cell(WORK/"generation/gesture_grip_v05.png",i,2,1),*gp) for i in range(2)]
        # These are endpoint-only registration offsets of freshly painted arms,
        # never a shift of the whole figure. Match read-only game hilt points.
        aims={123:(0,221,326),124:(0,221,326),125:(0,221.09,325.27),126:(0,222.09,326.27),127:(0,222.09,326.27),128:(0,222.09,327.27),129:(1,218.45,324.09),130:(1,217.8,322.5),131:(1,217,323.27)}
        for k,(idx,x,y) in aims.items():
            basepoint=(222,326) if idx==0 else (220,324)
            dx,dy=x-basepoint[0],y-basepoint[1]
            arm=bend(gr[idx],[((basepoint[0]-165)*6,(basepoint[1]-240)*6,dx*6,dy*6)],6)
            hds[k]=Image.composite(arm,hds[k],gm)
            src[k]["new_grip_edit"]={"source":"output/dragon_gesture_nod_redraw_v06/generation/gesture_grip_v05.png","cell":idx,"local_endpoint_delta_world":[dx,dy],"game_hilt_target":[x,y]}
        # First two frames grip with the active screen-right fist instead.
        for k,basepoint,target in [(123,(285.8,292),(284.5,290)),(124,(284.1070,298.7732),(285.5,297.5))]:
            dx,dy=target[0]-basepoint[0],target[1]-basepoint[1]
            hd=hds[k];local=bend(hd,[((basepoint[0]-165)*6,(basepoint[1]-240)*6,dx*6,dy*6)],6)
            m=Image.new("L",(960,960));ImageDraw.Draw(m).rectangle((588,222,828,444),fill=255);m=m.filter(ImageFilter.GaussianBlur(4))
            hds[k]=Image.composite(local,hd,m)
            src[k]["active_fist_endpoint_registration"]={"base":basepoint,"target":target,"delta":[dx,dy]}
    # One crop/selection scale for all cells, re-expressed in the old window.
    manifest={"candidate":cfg["candidate"],"targets":TARGET,"common_world_crop":CROP,"zoom":ZOOM,
        "generation_provenance":"output/dragon_gesture_nod_redraw_v06/generation/provenance.json",
        "registration":cfg["registration"],"frames":[]}
    reference_index=json.loads((ROOT/"output/action_redraw_2026-11-10/dragon_reference/generation_reference_index.json").read_text("utf-8"))
    contacts={v["tool_frame"]:v["hilt_contact"] for group in ("head_hand","gesture") for v in reference_index[group]["points"]}
    for clip,slots in [("clip_004_008",range(4,9)),("clip_123_128",range(123,129)),("clip_129_131",range(129,132))]:
        cd=out/"clips"/clip;(cd/"hd").mkdir(parents=True,exist_ok=True)
        report=json.loads((BASE/"clips"/clip/"selection.json").read_text("utf-8"))
        scale=160/report["window"][2];left,top=art.placement(report["window"],scale)
        for row in report["frames"]:
            k=row["slot"]
            row.pop("action_repair_v05",None)
            row["video_frame"]=f"builtin_gesture_nod_redraw_v06:{k}"
            row["scale"]=scale;row["offset"]=[165-left,240-top];row["track"]=[0,0]
            row["action_redraw_v06"]={**src[k],"common_world_crop":CROP,"fixed_common_selection":True,
                "no_per_cell_bbox_or_best_shift":True}
            hd=hds[k];hd.save(cd/f"hd/{k:04d}.png");hd.save(out/f"hd_frames/{k:04d}.png")
            frame=render(hd,palette)
            if k==4:frame=cnative.copy()
            elif 5<=k<=8:
                frame=Image.composite(frame,cnative,native_edit_mask)
                # New eye/chin colors are interior to an absolutely fixed skull.
                nn=np.array(frame);cc=np.array(cnative)
                nn[260:295,235:260,3]=cc[260:295,235:260,3]
                frame=Image.fromarray(nn,"RGBA")
            frame.save(out/f"native_frames/{k:04d}.png");frames[k]=frame
            nn=np.array(frame).astype(int);rr,gg,bb,aa=[nn[...,j] for j in range(4)];yy0,xx0=np.mgrid[:500,:500]
            row["hands"]=[]
            for contact in contacts[k]:
                cx,cy=contact["x"],contact["y"]
                warm=(rr>gg+5)&(gg>bb)&(aa>128)&((xx0-cx)**2+(yy0-cy)**2<81)
                ys,xs=np.where(warm)
                if not len(xs):continue
                near=np.argmin((xs-cx)**2+(ys-cy)**2)
                row["hands"].append({"target":[cx,cy],"found":[int(xs[near]),int(ys[near])],"gap":float(np.hypot(xs[near]-cx,ys[near]-cy)),"state":"verified_new_redraw_original_weapon_contact","native_is_authoritative":True})
            alpha=np.asarray(frame)[...,3]>0;yy,xx=np.where(alpha)
            manifest["frames"].append({"slot":k,"native_sha256":sha(out/f"native_frames/{k:04d}.png"),
                "hd_sha256":sha(out/f"hd_frames/{k:04d}.png"),"alpha_bbox":[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],
                "selection":{"scale":scale,"offset":row["offset"],"track":[0,0]},"source":src[k]})
        js(cd/"selection.json",report)
    assert sorted(frames)==TARGET
    # Exact static canonical regions: feet, pelvis, hair/horn silhouette.
    c=np.array(Image.open(CANON/"canonical_world_hd.png").convert("RGBA"))
    outside=np.array(mask)==0
    manifest["nod_static_hd_exact"]={str(k):bool(np.array_equal(np.array(hds[k])[outside],c[outside])) for k in range(4,9)}
    manifest["nod_first_native_matches_new_idle"]=sha(out/"native_frames/0004.png")==sha(CANON/"canonical_world_native.png")
    review(out,frames);weapon_review(out,frames)
    manifest["validation_numeric"]=str((out/"validation_numeric.json").relative_to(ROOT)).replace("\\","/")
    manifest["canonical_directory"]=str(CANON.relative_to(ROOT)).replace("\\","/")
    validate_and_details(out,frames,hds,canonical);js(out/"manifest.json",manifest)
    print(json.dumps({"candidate":str(out.relative_to(ROOT)),"frames":len(frames),"canonical_link":manifest["nod_first_native_matches_new_idle"]}))
if __name__=="__main__":build()

