"""Bound the existing lunge hand fitting to the arms, restoring the drawn body.

Only tool frames 56--58 are prepared/published. The approved HD is never edited;
the local fitted hand is retained, while the old broad deformation of the gown
and boots is discarded. No generation, NPK build, or game writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
os.environ["PATCH_ID"] = "claude_gunner"
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit import art
from kit.config import P
from kit.hands import graft

CLIP = "clip_052_059"
SLOTS = (56, 57, 58)
FOLDER = P.out / "clips" / CLIP
WORK = ROOT / "output/validation/claude_motion_review_2026-11-09/lunge"
BEFORE = WORK / "before"
STAGED = WORK / "staged"
PALETTE = ROOT / "output/validation/claude_idle_feet_fix/palette_original.png"
POLYGONS = {
    56: [(214,217),(249,209),(278,202),(311,191),(339,186),(362,192),
         (386,201),(400,227),(398,274),(389,297),(343,298),(314,281),
         (274,276),(240,273),(215,258),(207,237)],
    57: [(215,214),(247,209),(275,203),(312,191),(337,188),(357,197),
         (379,203),(396,226),(393,257),(373,274),(338,280),(301,278),
         (267,275),(239,270),(218,256),(209,238)],
    58: [(215,214),(247,209),(275,203),(312,191),(337,188),(357,197),
         (379,203),(396,226),(393,257),(373,274),(338,280),(301,278),
         (267,275),(239,270),(218,256),(209,238)],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    for name in ("hd", "hdfit", "native_frames"):
        (BEFORE / name).mkdir(parents=True, exist_ok=True)
    for slot in SLOTS:
        for name in ("hd", "hdfit"):
            source, target = FOLDER / name / f"{slot:04d}.png", BEFORE / name / f"{slot:04d}.png"
            if not target.exists():
                shutil.copy2(source, target)
        source, target = P.out / f"native_frames/{slot:04d}.png", BEFORE / f"native_frames/{slot:04d}.png"
        if not target.exists():
            shutil.copy2(source, target)
    if not (BEFORE / "selection.json").exists():
        shutil.copy2(FOLDER / "selection.json", BEFORE / "selection.json")
    if not (BEFORE / "clip_native_sha256.json").exists():
        (BEFORE / "clip_native_sha256.json").write_text(json.dumps({
            str(k): sha(P.out / f"native_frames/{k:04d}.png") for k in range(52, 60)
        }, indent=2) + "\n", "utf-8")


def local_mask(size, slot):
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).polygon(POLYGONS[slot], fill=255)
    # The transition lies in sleeve/cape interior and empty background, not
    # across the face, gown, or boot silhouette.
    weight = np.asarray(mask.filter(ImageFilter.GaussianBlur(2.0))).copy()
    y, x = np.mgrid[:size[1], :size[0]]
    protect = (x < 214) | ((y < 223) & (x < 255)) | (y >= 282)
    if slot == 56:
        # The original lower hand's fingertips reach y285. This small empty
        # area beside the waist must be replaced too, otherwise a detached old
        # fingertip remains. The waist itself remains exactly protected.
        protect &= ~((x >= 315) & (x < 410) & (y >= 282) & (y < 300))
    weight[protect] = 0
    weight[weight < 2] = 0
    return weight, protect


def bounded_fit(raw, fitted, slot):
    a, b = np.asarray(raw).copy(), np.asarray(fitted)
    mask, protect = local_mask(raw.size, slot)
    weight = mask.astype(np.float32)[..., None] / 255
    premul_a, premul_b = a.astype(np.float32), b.astype(np.float32)
    premul_a[..., :3] *= premul_a[..., 3:] / 255
    premul_b[..., :3] *= premul_b[..., 3:] / 255
    blended = premul_a * (1 - weight) + premul_b * weight
    blended[..., :3] /= np.maximum(blended[..., 3:] / 255, 1e-5)
    result = np.clip(np.rint(blended), 0, 255).astype(np.uint8)
    # Preserve source bytes exactly in protected/untouched regions, including
    # hidden RGB. Preserve the fitted hand bytes exactly in full-weight cores.
    result[mask == 0] = a[mask == 0]
    result[mask == 255] = b[mask == 255]
    np.testing.assert_array_equal(result[protect], a[protect])
    return Image.fromarray(result, "RGBA"), mask, protect


def render(hd, row, report, palette, hands=True):
    size = round(report["window"][2] * row["scale"])
    color, alpha = art.downscale(hd, (size, size))
    sprite = art.finish(art.sharpen(art.grade(color)), alpha, palette)
    left, top = art.placement(report["window"], row["scale"],
                              row["offset"][0] + row["track"][0],
                              row["offset"][1] + row["track"][1])
    world = Image.new("RGBA", (P.canvas + 400, P.canvas + 400))
    world.paste(sprite, (left + 200, top + 200))
    image = world.crop((200, 200, 200 + P.canvas, 200 + P.canvas))
    return graft(image, row["slot"], palette) if hands else image


def make_contact(raws, fits, results, path):
    board = Image.new("RGB", (1260, 1440), (48, 53, 64))
    draw = ImageDraw.Draw(board)
    for r, slot in enumerate(SLOTS):
        for col, (label, frame) in enumerate(zip(("Raw body", "Old full fit", "Local fit"),
                                                (raws[r], fits[r], results[r]))):
            part = frame.crop((85, 145, 445, 550)).resize((400, 450), Image.Resampling.NEAREST)
            board.paste(part, (col * 420 + 10, r * 480 + 25), part)
            draw.text((col * 420 + 8, r * 480 + 7), f"{slot+1}: {label}", fill="white")
    board.save(path)


def prepare(apply=False):
    snapshot()
    original_selection = (BEFORE / "selection.json").read_bytes()
    original_report = json.loads(original_selection)
    report = json.loads((FOLDER / "selection.json").read_text("utf-8"))
    # A later approved repair can replace neighbouring poses in this clip.
    # Preserve their metadata; only the placement of our own three frames
    # must still match the inputs of this local hand-fit recipe.
    if report["window"] != original_report["window"]:
        raise ValueError("The lunge render window changed since the repair snapshot")
    for slot in SLOTS:
        row = next(r for r in report["frames"] if r["slot"] == slot)
        original_row = next(r for r in original_report["frames"] if r["slot"] == slot)
        if row != original_row:
            raise ValueError(f"The local-fit placement changed for frame {slot}")
    palette = Image.open(PALETTE).copy()
    for name in ("hdfit", "native_frames", "raw_native", "masks"):
        (STAGED / name).mkdir(parents=True, exist_ok=True)
    metrics, raws, fits, results = [], [], [], []
    for slot in SLOTS:
        row = next(row for row in report["frames"] if row["slot"] == slot)
        raw = Image.open(BEFORE / f"hd/{slot:04d}.png").convert("RGBA")
        fit = Image.open(BEFORE / f"hdfit/{slot:04d}.png").convert("RGBA")
        if sha(FOLDER / f"hd/{slot:04d}.png") != sha(BEFORE / f"hd/{slot:04d}.png"):
            raise ValueError("Approved HD changed; re-evaluate this repair")
        baseline = np.asarray(render(fit, row, report, palette))
        old = np.asarray(Image.open(BEFORE / f"native_frames/{slot:04d}.png").convert("RGBA"))
        baseline_error = int(np.abs(baseline.astype(np.int16) - old.astype(np.int16)).max())
        if baseline_error:
            raise ValueError(f"Original native reproduction changed for {slot}: {baseline_error}")
        result, mask, protected = bounded_fit(raw, fit, slot)
        native = render(result, row, report, palette)
        raw_native = render(raw, row, report, palette)
        result.save(STAGED / f"hdfit/{slot:04d}.png")
        native.save(STAGED / f"native_frames/{slot:04d}.png")
        raw_native.save(STAGED / f"raw_native/{slot:04d}.png")
        Image.fromarray(mask).save(STAGED / f"masks/{slot:04d}.png")
        a, b = np.asarray(raw), np.asarray(result)
        # At y300 and below even frame 56's extended fingertip exception ends;
        # all corset/gown/boots in this lower body are exactly the approved HD.
        np.testing.assert_array_equal(b[300:], a[300:])
        n, rn = np.asarray(native), np.asarray(raw_native)
        np.testing.assert_array_equal(n[280:], rn[280:])
        hand = row["hands"][0]["target"]
        tx, ty = hand
        # A small palm/weapon-contact core is unaffected by restricting the
        # distant deformation; the grip patch remains exactly where it was.
        grip_box = [tx - 3, ty - 3, tx + 4, ty + 4]
        x0, y0, x1, y1 = grip_box
        grip_diff = int(np.any(n[y0:y1, x0:x1] != baseline[y0:y1, x0:x1], axis=2).sum())
        if grip_diff:
            raise ValueError(f"The already fitted grip moved for {slot}: {grip_diff}")
        # Count separated shoe silhouettes below the gown. This catches the
        # extra boot in the old fitted frame, rather than only checking soles.
        foot = b[520:, :, 3] > 128
        labels, _ = ndimage.label(foot, np.ones((3, 3)))
        sizes = np.bincount(labels.ravel())[1:]
        shoe_components = int((sizes > 8).sum())
        if shoe_components != 2:
            raise ValueError(f"Expected two drawn boot silhouettes for {slot}, got {shoe_components}")
        metrics.append(dict(slot=slot, user_frame=slot+1, original_render_max_rgba_difference=baseline_error,
                            protected_hd_pixels=int(protected.sum()), protected_hd_max_rgba_difference=0,
                            lower_hd_max_rgba_difference=0, lower_native_max_rgba_difference=0,
                            grip_roi=grip_box, grip_changed_pixels=grip_diff, boot_components=shoe_components,
                            original_hd_sha256=sha(BEFORE / f"hd/{slot:04d}.png"),
                            output_hdfit_sha256=sha(STAGED / f"hdfit/{slot:04d}.png"),
                            output_native_sha256=sha(STAGED / f"native_frames/{slot:04d}.png")))
        raws.append(raw); fits.append(fit); results.append(result)
    make_contact(raws, fits, results, WORK / "before_after_contact.png")
    if apply:
        for slot in SLOTS:
            for name, target in (("hdfit", FOLDER / f"hdfit/{slot:04d}.png"),
                                  ("native_frames", P.out / f"native_frames/{slot:04d}.png")):
                temporary = target.with_suffix(".local-hand.tmp")
                shutil.copyfile(STAGED / name / target.name, temporary)
                temporary.replace(target)
    result_report = dict(applied=apply, clip=CLIP, slots=list(SLOTS), alpha_blending="premultiplied RGBA replacement",
                         palette=PALETTE.relative_to(ROOT).as_posix(), selection_unchanged=True,
                         original_hd_unchanged=True, installed=False, frames=metrics)
    (WORK / "repair_report.json").write_text(json.dumps(result_report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(result_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    prepare(parser.parse_args().apply)
