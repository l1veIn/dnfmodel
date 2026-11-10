"""Replace only the wrong rear-reaching arm in Claude game frames 5 and 6.

Prepare by default; --apply publishes the two reviewed frames to the workbench.
The head, front hand and lower body remain from the approved original HD.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from fix_claude_idle_feet import native, P, ROOT

WORK = ROOT / "output/validation/claude_motion_review_2026-11-09/reload"
CLIP = P.out / "clips/clip_004_009"
POLYGONS = {
    4: [(170,147),(233,147),(228,206),(223,237),(222,255),(203,273),(195,315),(140,315),(140,245),(150,196)],
    5: [(150,147),(233,147),(232,210),(223,246),(204,267),(193,294),(111,294),(111,229),(127,181)],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def premul(array):
    value = array.astype(np.float32)
    value[..., :3] *= value[..., 3:] / 255
    return value


def straight(array):
    result = array.copy()
    result[..., :3] /= np.maximum(result[..., 3:] / 255, 1e-5)
    return np.clip(result, 0, 255).round().astype(np.uint8)


def gray_on_back(array):
    a = array[..., 3:] / 255.0
    visible = (array[..., :3] * a + 128 * (1-a)).astype(np.uint8)
    return cv2.cvtColor(visible, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255


def aligned_edit(original, edited):
    edited = np.asarray(edited.resize(original.size, Image.Resampling.LANCZOS))
    original_array = np.asarray(original)
    stable = np.zeros(original_array.shape[:2], np.uint8)
    stable[16:150, 196:307] = 255
    stable[330:545, 190:330] = 255
    warp = np.eye(2, 3, dtype=np.float32)
    score, warp = cv2.findTransformECC(gray_on_back(original_array), gray_on_back(edited), warp,
                                     cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 200, 1e-6), stable, 5)
    if score < 0.85 or np.max(np.abs(warp[:, :2] - np.eye(2))) > 0.06:
        raise ValueError(f"Edited pose drifted too far for local arm replacement: {score}, {warp}")
    warped = cv2.warpAffine(premul(edited), warp, original.size,
                            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
    return straight(warped), float(score), warp.tolist()


def prepare(apply=False):
    before = WORK / "before"
    staged = WORK / "staged"
    before.mkdir(parents=True, exist_ok=True)
    staged.mkdir(exist_ok=True)
    if not (before / "selection.json").exists():
        shutil.copy2(CLIP / "selection.json", before / "selection.json")
        for k in POLYGONS:
            shutil.copy2(CLIP / f"hd/{k:04d}.png", before / f"hd_{k:04d}.png")
            shutil.copy2(P.out / f"native_frames/{k:04d}.png", before / f"native_{k:04d}.png")
            fitted = CLIP / f"hdfit/{k:04d}.png"
            if fitted.exists():
                shutil.copy2(fitted, before / f"hdfit_{k:04d}.png")
    report = json.loads((before / "selection.json").read_text("utf-8"))
    palette = Image.open(ROOT / "output/validation/claude_idle_feet_fix/palette_original.png")
    output = []
    for k, polygon in POLYGONS.items():
        row = next(row for row in report["frames"] if row["slot"] == k)
        original = Image.open(before / f"hd_{k:04d}.png").convert("RGBA")
        old_native = np.asarray(Image.open(before / f"native_{k:04d}.png").convert("RGBA"))
        np.testing.assert_array_equal(np.asarray(native(original, row, report, palette)), old_native)
        edit_path = WORK / f"generated/frame_{k:04d}_edit.png"
        edit, score, warp = aligned_edit(original, Image.open(edit_path).convert("RGBA"))
        mask_image = Image.new("L", original.size)
        ImageDraw.Draw(mask_image).polygon(polygon, fill=255)
        weight = np.asarray(mask_image.filter(ImageFilter.GaussianBlur(3)), dtype=np.float32) / 255
        weight[weight < 1/255] = 0
        weight[:151] = 0
        weight[325:] = 0
        # Preserve the opposite forearm and the front hand crossing the waist.
        weight[198:241, 224:] = 0
        mixed = straight(premul(np.asarray(original)) * (1-weight[...,None]) + premul(edit) * weight[...,None])
        mixed[weight == 0] = np.asarray(original)[weight == 0]
        fixed = Image.fromarray(mixed)
        image = native(fixed, row, report, palette)
        np.testing.assert_array_equal(np.asarray(image)[290:], old_native[290:])
        np.testing.assert_array_equal(np.asarray(image)[:238], old_native[:238])
        fixed.save(staged / f"hd_{k:04d}.png")
        image.save(staged / f"native_{k:04d}.png")
        Image.fromarray((weight * 255).astype(np.uint8)).save(staged / f"mask_{k:04d}.png")
        if apply:
            for source, destination in ((staged / f"hd_{k:04d}.png", CLIP / f"hd/{k:04d}.png"),
                                        (staged / f"hd_{k:04d}.png", CLIP / f"hdfit/{k:04d}.png"),
                                        (staged / f"native_{k:04d}.png", P.out / f"native_frames/{k:04d}.png")):
                destination.parent.mkdir(exist_ok=True)
                temporary = destination.with_suffix(".arm-repair.tmp")
                shutil.copyfile(source, temporary)
                temporary.replace(destination)
        output.append(dict(tool_frame=k, generated=edit_path.relative_to(ROOT).as_posix(),
                           generated_sha256=sha(edit_path), ecc_score=score, sampling_affine=warp,
                           mask_polygon=polygon, mask_feather=3,
                           protected_head_and_lower_body_max_rgba_difference=0,
                           native_sha256=sha(staged / f"native_{k:04d}.png")))
    proof = Image.new("RGB", (4*300, 420), (55,61,74))
    draw = ImageDraw.Draw(proof)
    for i,k in enumerate(POLYGONS):
        for j,(label,path) in enumerate((("Before",before / f"hd_{k:04d}.png"),("Fixed",staged / f"hd_{k:04d}.png"))):
            picture = Image.open(path).convert("RGBA").crop((110,145,310,325)).resize((300,270),Image.Resampling.NEAREST)
            x=(i*2+j)*300
            draw.text((x+8,10),f"Game {k+1} {label}",fill="white")
            proof.paste(picture,(x,40),picture)
    proof.save(WORK / "arm_before_after.png")
    (WORK / "repair_report.json").write_text(json.dumps(dict(applied=apply,method="aligned local RGBA arm replacement",frames=output,installed=False),indent=2)+'\n',"utf-8")
    print(json.dumps(dict(applied=apply,frames=output),indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true")
    prepare(parser.parse_args().apply)
