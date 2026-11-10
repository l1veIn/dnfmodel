"""Prepare/apply Claude's four-frame idle with planted ankles and boots.

Uses the approved reload cell and existing micro renderer. No image generation,
NPK build, game writes, or changes to other actions. Review staged output first;
--apply publishes only these four HD/native frames to the workbench's source.
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

ROOT = Path(__file__).resolve().parents[1]
os.environ["PATCH_ID"] = "claude_gunner"
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit import art, sheets
from kit.config import P

CLIP = "clip_000_003"
WORK = ROOT / "output/validation/claude_idle_feet_fix"
BEFORE = WORK / "before"
STAGED = WORK / "staged"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    if (BEFORE / "snapshot.json").exists():
        return
    for sub in ("native_frames", "hd"):
        (BEFORE / sub).mkdir(parents=True, exist_ok=True)
    hashes = {p.relative_to(ROOT).as_posix(): sha(p)
              for p in sorted((P.out / "native_frames").glob("*.png"))}
    for k in range(4):
        shutil.copy2(P.out / f"native_frames/{k:04d}.png", BEFORE / f"native_frames/{k:04d}.png")
        shutil.copy2(P.out / f"clips/{CLIP}/hd/{k:04d}.png", BEFORE / f"hd/{k:04d}.png")
    shutil.copy2(P.out / f"clips/{CLIP}/selection.json", BEFORE / "selection.json")
    shutil.copy2(P.run / "pose_sheets.json", BEFORE / "pose_sheets.json")
    (BEFORE / "snapshot.json").write_text(json.dumps({"native_file_sha256": hashes}, indent=2) + "\n", "utf-8")


def original_palette():
    """Recover the old global palette before hand fitting, once, then freeze it.

    The original full final pass sampled HD before creating hdfit. Sampling
    today's hdfit instead changes colors even when the pose is unmodified.
    """
    path = WORK / "palette_original.png"
    if path.exists():
        return Image.open(path).copy()
    samples = []
    for clip in P.clips():
        folder = P.out / "clips" / clip["id"]
        if not (folder / "selection.json").exists():
            continue
        report = json.loads((folder / "selection.json").read_text("utf-8"))
        for row in report["frames"][::3]:
            source = BEFORE / f"hd/{row['slot']:04d}.png" if clip["id"] == CLIP else folder / f"hd/{row['slot']:04d}.png"
            hd = Image.open(source).convert("RGBA")
            size = round(report["window"][2] * row["scale"])
            color, alpha = art.downscale(hd, (size, size))
            samples.append((art.sharpen(art.grade(color)), alpha))
    palette = art.build_palette(samples, 96)
    saved = Image.new("P", (1, 1))
    saved.putpalette(palette.getpalette())
    saved.save(path)
    return saved


def native(hd, row, report, palette):
    if row.get("hands"):
        raise ValueError("Idle repair expects the existing empty hand-fit list")
    size = round(report["window"][2] * row["scale"])
    color, alpha = art.downscale(hd, (size, size))
    sprite = art.finish(art.sharpen(art.grade(color)), alpha, palette)
    left, top = art.placement(report["window"], row["scale"],
                               row["offset"][0] + row["track"][0],
                               row["offset"][1] + row["track"][1])
    # Same placement as process.render_clip; generous padding also handles
    # poses extending beyond the final canvas without changing the crop.
    world = Image.new("RGBA", (P.canvas + 400, P.canvas + 400))
    world.paste(sprite, (left + 200, top + 200))
    return world.crop((200, 200, 200 + P.canvas, 200 + P.canvas))


def contact(frames, path, crop, factor, label):
    w, h = (crop[2] - crop[0]) * factor, (crop[3] - crop[1]) * factor
    board = Image.new("RGB", (4 * (w + 16), h + 40), (47, 53, 65))
    draw = ImageDraw.Draw(board)
    for k, frame in enumerate(frames):
        draw.text((k * (w + 16) + 8, 10), f"{label} {k+1}", fill="white")
        part = frame.crop(crop).resize((w, h), Image.Resampling.NEAREST)
        board.paste(part, (k * (w + 16) + 8, 32), part)
    board.save(path)


def prepare(apply=False):
    snapshot()
    report = json.loads((BEFORE / "selection.json").read_text("utf-8"))
    current_report = P.out / f"clips/{CLIP}/selection.json"
    if current_report.read_bytes() != (BEFORE / "selection.json").read_bytes():
        raise ValueError("Idle placement changed since the repair snapshot")
    palette = original_palette()
    baseline = []
    for row in report["frames"]:
        k = row["slot"]
        old = np.asarray(Image.open(BEFORE / f"native_frames/{k:04d}.png").convert("RGBA"))
        reproduced = np.asarray(native(Image.open(BEFORE / f"hd/{k:04d}.png").convert("RGBA"), row, report, palette))
        baseline.append(int(np.abs(old.astype(np.int16) - reproduced.astype(np.int16)).max()))
    if any(baseline):
        raise ValueError(f"Original render/color reproduction failed: {baseline}")

    layout = sheets.load("reload")
    entries = layout["clips"][CLIP]
    if any("phase" in entry for entry in entries):
        raise ValueError("Replace the old phase entries with explicit planted micro controls first")
    raw = Image.open(P.parts / "raw/poses_reload_v1_0.png").convert("RGB")
    cell_w, cell_h = raw.width // layout["cols"], raw.height // layout["rows"]
    side = max(cell_w, cell_h)
    source = Image.new("RGBA", (side, side))
    source.paste(art.matte(raw.crop((0, 0, cell_w, cell_h))), (0, 0))
    per_world = layout["zoom"] * (raw.width / layout["width"]) / report["base_scale"]
    box = source.getchannel("A").getbbox()
    lock_y = int(np.ceil(box[1] + 0.86 * (box[3] - box[1])))
    hd_frames, frames = [], []
    for sub in ("hd", "native_frames"):
        (STAGED / sub).mkdir(parents=True, exist_ok=True)
    for row, entry in zip(report["frames"], entries):
        k = row["slot"]
        if entry["slot"] != k or entry["cell"] != 0:
            raise ValueError("Expected the same approved first cell for all four idle frames")
        hd = sheets.micro(source, layout["micro"][str(k)], per_world)
        np.testing.assert_array_equal(np.asarray(hd)[lock_y:], np.asarray(source)[lock_y:])
        image = native(hd, row, report, palette)
        hd.save(STAGED / f"hd/{k:04d}.png")
        image.save(STAGED / f"native_frames/{k:04d}.png")
        hd_frames.append(hd)
        frames.append(image)
    fixed = [np.asarray(frame)[323:339, 220:265] for frame in frames]
    old_fixed = np.asarray(Image.open(BEFORE / "native_frames/0000.png").convert("RGBA"))[323:339, 220:265]
    for area in fixed:
        np.testing.assert_array_equal(area, old_fixed)
    differences = [int(np.any(np.asarray(frames[k]) != np.asarray(frames[(k+1) % 4]), axis=2).sum()) for k in range(4)]
    if min(differences) < 50:
        raise ValueError("The idle must retain visible local motion in each transition")
    snapshot_data = json.loads((BEFORE / "snapshot.json").read_text("utf-8"))
    # Other actions may have received later approved repairs. Protect their
    # current bytes during this invocation, rather than freezing them forever
    # at the date of the first idle repair.
    others = {p: sha(ROOT / p) for p in snapshot_data["native_file_sha256"]
              if int(Path(p).stem) not in range(4)}
    contact(frames, WORK / "after_full.png", (205, 200, 275, 345), 3, "Fixed frame")
    contact(frames, WORK / "after_feet.png", (220, 318, 265, 340), 6, "Fixed feet")
    contact(hd_frames, WORK / "after_hd_feet.png", (215, 475, 305, 546), 3, "Fixed HD")
    animated = []
    for frame in frames:
        part = frame.crop((205, 200, 275, 345))
        bg = Image.new("RGBA", part.size, (68, 76, 94, 255))
        bg.alpha_composite(part)
        animated.append(bg.convert("RGB").resize((210, 435), Image.Resampling.NEAREST))
    animated[0].save(WORK / "idle_fixed.gif", save_all=True, append_images=animated[1:], duration=100, loop=0)
    applied = False
    if apply:
        for k in range(4):
            for sub, dest in (("hd", P.out / f"clips/{CLIP}/hd"), ("native_frames", P.out / "native_frames")):
                source_path, target = STAGED / sub / f"{k:04d}.png", dest / f"{k:04d}.png"
                temporary = target.with_suffix(".idle-fix.tmp")
                shutil.copyfile(source_path, temporary)
                temporary.replace(target)
        applied = True
    if any(sha(ROOT / p) != digest for p, digest in others.items()):
        raise ValueError("Another character frame changed during this repair")
    result = dict(applied=applied, frames=[0, 1, 2, 3], original_render_max_rgba_difference=baseline,
                  native_fixed_roi=[220, 323, 265, 339], fixed_roi_max_rgba_difference=0,
                  hd_fixed_from_y=lock_y, source_bbox=list(box), per_world=per_world,
                  neighbouring_changed_pixels=differences, unchanged_other_frames=len(others),
                  palette="palette_original.png", selection_unchanged=True, installed=False,
                  native_sha256=[sha(STAGED / f"native_frames/{k:04d}.png") for k in range(4)])
    (WORK / "repair_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    prepare(parser.parse_args().apply)
