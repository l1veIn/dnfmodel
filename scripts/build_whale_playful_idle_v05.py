"""Cut a genuinely drawn four-pose sheet into one shared game-world registration.

Writes only output/whale_playful_idle_v05/{reference,candidate*,freeze.json}.
The caller owns art/, prompts and generation_record.json. No image-generation,
old-body graft, mesh warp, release build, project-pointer or game write occurs.
"""
from __future__ import annotations

import argparse
from datetime import datetime
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
WORK = ROOT / "output/whale_playful_idle_v05"
BASE = ROOT / "output/fatfish_whale_maid_v04"
PALETTE = ROOT / "output/whale_stand_redraw_v04/palette_original.png"
SLOTS = [10, 11, 12, 13]
os.environ["PATCH_ID"] = "fatfish_whale_maid"
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit import art


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def native_records():
    return {p.name: dict(sha256=sha(p), mtime_ns=p.stat().st_mtime_ns)
            for p in sorted((BASE / "native_frames").glob("*.png"))}


def make_board(rows, labels, crop, target, factor=4):
    w, h = crop[2] - crop[0], crop[3] - crop[1]
    output = Image.new("RGB", (4 * (w * factor + 16), len(rows) * (h * factor + 28)), (49, 56, 70))
    draw = ImageDraw.Draw(output)
    for y, (row, label) in enumerate(zip(rows, labels)):
        for x, frame in enumerate(row):
            ox, oy = x * (w * factor + 16) + 8, y * (h * factor + 28)
            draw.text((ox, oy + 4), f"{label}: tool{SLOTS[x]}", fill="white")
            piece = frame.crop(crop).resize((w * factor, h * factor), Image.Resampling.NEAREST)
            output.paste(piece, (ox, oy + 24), piece)
    output.save(target)


def loop(frames, crop, target, factor=1, duration=300):
    sequence = []
    for image in frames:
        frame = image.crop(crop)
        canvas = Image.new("RGBA", frame.size, (49, 56, 70, 255))
        canvas.alpha_composite(frame)
        sequence.append(canvas.convert("RGB").resize((canvas.width * factor, canvas.height * factor), Image.Resampling.NEAREST))
    sequence[0].save(target, save_all=True, append_images=sequence[1:], duration=duration, loop=0, lossless=True)


def region_landmarks(frames):
    """Absolute fixed-world ROI measurements, never a best-shift alignment."""
    regions = {
        "face_skin": [245, 298, 265, 314],
        "near_shoulder_gold_cross": [242, 309, 249, 320],
        "white_upper_bodice": [249, 316, 262, 325],
        "shoe_soles": [232, 375, 273, 391],
        "short_tail": [220, 333, 237, 346],
    }
    result = {}
    for name, (x0, y0, x1, y1) in regions.items():
        records = []
        for slot, frame in zip(SLOTS, frames):
            pixels = np.asarray(frame)[y0:y1, x0:x1]
            rgb = pixels[..., :3].astype(np.int16)
            r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
            visible = pixels[..., 3] > 0
            if name == "face_skin":
                visible &= (r > g + 12) & (g > b + 3) & (r > 170)
            elif name == "near_shoulder_gold_cross":
                visible &= (r > 145) & (g > 90) & (b < 130) & (r > g + 3) & (g > b + 15)
            elif name == "white_upper_bodice":
                visible &= (r > 160) & (g > 160) & (b > 160)
            elif name == "shoe_soles":
                visible &= (b > r + 8) & (b > g + 2) & (r < 150)
            yy, xx = np.where(visible)
            row = dict(slot=slot, opaque_feature_pixels=int(visible.sum()))
            if len(xx):
                row.update(bbox=[int(xx.min() + x0), int(yy.min() + y0), int(xx.max() + x0 + 1), int(yy.max() + y0 + 1)],
                           centroid=[float(xx.mean() + x0), float(yy.mean() + y0)])
                bottom = yy.max()
                row["lowest_feature_row"] = int(bottom + y0)
                row["bottom_row_x_span"] = [int(xx[yy == bottom].min() + x0), int(xx[yy == bottom].max() + x0)]
            records.append(row)
        if all("centroid" in row for row in records):
            base = records[0]["centroid"]
            for row in records:
                row["centroid_delta_from_neutral"] = [round(v - u, 4) for v, u in zip(row["centroid"], base)]
        result[name] = dict(roi=[x0, y0, x1, y1], frames=records)
    return dict(method="Fixed-world feature masks and absolute coordinates; geometric proxies only, not claimed skeletal pivots", regions=result,
                alpha_bboxes={str(slot): list(frame.getbbox()) for slot, frame in zip(SLOTS, frames)})


def reference():
    folder = WORK / "reference"
    folder.mkdir(parents=True, exist_ok=True)
    slots = [0, 9, 14, 17]
    images = [Image.open(BASE / f"native_frames/{k:04d}.png").convert("RGBA") for k in slots]
    make_board([images], ["accepted-scale reference"], (210, 280, 295, 398), folder / "accepted_scale_contact.png", 5)
    records = native_records()
    assert len(records) == 174
    save(folder / "native_baseline.json", dict(
        source=rel(BASE / "native_frames"), frames=records,
        scale_samples={str(k): list(im.getbbox()) for k, im in zip(slots, images)},
        note="Read-only scale references; no old figure pixels enter the new idle.",
    ))
    print(json.dumps(dict(reference=rel(folder), native_baseline=174)))


def prepare(args):
    sheet = args.sheet.resolve(strict=True)
    assert sheet.is_relative_to(WORK / "art"), "The parent-owned source must be under art/"
    candidate = WORK / args.candidate
    assert candidate.parent == WORK and candidate.name.startswith("candidate")
    assert not candidate.exists(), "Use a sibling candidate instead of overwriting reviewed art"
    before = native_records()
    assert len(before) == 174
    source = Image.open(sheet).convert("RGBA")
    assert np.mean(np.asarray(source)[..., 3] == 0) > .1, "Expected real transparent gutters"
    base_cell = max(round(source.width / 2), round(source.height / 2))
    step_x = args.grid_step_x if args.grid_step_x is not None else source.width / 2
    step_y = args.grid_step_y if args.grid_step_y is not None else source.height / 2
    cell = base_cell + args.overscan * 2
    equal_split = []
    for index in range(4):
        bounds = [round(index % 2 * source.width / 2), round(index // 2 * source.height / 2),
                  round((index % 2 + 1) * source.width / 2), round((index // 2 + 1) * source.height / 2)]
        pixels = np.asarray(source.crop(bounds))
        labels, count = ndimage.label(pixels[..., 3] > 24, structure=np.ones((3, 3)))
        counts = np.bincount(labels.ravel()); counts[0] = 0
        main = labels == int(counts.argmax())
        equal_split.append(dict(source_cell=bounds, main_alpha_bbox=list(Image.fromarray(main.astype("uint8") * 255).getbbox())))
    size, left, top = args.size, args.left, args.top
    assert 0 <= left < left + size <= 500 and 0 <= top < top + size <= 500
    nd = candidate / "native_frames"
    hdroot = candidate / "clips/clip_010_013/hd"
    nd.mkdir(parents=True)
    hdroot.mkdir(parents=True)
    review = candidate / "review"
    review.mkdir()
    palette = Image.open(PALETTE).copy()
    selected = load(BASE / "clips/clip_010_013/selection.json")
    selected.pop("action_repair_source", None)
    scale = size / selected["window"][2]
    px, py = art.placement(selected["window"], scale)
    offset = [left - px, top - py]
    selected.update(sheet=f"whale_playful_idle_v05:{sheet.stem}", base_scale=scale,
                    redraw_source=rel(sheet), redraw_method="Newly drawn four-phase playful breathing idle; one complete-cell transform and no per-cell bbox fitting.")
    frames, records, segmented = [], [], []
    for index, slot in enumerate(SLOTS):
        x, y = round(index % 2 * step_x) - args.overscan, round(index // 2 * step_y) - args.overscan
        box = [x, y, x + cell, y + cell]
        pixels = np.asarray(source.crop(box)).copy()
        labels, count = ndimage.label(pixels[..., 3] > 24, structure=np.ones((3, 3)))
        assert count > 0
        counts = np.bincount(labels.ravel())
        counts[0] = 0
        main = labels == int(counts.argmax())
        support = ndimage.distance_transform_edt(~main) <= 2
        removed = int(np.sum((~support) & (pixels[..., 3] > 0)))
        pixels[~support] = 0
        hd = Image.fromarray(pixels, "RGBA")
        hd.save(hdroot / f"{slot:04d}.png")
        segmented.append(hd)
        color, alpha = art.downscale(hd, (size, size))
        sprite = art.finish(art.sharpen(art.grade(color)), alpha, palette)
        world = Image.new("RGBA", (500, 500))
        world.paste(sprite, (left, top))
        frames.append(world)
        selected["frames"][index].update(
            slot=slot, video_frame=f"whale_playful_idle_v05:phase{index + 1}",
            scale=scale, offset=offset, track=[0, 0], offset_before_ground=offset,
            hands=[], score=None, action_redraw_v05=dict(source=rel(sheet), cell=index,
                new_drawn_body=True, original_motion_match_required=False),
        )
        records.append(dict(slot=slot, user_frame=slot + 1, source_cell=box,
                            source_pose=index + 1, removed_external_alpha_pixels=removed,
                            segmented_hd_bbox=list(hd.getbbox()), hd=rel(hdroot / f"{slot:04d}.png")))
    raw_frames = [image.copy() for image in frames]
    rois = args.foot_roi or []
    mask = np.zeros((500, 500), bool)
    for x0, y0, x1, y1 in rois:
        assert 0 <= x0 < x1 <= 500 and 0 <= y0 < y1 <= 500
        mask[y0:y1, x0:x1] = True
    hd_support_rois = []
    hd_support_mask = np.zeros((cell, cell), bool)
    if rois:
        before_hd = candidate / "hd_before_support"
        before_hd.mkdir()
        for x0, y0, x1, y1 in rois:
            hx0 = max(0, int(np.floor((x0 - left) * cell / size)))
            hy0 = max(0, int(np.floor((y0 - top) * cell / size)))
            hx1 = min(cell, int(np.ceil((x1 - left) * cell / size)))
            hy1 = min(cell, int(np.ceil((y1 - top) * cell / size)))
            assert hx0 < hx1 and hy0 < hy1
            hd_support_rois.append([hx0, hy0, hx1, hy1])
            hd_support_mask[hy0:hy1, hx0:hx1] = True
        neutral_hd = np.asarray(segmented[0])
        for slot, hd, record in zip(SLOTS, segmented, records):
            original = np.asarray(hd)
            pixels = original.copy()
            saved_before = before_hd / f"{slot:04d}.png"
            hd.save(saved_before)
            pixels[hd_support_mask] = neutral_hd[hd_support_mask]
            assert np.array_equal(pixels[~hd_support_mask], original[~hd_support_mask])
            Image.fromarray(pixels, "RGBA").save(ROOT / record["hd"])
            record.update(hd_before_support=rel(saved_before), hd_before_support_sha256=sha(saved_before),
                          hd_support_outside_changed_pixels=0)
        Image.fromarray((mask * 255).astype("uint8")).save(candidate / "native_support_mask.png")
        Image.fromarray((hd_support_mask * 255).astype("uint8")).save(candidate / "hd_support_mask.png")
    canonical = np.asarray(frames[0])
    outside, changed = [], []
    for slot, image, record in zip(SLOTS, frames, records):
        pixels = np.asarray(image).copy()
        raw = pixels.copy()
        pixels[mask] = canonical[mask]
        result = Image.fromarray(pixels, "RGBA")
        path = nd / f"{slot:04d}.png"
        result.save(path)
        frames[slot - 10] = result
        outside.append(int(np.sum(np.any(pixels[~mask] != raw[~mask], axis=1))))
        changed.append(int(np.sum(np.any(pixels != raw, axis=2))))
        record.update(native=rel(path), native_sha256=sha(path), hd_sha256=sha(ROOT / record["hd"]),
                      native_bbox=list(result.getbbox()))
    assert not any(outside)
    selected["native_postprocess"] = dict(
        source="Only the newly drawn neutral tool10, never old figure pixels",
        fixed_new_neutral_rois=rois, changed_pixels=changed, outside_roi_changed_pixels=outside,
        matching_hd_support_rois=hd_support_rois,
        reconstruction="Render each saved HD-before-support with the frozen render settings, then replace only declared native ROI from the same new neutral. HD is separately held in the corresponding neutral foot ROI; native remains authoritative after pixel support hold.",
        native_is_authoritative=True,
    )
    save(candidate / "clips/clip_010_013/selection.json", selected)
    old = [Image.open(BASE / f"native_frames/{k:04d}.png").convert("RGBA") for k in SLOTS]
    bboxes = [image.getbbox() for image in old + frames]
    crop = (min(box[0] for box in bboxes) - 5, min(box[1] for box in bboxes) - 5,
            max(box[2] for box in bboxes) + 5, max(box[3] for box in bboxes) + 5)
    make_board([old, frames], ["previous v04", "original playful idle"], crop, review / "whole_body_comparison.png", 5)
    make_board([raw_frames, frames], ["new draw before support hold", "new draw with chosen holds"], (left, max(top, 355), left + size, top + size), review / "feet_comparison.png", 6)
    loop(frames, crop, review / "idle_native.webp", 1, args.duration)
    loop(frames, crop, review / "idle_x4.webp", 4, args.duration)
    make_board([frames], ["shoulder bodice head fixed world"], (230, 294, 270, 345), review / "shoulder_chest_head_close.png", 9)
    make_board([frames], ["shoe support fixed world"], (232, 365, 273, 393), review / "shoe_support_close.png", 10)
    save(candidate / "absolute_landmarks.json", region_landmarks(frames))
    settings = dict(grade=art.P.grade, ink=[float(v) for v in art.INK],
                    line_keep=.45, sharpen_amount=.55, alpha_cut=.42, outline=True,
                    palette=dict(path=rel(PALETTE), sha256=sha(PALETTE)),
                    config_ident="fatfish_whale_maid", mutable_patch_pointer_not_a_frozen_dependency=True)
    save(candidate / "render_settings.json", settings)
    after = native_records()
    assert before == after, "Original complete v04 source must stay byte/mtime exact"
    save(candidate / "manifest.json", dict(
        status="prepared_for_root_visual_review", created_at=datetime.now().astimezone().isoformat(),
        user_request="Original small playful breathing idle inspired by the DeepSeek whale maid identity",
        slots=SLOTS, frames=records, source_sheet=rel(sheet), source_sheet_sha256=sha(sheet),
        source_layout=dict(sheet_size=list(source.size), equal_split_diagnostics=equal_split,
                           fixed_grid_step=[step_x, step_y], base_square_side=base_cell, uniform_overscan=args.overscan,
                           extraction_boxes=[record["source_cell"] for record in records],
                           rationale="Root-authorized shared sheet-layout calibration: actual two-column packing is550px rather than width/2; same column step applies in both rows, no per-frame bbox fit. Uniform overscan retains looped ahoge crossing the row boundary."),
        common_transform=dict(cell_size=[cell, cell], native_size=[size, size], world_offset=[left, top], canvas=[500, 500]),
        one_common_affine=True, per_cell_bbox_fit=False, old_body_pixels_used=False,
        palette=dict(path=rel(PALETTE), sha256=sha(PALETTE)),
        render_settings=rel(candidate / "render_settings.json"), render_settings_sha256=sha(candidate / "render_settings.json"),
        native_postprocess=selected["native_postprocess"],
        source_native_baseline=before, source_native_unchanged=True,
        selection=rel(candidate / "clips/clip_010_013/selection.json"),
        selection_sha256=sha(candidate / "clips/clip_010_013/selection.json"),
        preview_frame_duration_ms=args.duration, preview_timing_is_not_ingame_ani=True,
        loop_frame_order=[10, 11, 12, 13, 10], absolute_landmarks=rel(candidate / "absolute_landmarks.json"),
        installed=False, user_aesthetic_approved=False, new_65535_calls=0,
    ))
    print(json.dumps(dict(candidate=rel(candidate), common_size=size, world=[left, top],
                          fixed_new_neutral_rois=rois, outside_roi_changes=outside,
                          native_bboxes=[r["native_bbox"] for r in records]), ensure_ascii=False))


def freeze(args):
    assert args.approved, "Root must first review the exact full-body and native animation candidate"
    target = WORK / "freeze.json"
    assert not target.exists(), "Do not overwrite a frozen candidate"
    candidate = WORK / args.candidate
    assert candidate.parent == WORK and candidate.name.startswith("candidate")
    manifest = load(candidate / "manifest.json")
    assert manifest["source_native_baseline"] == native_records()
    paths = [p for p in candidate.rglob("*") if p.is_file()]
    paths += [p for p in (WORK / "art").rglob("*") if p.is_file()]
    paths += [p for p in (WORK / "reference").rglob("*") if p.is_file()]
    generation_path = WORK / "generation_record.json"
    generation = load(generation_path)
    paths.append(generation_path)
    for iteration in generation["iterations"]:
        raw = ROOT / iteration["workspace_raw_copy"]
        assert sha(raw) == iteration["workspace_raw_sha256"]
        prompt = ROOT / iteration["exact_prompt_file"]
        assert sha(prompt) == iteration["prompt_sha256"]
        paths.extend([raw, prompt])
        for reference in iteration.get("exact_referenced_image_paths", []):
            source = Path(reference["path"])
            if not source.is_absolute():
                source = ROOT / source
            assert sha(source) == reference["sha256"]
            assert source.resolve().is_relative_to(ROOT), "Copy source references into the project before freezing"
            paths.append(source)
    paths += list((BASE / "native_frames").glob("*.png"))
    paths += [Path(__file__), PALETTE]
    bindings = {rel(p): sha(p) for p in sorted(set(paths))}
    save(target, dict(
        status="root_selected_local_candidate_pending_user_review",
        frozen_at=datetime.now().astimezone().isoformat(),
        candidate=rel(candidate), manifest=rel(candidate / "manifest.json"),
        manifest_sha256=sha(candidate / "manifest.json"),
        native_dir=rel(candidate / "native_frames"), hd_root=rel(candidate / "clips"),
        selection_root=rel(candidate / "clips"), slots=SLOTS, frame_count=4,
        files_sha256=bindings, generation_record=rel(generation_path),
        generation_record_sha256=sha(generation_path), new_imagegen_calls=generation["new_imagegen_calls"],
        new_65535_calls=0, installed=False, user_aesthetic_approved=False,
    ))
    print(json.dumps(dict(frozen=rel(target), sha256=sha(target), bound_files=len(bindings))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["reference", "prepare", "freeze"])
    parser.add_argument("--sheet", type=Path, default=WORK / "art/idle_sheet_v01.png")
    parser.add_argument("--candidate", default="candidate01")
    parser.add_argument("--size", type=int, default=107)
    parser.add_argument("--left", type=int, default=199)
    parser.add_argument("--top", type=int, default=286)
    parser.add_argument("--grid-step-x", type=float)
    parser.add_argument("--grid-step-y", type=float)
    parser.add_argument("--overscan", type=int, default=16)
    parser.add_argument("--foot-roi", type=int, nargs=4, action="append")
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--approved", action="store_true")
    parsed = parser.parse_args()
    if parsed.command == "reference":
        reference()
    elif parsed.command == "prepare":
        prepare(parsed)
    else:
        freeze(parsed)
