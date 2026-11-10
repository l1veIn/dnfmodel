"""Rebuild only Claude's four crossing-gun frames from the reviewed repair art.

The source's first frame is a purposeful fast smear. The three settled frames
share one drawing; only their small measured hand changes are animated. No NPK
build, installation, paid image requests, or writes to other character frames.
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

OUT = ROOT / "output/validation/claude_motion_review_2026-11-09/hold"
BEFORE, STAGE = OUT / "before", OUT / "staged"
CLIP = P.out / "clips/clip_064_067"
RAW = P.parts / "raw/poses_hold_repair_v4_0.png"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def warp(image, dx, dy):
    source = np.asarray(image).astype(np.float32)
    dxdy, dxdx = np.gradient(dx)
    dydy, dydx = np.gradient(dy)
    determinant = (1-dxdx) * (1-dydy) - dxdy*dydx
    if float(determinant.min()) <= 0.35:
        raise ValueError("Local pose adjustment would compress/fold the drawing too strongly")
    yy, xx = np.mgrid[:image.height, :image.width].astype(np.float32)
    sx, sy = xx.copy(), yy.copy()
    for _ in range(7):
        sx = xx - ndimage.map_coordinates(dx, [sy, sx], order=1, mode="nearest")
        sy = yy - ndimage.map_coordinates(dy, [sy, sx], order=1, mode="nearest")
    premult = source.copy()
    premult[..., :3] *= source[..., 3:] / 255
    moved = np.stack([ndimage.map_coordinates(premult[..., c], [sy, sx], order=1, mode="constant") for c in range(4)], 2)
    moved[..., :3] /= np.maximum(moved[..., 3:] / 255, 1e-3)
    active = np.abs(dx) + np.abs(dy) > 0.001
    return Image.fromarray(np.clip(np.where(active[..., None], moved, source), 0, 255).astype(np.uint8), "RGBA")


def palm(image, box):
    x0, y0, x1, y1 = box
    roi = np.asarray(image)[y0:y1, x0:x1].astype(np.int16)
    mask = ((roi[..., 0] > 170) & (roi[..., 0] - roi[..., 1] > 26)
            & (roi[..., 0] - roi[..., 1] < 85) & (roi[..., 1] - roi[..., 2] > 8)
            & (roi[..., 3] > 128))
    yy, xx = np.nonzero(mask)
    if len(xx) < 30:
        raise ValueError("The expected newly drawn palm is missing")
    return np.array([xx.mean() + x0, yy.mean() + y0])


def small(image, size, palette):
    rgb, alpha = art.downscale(image, (size, size))
    return art.finish(art.sharpen(art.grade(rgb)), alpha, palette)


def original(slot):
    image = Image.new("RGBA", (P.canvas, P.canvas))
    for layer in P.order:
        image.alpha_composite(layer_world(layer, slot))
    return image


def shoe_target(slot):
    mask = np.zeros((P.canvas, P.canvas), bool)
    for layer in P.order:
        if layer.startswith("shoes/"):
            mask |= np.asarray(layer_world(layer, slot))[..., 3] > 128
    targets = []
    for a, b in ((0, 240), (240, 500)):
        yy, xx = np.nonzero(mask[:, a:b])
        bottom = yy.max() + 1
        band = yy >= bottom - 8
        targets.append((float(xx[band].mean() + a), int(bottom)))
    return targets


def place(image, size, palette, source_slot):
    sprite = small(image, size, palette)
    box = sprite.getbbox()
    alpha = np.asarray(sprite)[..., 3] > 128
    yy, xx = np.nonzero(alpha[box[3]-8:, :size//2])
    target = shoe_target(source_slot)[0]
    left, top = round(target[0] - xx.mean()), target[1] - box[3]
    world = Image.new("RGBA", (P.canvas, P.canvas))
    world.paste(sprite, (left, top))
    return world, (left, top)


def fit_feet(image, size, palette, source_slot):
    world, (left, top) = place(image, size, palette, source_slot)
    pixels = np.asarray(world)
    goals = shoe_target(source_slot)
    yy, xx = np.nonzero(pixels[325:340, 240:300, 3] > 128)
    right_bottom = int(yy.max() + 326)
    band = yy >= yy.max() - 7
    right_x = float(xx[band].mean() + 240)
    delta = np.array([goals[1][0] - right_x, goals[1][1] - right_bottom])
    yy, xx = np.mgrid[:image.height, :image.width].astype(np.float32)
    weight = smooth((xx - 230) / 150) * smooth((yy - 350) / 125)
    ratio = image.width / size
    fixed = warp(image, weight * delta[0] * ratio, weight * delta[1] * ratio)
    return fixed, dict(right_foot_world_shift=delta.tolist(), targets=goals)


def fit_arms(image, size, palette, source_slot, centers, max_move=6):
    _, (left, top) = place(image, size, palette, source_slot)
    factor = size / image.width
    targets = [np.array(t[:2]) for t in hands.sprite_hands(source_slot)]
    yy, xx = np.mgrid[:image.height, :image.width].astype(np.float32)
    dx, dy = np.zeros_like(xx), np.zeros_like(yy)
    records = []
    for n, (center, target) in enumerate(zip(centers, targets)):
        world = np.array([left, top]) + center * factor
        delta = target - world
        distance = float(np.linalg.norm(delta))
        if distance > max_move:
            raise ValueError(f"Frame {source_slot} needs a large arm stretch {distance:.2f}px; revise the art")
        radius, inner = (100, 20) if n == 0 else (75, 23)
        dist = np.hypot(xx - center[0], yy - center[1])
        weight = smooth((radius - dist) / (radius - inner))
        if n == 0:
            weight *= 1 - smooth((xx - 260) / 25)
        else:
            weight *= smooth((yy - 210) / 25)
        # Face, head, neck and all lower-body pixels stay exactly unchanged.
        weight *= 1 - smooth((xx - 240) / 20) * (1-smooth((yy - 145) / 20))
        weight *= smooth((yy - 130) / 15) * (1-smooth((yy - 300) / 20))
        weight[((xx >= 285) & (yy <= 205)) | ((xx >= 260) & (yy <= 145)) | (yy <= 130)] = 0
        weight[yy >= 320] = 0
        dx += weight * delta[0] / factor
        dy += weight * delta[1] / factor
        records.append(dict(target=target.tolist(), found=world.tolist(), gap=distance,
                            hd_palm=center.tolist(), correction_world=delta.tolist(), state="small local arm correction"))
    fitted = warp(image, dx, dy)
    protected = ((xx >= 285) & (yy <= 205)) | ((xx >= 260) & (yy <= 145)) | (yy <= 130) | (yy >= 320)
    np.testing.assert_array_equal(np.asarray(fitted)[protected], np.asarray(image)[protected])
    return fitted, records


def build(apply=False):
    if apply:
        raise SystemExit(
            "This pose was rejected and superseded. "
            "Run scripts/fix_claude_crossed_arms.py --apply instead."
        )
    cfg = json.loads((ROOT / "design/claude_gunner/hold_repair.json").read_text("utf-8"))
    palette = Image.open(ROOT / cfg["palette"]).copy()
    sheet = Image.open(RAW).convert("RGB")
    if sheet.size != (1254, 1254):
        raise ValueError("Unexpected reviewed repair sheet dimensions")
    for sub in ("hd", "hdfit", "native_frames"):
        (STAGE / sub).mkdir(parents=True, exist_ok=True)
    if not (BEFORE / "selection.json").exists():
        raise ValueError("Create the pre-repair backup before publishing")
    report = json.loads((BEFORE / "selection.json").read_text("utf-8"))
    report["sheet"] = "hold_repair_v4"
    report["repair"] = "design/claude_gunner/hold_repair.json"
    result, frames = [], []
    raw_cells = [art.matte(sheet.crop((n % 2 * 627, n // 2 * 627, (n % 2 + 1) * 627, (n // 2 + 1) * 627))) for n in range(2)]
    # The settled pose uses one consistent drawing rather than three drifting
    # figures; hand changes below come from the actual original target points.
    for n, slot in enumerate(range(64, 68)):
        base = raw_cells[0 if n == 0 else 1].copy()
        size = 180 if n else 179
        corrected_feet, feet_record = fit_feet(base, size, palette, slot)
        rois = cfg["palm_rois"]["smear" if n == 0 else "settled"]
        centers = [palm(corrected_feet, roi) for roi in rois]
        fitted, arm_records = fit_arms(corrected_feet, size, palette, slot, centers)
        frame, (left, top) = place(fitted, size, palette, slot)
        frame = hands.graft(frame, slot, palette)
        corrected_feet.save(STAGE / f"hd/{slot:04d}.png")
        fitted.save(STAGE / f"hdfit/{slot:04d}.png")
        frame.save(STAGE / f"native_frames/{slot:04d}.png")
        row = report["frames"][n]
        scale = size / report["window"][2]
        origin = art.placement(report["window"], scale)
        row.update(video_frame=f"hold_repair:{n}", scale=scale,
                   offset=[left-origin[0], top-origin[1]], track=[0, 0],
                   hands=[{**record, "gap": round(record["gap"], 1), "state": "局部校准"}
                          for record in arm_records], repair_source_cell=0 if n == 0 else 1)
        row["offset_before_ground"] = row["offset"].copy()
        source_box, new_box = original(slot).getbbox(), frame.getbbox()
        result.append(dict(slot=slot, user_frame=slot+1, source_bbox=source_box, new_bbox=new_box,
                           source_height=source_box[3]-source_box[1], new_height=new_box[3]-new_box[1],
                           feet=feet_record, hands=arm_records, max_hand_correction_px=max(r["gap"] for r in arm_records)))
        frames.append(frame)
    (STAGE / "selection.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    board = Image.new("RGB", (4*480, 2*620), (72, 80, 98))
    draw = ImageDraw.Draw(board)
    for n, slot in enumerate(range(64, 68)):
        for j, (tag, im) in enumerate((("original", armed(original(slot), slot)), ("repaired", armed(frames[n], slot)))):
            draw.text((n*480+8, j*620+6), f"{slot+1} / tool{slot} {tag}", fill="white")
            crop=im.crop((185,195,305,340)).resize((480,580), Image.Resampling.NEAREST)
            board.paste(crop, (n*480,j*620+24), crop)
    board.save(OUT / "repaired_contact.png")
    crops=[]
    for slot, frame in zip(range(64,68),frames):
        c=armed(frame,slot).crop((185,195,305,340))
        bg=Image.new("RGBA",c.size,(72,80,98,255));bg.alpha_composite(c)
        crops.append(bg.convert("RGB").resize((360,435),Image.Resampling.NEAREST))
    crops[0].save(OUT/"repaired_animation.gif", save_all=True,append_images=crops[1:],duration=[70,100,100,100],loop=0)
    if apply:
        for slot in range(64,68):
            for sub in ("hd", "hdfit", "native_frames"):
                dest=(P.out/sub if sub=="native_frames" else CLIP/sub)/f"{slot:04d}.png"
                temporary=dest.with_suffix(".hold-repair.tmp")
                shutil.copyfile(STAGE/sub/f"{slot:04d}.png",temporary);temporary.replace(dest)
        temporary=(CLIP/"selection.json").with_suffix(".hold-repair.tmp")
        shutil.copyfile(STAGE/"selection.json",temporary);temporary.replace(CLIP/"selection.json")
    summary=dict(applied=apply,raw=RAW.relative_to(ROOT).as_posix(),raw_sha256=sha(RAW),
                 source="builtin image_gen",frames=result,installed=False,ingame_verified=False,
                 native_sha256=[sha(STAGE/f"native_frames/{k:04d}.png") for k in range(64,68)])
    (OUT/"repair_report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),"utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true")
    build(parser.parse_args().apply)
