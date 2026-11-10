"""Targeted clap/standing/walk placement fixes for the Claude workbench.

Prepare by default; --apply writes only native slots 10-20 and 68-75 and the
corresponding selection offsets. Original inputs are versioned under validation.
No global final, palette rebuild, image generation, NPK build or game writes.
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
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
os.environ["PATCH_ID"] = "claude_gunner"
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit import art
from kit.config import P
from kit.source import layer_world

WORK = ROOT / "output/validation/claude_motion_review_2026-11-09/alignment"
BEFORE = WORK / "before"
STAGED = WORK / "staged"
CLIPS = {"clap": (10, 13), "stand": (14, 20), "walk": (68, 75)}
CONFIG = ROOT / "design/claude_gunner/motion_alignment.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8"))


def rgba(path):
    return Image.open(path).convert("RGBA")


def smooth(value):
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def translated(image, delta):
    result = Image.new("RGBA", image.size)
    result.paste(image, tuple(delta))
    return result


def fixed_box(image, reference, box):
    image.paste(reference.crop(tuple(box)), tuple(box[:2]))


def render_hd(hd, row, report, palette):
    if row.get("hands"):
        raise ValueError("This placement repair expects empty hand-fit lists")
    size = round(report["window"][2] * row["scale"])
    color, alpha = art.downscale(hd, (size, size))
    sprite = art.finish(art.sharpen(art.grade(color)), alpha, palette)
    left, top = art.placement(report["window"], row["scale"],
                              row["offset"][0] + row["track"][0],
                              row["offset"][1] + row["track"][1])
    world = Image.new("RGBA", (P.canvas + 400, P.canvas + 400))
    world.paste(sprite, (left + 200, top + 200))
    return world.crop((200, 200, P.canvas + 200, P.canvas + 200))


def planted_side(hd, row, report, spec, delta):
    """Correct the planted side, with a fixed upper-body root and other foot.

    The original clap leans in above a planted right foot; moving the whole
    image would remove that action. One smooth inverse warp narrows only the
    displaced side below the waist. Premultiplied sampling avoids edge ghosts.
    """
    if not delta:
        return hd.copy(), {"max_displacement_px": 0.0, "min_inverse_jacobian": 1.0}
    arr = np.asarray(hd, np.float32)
    h, w = arr.shape[:2]
    side = round(report["window"][2] * row["scale"])
    k = side / w
    left, top = art.placement(report["window"], row["scale"], *row["offset"])
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    world_x, world_y = left + xx * k, top + yy * k
    other = spec["other_foot_center_x"][str(row["slot"])]
    vertical = smooth((world_y - spec["lower_body_root_y"]) /
                      (spec["fully_planted_y"] - spec["lower_body_root_y"]))
    horizontal = smooth((other - world_x) / (other - 207))
    dx = delta * vertical * horizontal / k
    premultiplied = arr.copy()
    premultiplied[..., :3] *= arr[..., 3:] / 255
    out = np.stack([ndimage.map_coordinates(premultiplied[..., c], [yy, xx - dx],
                                           order=1, mode="constant", cval=0)
                    for c in range(4)], axis=2)
    out[..., :3] /= np.maximum(out[..., 3:] / 255, 1e-3)
    active = np.abs(dx) > 0.001
    result = np.where(active[..., None], out, arr)
    jacobian = 1 - np.gradient(dx, axis=1)
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), "RGBA"), {
        "max_displacement_px": float(dx.max() * k),
        "min_inverse_jacobian": float(jacobian.min()),
    }


def registration(reference, moving, y0, y1, reach=8):
    a = np.asarray(reference)[y0:y1].astype(np.int32)
    bfull = np.asarray(moving).astype(np.int32)
    best, cost = (0, 0), float("inf")
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            b = np.roll(np.roll(bfull, dy, 0), dx, 1)[y0:y1]
            solid = (a[..., 3] > 128) | (b[..., 3] > 128)
            value = (np.abs(a - b).max(2) * solid).sum() / max(solid.sum(), 1)
            value += 0.5 * (abs(dx) + abs(dy))
            if value < cost:
                best, cost = (dx, dy), value
    return best


def make_evidence(name, slots, images):
    crop, scale = (175, 190, 305, 350), 2
    cw, ch = 260, 320
    board = Image.new("RGB", (len(slots) * cw, 3 * (ch + 25)), (64, 73, 90))
    draw = ImageDraw.Draw(board)
    for j, slot in enumerate(slots):
        for r, image in enumerate((rgba(WORK / f"source/{slot:04d}.png"),
                                   rgba(BEFORE / f"native_frames/{slot:04d}.png"), images[slot])):
            part = image.crop(crop).resize((cw, ch), Image.Resampling.NEAREST)
            board.paste(part, (j * cw, 25 + r * (ch + 25)), part)
            draw.text((j * cw + 4, r * (ch + 25) + 4),
                      f"{slot+1} " + ("original", "before", "fixed")[r], fill="white")
    board.save(WORK / f"{name}_after_contact.png")
    animation = []
    for slot in slots:
        part = images[slot].crop(crop)
        background = Image.new("RGBA", part.size, (64, 73, 90, 255))
        background.alpha_composite(part)
        animation.append(background.convert("RGB").resize((260, 320), Image.Resampling.NEAREST))
    animation[0].save(WORK / f"{name}_fixed.gif", save_all=True,
                      append_images=animation[1:], duration=100, loop=0)


def prepare(apply=False):
    cfg = read(CONFIG)
    if not (BEFORE / "snapshot.json").exists():
        raise ValueError("Capture the read-only pre-repair snapshot before preparing the repair")
    palette = Image.open(ROOT / "output/validation/claude_idle_feet_fix/palette_original.png").copy()
    (STAGED / "native_frames").mkdir(parents=True, exist_ok=True)
    images, hd_images, reports, metrics = {}, {}, {}, {}
    for name, (a, b) in CLIPS.items():
        ident = f"clip_{a:03d}_{b:03d}"
        report = read(BEFORE / f"clips/{ident}/selection.json")
        spec = cfg[name]
        reference = rgba(BEFORE / f"native_frames/{spec['reference']:04d}.png")
        motion = []
        for row in report["frames"]:
            slot = row["slot"]
            old = rgba(BEFORE / f"native_frames/{slot:04d}.png")
            if name == "clap":
                hd = rgba(BEFORE / f"clips/{ident}/hd/{slot:04d}.png")
                reproduced = render_hd(hd, row, report, palette)
                np.testing.assert_array_equal(np.asarray(reproduced), np.asarray(old))
                new_hd, field = planted_side(hd, row, report, spec, spec["corrections_px"][str(slot)])
                image = render_hd(new_hd, row, report, palette)
                fixed_box(image, reference, spec["fixed_native_foot_box"])
                hd_images[slot] = new_hd
                motion.append({"frame": slot, **field})
            else:
                delta = spec["translation_px"][str(slot)]
                image = translated(old, delta)
                if name == "stand":
                    for box in spec["fixed_native_foot_boxes"]:
                        fixed_box(image, reference, box)
                for key in ("offset", "offset_before_ground"):
                    if key in row:
                        row[key] = [row[key][0] + delta[0], row[key][1] + delta[1]]
                motion.append({"frame": slot, "translation_px": delta})
            images[slot] = image
            image.save(STAGED / f"native_frames/{slot:04d}.png")
        reports[ident] = report
        target = STAGED / "clips" / ident
        target.mkdir(parents=True, exist_ok=True)
        (target / "selection.json").write_text(json.dumps(report, indent=1) + "\n", "utf-8")
        if name == "clap":
            (target / "hd").mkdir(exist_ok=True)
            for slot in range(a, b + 1):
                hd_images[slot].save(target / f"hd/{slot:04d}.png")
            box = spec["fixed_native_foot_box"]
            x0, y0, x1, y1 = box
            fixed_difference = max(int(np.abs(np.asarray(images[k])[y0:y1, x0:x1].astype(np.int16)
                                                 - np.asarray(reference)[y0:y1, x0:x1].astype(np.int16)).max())
                                   for k in range(a, b + 1))
            metrics[name] = {"fixed_boot_max_rgba_difference": fixed_difference, "local_fields": motion}
        elif name == "stand":
            fixed_difference = 0
            for box in spec["fixed_native_foot_boxes"]:
                x0, y0, x1, y1 = box
                for slot in range(a, b + 1):
                    fixed_difference = max(fixed_difference, int(np.abs(np.asarray(images[slot])[y0:y1, x0:x1].astype(np.int16)
                                                                                 - np.asarray(reference)[y0:y1, x0:x1].astype(np.int16)).max()))
            metrics[name] = {"both_boots_max_rgba_difference": fixed_difference, "translations": motion}
        else:
            official = {slot: layer_world(P.body, slot) for slot in range(a, b + 1)}
            ys = np.where(np.asarray(official[a])[..., 3].any(axis=1))[0]
            source_band = (int(ys.min()), int(ys.min()) + 16)
            ys = np.where(np.asarray(reference)[..., 3].any(axis=1))[0]
            drawn_band = (int(ys.min()), int(ys.min()) + 24)
            source_motion = [registration(official[a], official[k], *source_band) for k in range(a, b + 1)]
            old_motion = [registration(reference, rgba(BEFORE / f"native_frames/{k:04d}.png"), *drawn_band) for k in range(a, b + 1)]
            new_motion = [registration(images[a], images[k], *drawn_band) for k in range(a, b + 1)]
            metrics[name] = dict(source_head_registration=source_motion, before_head_registration=old_motion,
                                 after_head_registration=new_motion, translations=motion,
                                 head_template_source_band=source_band, head_template_drawn_band=drawn_band,
                                 max_registration_residual_px=max(max(abs(x-y) for x,y in zip(u,v)) for u,v in zip(source_motion,new_motion)))
        make_evidence(name, list(range(a, b + 1)), images)
    if metrics["clap"]["fixed_boot_max_rgba_difference"] or metrics["stand"]["both_boots_max_rgba_difference"]:
        raise ValueError("Planted shoes must be pixel-identical")
    if metrics["walk"]["max_registration_residual_px"] > 1:
        raise ValueError("Walk head motion still differs from the official head band")
    if apply:
        for slot, image in images.items():
            target = P.out / f"native_frames/{slot:04d}.png"
            temporary = target.with_suffix(".alignment.tmp")
            shutil.copyfile(STAGED / f"native_frames/{slot:04d}.png", temporary)
            temporary.replace(target)
        for ident, report in reports.items():
            if ident != "clip_010_013":
                target = P.out / f"clips/{ident}/selection.json"
                target.write_text(json.dumps(report, indent=1) + "\n", "utf-8")
        for slot in hd_images:
            # Keep repaired lower-body geometry in its HD source as well. The
            # explicit fixed native foot recipe is re-applied after downscale.
            shutil.copyfile(STAGED / f"clips/clip_010_013/hd/{slot:04d}.png",
                            P.out / f"clips/clip_010_013/hd/{slot:04d}.png")
        clips_path = P.run / "clips.json"
        clips_data = read(clips_path)
        for clip in clips_data["clips"]:
            if clip["start"] == 68:
                clip["anchor"] = "head"
                clip["anchor_px"] = 24
        text = json.dumps(clips_data, ensure_ascii=False, indent=1) + "\n"
        if b"\r\n" in clips_path.read_bytes():
            text = text.replace("\n", "\r\n")
        clips_path.write_bytes(text.encode("utf-8"))
    result = dict(applied=apply, tool_frames=sorted(images), changes=metrics, installed=False,
                  native_sha256={str(slot): digest(STAGED / f"native_frames/{slot:04d}.png") for slot in images},
                  note="Only these 19 native frames are published. Other concurrent workers own their separate actions.")
    (WORK / "repair_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    prepare(parser.parse_args().apply)
