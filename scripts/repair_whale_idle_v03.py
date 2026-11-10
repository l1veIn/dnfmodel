"""Prepare eight local whale-maid idle repairs without changing released inputs.

The original arms-down left cell is reused. Standing motion is driven from
planted toe contacts; battle changes only the original small ahoge layer.
No network, image generation, final/build, installation or issue-store writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
os.environ["PATCH_ID"] = "fatfish_whale_maid"
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit import art, sheets, source
from kit.config import P

WORK = ROOT / "output/whale_action_repair_v03"
CONFIG = ROOT / "design/fatfish_whale_maid/action_repair_v03.json"
OLD = ROOT / "output/fatfish_whale_maid_v01"
SLOTS = list(range(10, 18))
CLIPS = {"clip_010_013": list(range(10, 14)), "clip_014_017": list(range(14, 18))}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def warp(image, xfield, yfield):
    arr = np.asarray(image.convert("RGBA"), np.float32)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    premul = arr.copy()
    premul[..., :3] *= arr[..., 3:] / 255
    out = np.stack([ndimage.map_coordinates(premul[..., c], [yy-yfield, xx-xfield], order=1, mode="constant") for c in range(4)], 2)
    out[..., :3] /= np.maximum(out[..., 3:] / 255, 1e-3)
    still = (np.abs(xfield) < .001) & (np.abs(yfield) < .001)
    out[still] = arr[still]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def palette():
    path = WORK / "palette_original.png"
    if path.exists():
        return Image.open(path).copy()
    samples = []
    for clip in P.clips():
        folder = OLD / "clips" / clip["id"]
        report = json.loads((folder / "selection.json").read_text("utf-8"))
        for row in report["frames"][::3]:
            hd = Image.open(folder / f"hd/{row['slot']:04d}.png").convert("RGBA")
            size = round(report["window"][2] * row["scale"])
            color, alpha = art.downscale(hd, (size, size))
            samples.append((art.sharpen(art.grade(color)), alpha))
    result = art.build_palette(samples, 96)
    frozen = Image.new("P", (1, 1)); frozen.putpalette(result.getpalette()); frozen.save(path)
    return frozen


def native(hd, row, report, pal):
    if row.get("hands"):
        raise ValueError("Idle repairs expect the existing empty hand-fit list")
    size = round(report["window"][2] * row["scale"])
    color, alpha = art.downscale(hd, (size, size))
    sprite = art.finish(art.sharpen(art.grade(color)), alpha, pal)
    left, top = art.placement(report["window"], row["scale"], row["offset"][0] + row["track"][0], row["offset"][1] + row["track"][1])
    world = Image.new("RGBA", (P.canvas + 400, P.canvas + 400))
    world.paste(sprite, (left + 200, top + 200))
    return world.crop((200, 200, 200+P.canvas, 200+P.canvas))


def raw_cell(cell):
    raw = Image.open(OLD / "parts/raw/poses_idle_v1_0.png").convert("RGB")
    cw, ch = raw.width // 2, raw.height
    result = Image.new("RGBA", (max(cw, ch), max(cw, ch)))
    result.paste(art.matte(raw.crop((cell*cw, 0, (cell+1)*cw, ch))), (0, 0))
    return result


def standing(hd, per_world, index):
    """Raise the heels a fraction of a pixel while the two toe caps stay put."""
    h, w = hd.height, hd.width
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    lift = [0, .95, 0, .60][index]
    rock = [0, .55, 0, -.45][index]
    # Above the ankles the body follows the heel lift as a single relaxed mass.
    # Inside each shoe that displacement dies away toward the forward toe.
    blend = np.clip((yy - 960) / 90, 0, 1)
    blend = blend * blend * (3 - 2 * blend)
    heel_weight = np.clip((552-xx) / 128, 0, 1)
    yfield = -lift * per_world * (1-blend + blend*heel_weight)
    xfield = rock * per_world * np.clip((1068-yy)/850, 0, 1)
    moved = warp(hd, xfield, yfield)
    # Let only loose ends follow with a small delay; do not counter-twist torso.
    follow = [0, -.20, .15, .25][index]
    spec = {"moves": [
        {"poly": [[235,530],[355,530],[355,650],[235,650]], "dy": follow, "feather": 18},
        {"poly": [[290,430],[365,430],[390,540],[300,560]], "dx": -follow, "feather": 18},
    ]}
    return sheets.micro(moved, spec, per_world)


def ahoge(hd, per_world, index):
    """Reuse and thicken the original arc, attached at the same hair root."""
    arr = np.asarray(hd.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    # This outline follows the arc above the white headband, including its
    # descending left tip; it deliberately excludes the headband and face.
    region = (xx >= 427) & (xx < 520) & (yy >= 112) & (yy < 184)
    region &= (yy < 155) | ((xx < 475) & (yy < 183)) | ((xx > 496) & (yy < 163))
    mask = region & (arr[..., 3] > 0)
    layer = np.zeros_like(arr); layer[mask] = arr[mask]
    background = arr.copy(); background[mask] = 0
    # The source arc becomes less than one output pixel thick. Recover a
    # readable continuous line using its own nearest color, never a new motif.
    alpha = layer[..., 3].astype(np.float32)
    distance, indices = ndimage.distance_transform_edt(alpha < 30, return_indices=True)
    expand = (distance <= 2) & region
    nearest = layer[tuple(indices)]
    layer[expand] = nearest[expand]
    layer[expand, 3] = np.maximum(layer[expand, 3], (255*np.clip(3-distance[expand], 0, 1)).astype(np.uint8))
    yyf, xxf = np.mgrid[0:h, 0:w].astype(np.float32)
    anchor_x, anchor_y = 504., 163.
    sy, sx = 1.44, 1.08
    source_y = anchor_y + (yyf-anchor_y)/sy
    strength = np.clip((anchor_y-source_y)/34, 0, 1)
    sway = [0, .55, .05, -.55][index]
    source_x = anchor_x+(xxf-anchor_x)/sx-sway*per_world*strength
    premul = layer.astype(np.float32)
    premul[..., :3] *= premul[..., 3:] / 255
    sampled = np.stack([ndimage.map_coordinates(premul[..., c], [source_y,source_x], order=1, mode="constant") for c in range(4)],2)
    sampled[..., :3] /= np.maximum(sampled[..., 3:]/255, 1e-3)
    moved = Image.fromarray(np.clip(sampled,0,255).astype(np.uint8),"RGBA")
    result = Image.fromarray(background,"RGBA"); result.alpha_composite(moved)
    return result


def composite_reference(k):
    im = Image.new("RGBA", (P.canvas, P.canvas))
    for layer in P.order:
        im.alpha_composite(source.layer_world(layer,k))
    return im


def board(rows, names, crop, factor, path):
    width, height = crop[2]-crop[0], crop[3]-crop[1]
    out = Image.new("RGB", (4*(width*factor+12), len(rows)*(height*factor+28)), (56,64,80))
    draw = ImageDraw.Draw(out)
    for row,(frames,name) in enumerate(zip(rows,names)):
        for i,im in enumerate(frames):
            x,y=i*(width*factor+12)+6,row*(height*factor+28)
            draw.text((x,y+3), f"{name} {i+1}",fill="white")
            part=im.crop(crop).resize((width*factor,height*factor),Image.Resampling.NEAREST)
            out.paste(part,(x,y+25),part)
    out.save(path)


def animate(frames, path, crop=(210,278,280,392), factor=1):
    seq=[]
    for im in frames:
        part=im.crop(crop)
        bg=Image.new("RGBA",part.size,(56,64,80,255));bg.alpha_composite(part)
        seq.append(bg.convert("RGB").resize((part.width*factor,part.height*factor),Image.Resampling.NEAREST))
    seq[0].save(path,save_all=True,append_images=seq[1:],duration=140,loop=0,lossless=True)


def prepare():
    if (WORK/"frozen.json").exists():
        raise ValueError("Candidate is frozen; do not overwrite approved frames")
    WORK.mkdir(parents=True,exist_ok=True)
    baseline={p.name:sha(p) for p in sorted((OLD/"native_frames").glob("*.png"))}
    if len(baseline)!=174: raise ValueError("Expected174 original character frames")
    save_json(WORK/"protected_native_baseline.json",baseline)
    pal=palette()
    old_reports={name:json.loads((OLD/f"clips/{name}/selection.json").read_text("utf-8")) for name in CLIPS}
    original_reproduction=[]
    for name, slots in CLIPS.items():
        report=old_reports[name]
        for row in report["frames"]:
            hd=Image.open(OLD/f"clips/{name}/hd/{row['slot']:04d}.png").convert("RGBA")
            old=Image.open(OLD/f"native_frames/{row['slot']:04d}.png").convert("RGBA")
            diff=np.abs(np.asarray(native(hd,row,report,pal)).astype(np.int16)-np.asarray(old).astype(np.int16))
            original_reproduction.append({"slot":row["slot"],"max_rgba_delta":int(diff.max()),"changed_visible_pixels":int(np.any(diff,2).sum())})
    base_stand=raw_cell(0)
    all_frames={}; details=[]
    stand_report=old_reports["clip_010_013"]
    stand_base_native=native(base_stand,stand_report["frames"][0],stand_report,pal)
    stand_base_native.save(WORK/"standing_arms_down_base.png")
    # Both forefeet are held at the common supporting ground. These are toe
    # caps, not the whole shoe: the heel above/behind them remains free to lift.
    toe_rois=[[249,381,255,387],[244,376,250,381]]
    for name,slots in CLIPS.items():
        report=old_reports[name]
        hd_dir=WORK/f"candidate/clips/{name}/hd";hd_dir.mkdir(parents=True,exist_ok=True)
        native_dir=WORK/"candidate/native_frames";native_dir.mkdir(parents=True,exist_ok=True)
        per_world=6.965986394557823/report["base_scale"]
        for i,row in enumerate(report["frames"]):
            k=row["slot"]
            if k<14:
                hd=standing(base_stand,per_world,i)
                frame=np.asarray(native(hd,row,report,pal)).copy()
                base=np.asarray(stand_base_native)
                for x0,y0,x1,y1 in toe_rois: frame[y0:y1,x0:x1]=base[y0:y1,x0:x1]
                frame=Image.fromarray(frame,"RGBA")
            else:
                current_hd=Image.open(OLD/f"clips/{name}/hd/{k:04d}.png").convert("RGBA")
                hd=ahoge(current_hd,per_world,i)
                proposed=np.asarray(native(hd,row,report,pal))
                frame=np.asarray(Image.open(OLD/f"native_frames/{k:04d}.png").convert("RGBA")).copy()
                # The headband starts at y295. Preserve it and every body
                # pixel below exactly; the original little arc is above it.
                frame[282:295,238:254]=proposed[282:295,238:254]
                frame=Image.fromarray(frame,"RGBA")
            hd.save(hd_dir/f"{k:04d}.png")
            frame.save(native_dir/f"{k:04d}.png")
            all_frames[k]=frame
            details.append({"slot":k,"user_frame":k+1,"clip":name,"native":(native_dir/f"{k:04d}.png").relative_to(ROOT).as_posix(),"native_sha256":sha(native_dir/f"{k:04d}.png"),"hd":(hd_dir/f"{k:04d}.png").relative_to(ROOT).as_posix(),"hd_sha256":sha(hd_dir/f"{k:04d}.png")})
        report["repair_note"]="v03 local idle repair, original selection scale/offset retained; standing uses original arms-down cell, battle keeps old body and changes ahoge only."
        report["repair_source_raw"]="output/fatfish_whale_maid_v01/parts/raw/poses_idle_v1_0.png"
        if name=="clip_010_013":
            for row in report["frames"]: row["video_frame"]="idle:0; v03 toe-driven motion"
        save_json(WORK/f"candidate/clips/{name}/selection.json",report)
    review=WORK/"review";review.mkdir(exist_ok=True)
    fixed_errors=[]
    for k in range(10,14):
        arr=np.asarray(all_frames[k]);base=np.asarray(stand_base_native)
        fixed_errors.append(max(int(np.abs(arr[y0:y1,x0:x1].astype(np.int16)-base[y0:y1,x0:x1].astype(np.int16)).max()) for x0,y0,x1,y1 in toe_rois))
    body_errors=[]
    for k in range(14,18):
        old=np.asarray(Image.open(OLD/f"native_frames/{k:04d}.png").convert("RGBA"));new=np.asarray(all_frames[k])
        diff=np.any(old!=new,2);diff[282:295,238:254]=False
        body_errors.append(int(diff.sum()))
    for name,slots in CLIPS.items():
        before=[Image.open(OLD/f"native_frames/{k:04d}.png").convert("RGBA") for k in slots]
        official=[composite_reference(k) for k in slots]
        after=[all_frames[k] for k in slots]
        short="standing" if slots[0]==10 else "battle"
        board([official,before,after],["official all layers","before","candidate"],(210,278,280,392),3,review/f"{short}_comparison.png")
        animate(after,review/f"{short}_native.webp")
        animate(after,review/f"{short}_x3.webp",factor=3)
        if short=="standing": board([before,after],["before","candidate"],(236,369,260,390),8,review/"standing_feet.png")
        else: board([before,after],["before","candidate"],(238,282,257,310),8,review/"battle_ahoge.png")
    current={p.name:sha(p) for p in sorted((OLD/"native_frames").glob("*.png"))}
    if current!=baseline: raise ValueError("Original native inputs changed during preparation")
    assert max(fixed_errors)==0 and max(body_errors)==0
    record={"status":"prepared_for_root_visual_review","target_slots":SLOTS,"unchanged_non_target_frames":166,"all174_original_native_unchanged":True,"original_render_reproduction":original_reproduction,"toe_contact_rois":toe_rois,"toe_contact_max_rgba_delta":fixed_errors,"battle_body_changed_pixels_outside_ahoge":body_errors,"frames":details,"source_raw":"output/fatfish_whale_maid_v01/parts/raw/poses_idle_v1_0.png","source_raw_sha256":sha(OLD/"parts/raw/poses_idle_v1_0.png"),"palette":"output/whale_action_repair_v03/palette_original.png","palette_sha256":sha(WORK/"palette_original.png"),"paid_calls":0,"image_generation_calls":0,"installed":False}
    save_json(WORK/"repair_report.json",record)
    save_json(CONFIG,{"project":"fatfish_whale_maid","issues":[1,2],"target_slots":SLOTS,"candidate_native":"output/whale_action_repair_v03/candidate/native_frames","candidate_clips":"output/whale_action_repair_v03/candidate/clips","report":"output/whale_action_repair_v03/repair_report.json","source_inputs_untouched":True})
    print(json.dumps({k:v for k,v in record.items() if k not in ["frames","original_render_reproduction"]},ensure_ascii=False,indent=2))


def freeze():
    report=json.loads((WORK/"repair_report.json").read_text("utf-8"))
    if (WORK/"frozen.json").exists(): raise ValueError("Already frozen")
    for row in report["frames"]:
        for key in ["native","hd"]:
            if sha(ROOT/row[key])!=row[key+"_sha256"]:raise ValueError("Candidate changed since visual review")
    save_json(WORK/"frozen.json",{"status":"root_selected","report_sha256":sha(WORK/"repair_report.json"),"script_sha256":sha(Path(__file__)),"config_sha256":sha(CONFIG),"target_slots":SLOTS,"frames":report["frames"],"installed":False})
    print("Frozen selected8-frame idle candidate; no old asset or package writes.")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["prepare","freeze"])
    command=parser.parse_args().command
    prepare() if command=="prepare" else freeze()
