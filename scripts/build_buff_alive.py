"""Build the v05 portrait: locked camera, local hair/cloth deformation and blink.

The approved hero is sampled once. Sparse, root-pinned displacement fields then
move only selected peripheral material; no face/body/camera animation is used.
Blink artwork is aligned and feathered into two eye ROIs, never a whole-face swap.
No network, generation, external programs, installation or game writes.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import distance_transform_edt, map_coordinates

from buff_portrait import ROOT, digest, write_mov


def smooth(value):
    value = np.clip(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def fixed_camera(image, size, framing):
    """One constant uniform mapping shared by every material and eye state."""
    width, height = size
    ratio = max if framing.get("fit", "cover") == "cover" else min
    scale = ratio(width / image.width, height / image.height) * framing.get("zoom", 1)
    focus = framing.get("focus", [0.5, 0.5])
    target = framing.get("target", [0.5, 0.5])
    cx, cy = focus[0] * image.width, focus[1] * image.height
    tx, ty = target[0] * width, target[1] * height
    affine = [1 / scale, 0, cx - tx / scale, 0, 1 / scale, cy - ty / scale]
    result = image.transform(size, Image.Transform.AFFINE, affine,
                             Image.Resampling.BICUBIC, fillcolor=0)
    return result, dict(uniform_scale=scale, source_focus=[cx, cy],
                        target_focus=[tx, ty], inverse_affine=affine,
                        x=0, y=0, zoom=1, angle_degrees=0)


def source_grid(size, camera):
    y, x = np.mgrid[:size[1], :size[0]].astype(np.float32)
    a, b, c, d, e, f = camera["inverse_affine"]
    return a * x + b * y + c, d * x + e * y + f


def polygon_mask(polygon, source_size, size, camera, feather_source=0):
    mask = Image.new("L", source_size)
    ImageDraw.Draw(mask).polygon([tuple(p) for p in polygon], fill=255)
    if feather_source:
        mask = mask.filter(ImageFilter.GaussianBlur(feather_source))
    mask = mask.transform(size, Image.Transform.AFFINE, camera["inverse_affine"],
                          Image.Resampling.BILINEAR, fillcolor=0)
    result = np.asarray(mask, dtype=np.float32) / 255
    # Exact zero outside a finite support keeps all unanimated pixels identical.
    result[result < 1 / 255] = 0
    return result


def make_fields(cfg, original, base, camera):
    size = base.size
    sx, sy = source_grid(size, camera)
    protected = np.zeros((size[1], size[0]), dtype=bool)
    protected_named = {}
    for region in cfg["protected"]:
        mask = polygon_mask(region["polygon"], original.size, size, camera) > 0
        protected |= mask
        protected_named[region["name"]] = mask
    fields = []
    pin = smooth(distance_transform_edt(~protected) / cfg.get("protected_falloff_px", 8))
    yy, xx = np.mgrid[:size[1], :size[0]]
    edge_distance = np.minimum.reduce([xx, yy, size[0] - 1 - xx, size[1] - 1 - yy])
    pin *= smooth(edge_distance / cfg.get("canvas_pin_px", 3))
    for region in cfg["local_motion"]:
        weight = polygon_mask(region["polygon"], original.size, size, camera,
                              region.get("feather_source", 20))
        root = region.get("root_ramp")
        if root:
            coord = sx if root["axis"] == "x" else sy
            weight *= smooth((coord - root["start"]) / (root["end"] - root["start"]))
        # Interior masks are pinned before the single image resample. They are
        # also copied exactly after it, including every original alpha byte.
        weight *= pin
        weight[protected] = 0
        phase = float(region.get("phase", 0)) + (sy / original.height) * float(region.get("length_lag", 0))
        fields.append(dict(config=region, weight=weight, phase=phase))
    return fields, protected, protected_named


def displacement(fields, k, count, max_displacement=3.0):
    shape = fields[0]["weight"].shape
    dx, dy = np.zeros(shape, np.float32), np.zeros(shape, np.float32)
    phase = 2 * math.pi * k / (count - 1)
    per_region = []
    for field in fields:
        cfg, w, lag = field["config"], field["weight"], field["phase"]
        # Starts at the approved illustration, returns to it, and permits a
        # different phase down the strand. The root remains weight zero.
        wave = (np.sin(phase + lag) - np.sin(lag)) / (1 + np.abs(np.sin(lag)))
        if k in (0, count - 1):
            wave = np.zeros_like(wave)
        wx, wy = cfg["amplitude_px"]
        local_x, local_y = w * wave * wx, w * wave * wy
        dx += local_x
        dy += local_y
        per_region.append(dict(name=cfg["name"], phase=float(cfg.get("phase", 0)),
                               amplitude_px=cfg["amplitude_px"],
                               max_displacement_px=float(np.hypot(local_x, local_y).max())))
    length = np.hypot(dx, dy)
    factor = np.minimum(1.0, max_displacement / np.maximum(length, 1e-8))
    dx *= factor
    dy *= factor
    return dx, dy, per_region


def warp_local(image, dx, dy, protected):
    """One inverse warp in premultiplied RGBA; no crossfaded duplicate layers."""
    src = np.asarray(image)
    changed = (np.abs(dx) + np.abs(dy) > 1e-6) & ~protected
    if not np.any(changed):
        return image.copy()
    y, x = np.mgrid[:image.height, :image.width].astype(np.float32)
    coords = [y - dy, x - dx]
    values = src.astype(np.float32) / 255
    values[..., :3] *= values[..., 3:4]
    warped = np.stack([map_coordinates(values[..., c], coords, order=3,
                                       mode="constant", cval=0, prefilter=True)
                       for c in range(4)], axis=-1)
    warped = np.clip(warped, 0, 1)
    alpha = warped[..., 3:4]
    warped[..., :3] = np.divide(warped[..., :3], alpha,
                               out=np.zeros_like(warped[..., :3]), where=alpha > 1e-6)
    warped = np.rint(np.clip(warped, 0, 1) * 255).astype(np.uint8)
    result = src.copy()
    result[changed] = warped[changed]
    return Image.fromarray(result, "RGBA")


def aligned_state(image, source_size, alignment):
    """Alignment is output-source -> edited-image sampling, per eye or state.

    offset [dx,dy] means sample (x+dx,y+dy) in the edited image for source (x,y).
    inverse_affine optionally supplies the full six PIL sampling coefficients.
    Identity is intentionally the default; automatic face tracking is not used.
    """
    affine = alignment.get("inverse_affine")
    if affine is None:
        dx, dy = alignment.get("offset", [0, 0])
        affine = [1, 0, dx, 0, 1, dy]
    return image.transform(source_size, Image.Transform.AFFINE, affine,
                           Image.Resampling.BICUBIC, fillcolor=0)


def make_blinks(cfg, original, base, camera):
    blink = cfg["blink"]
    states = {"open": base}
    masks = {}
    source_masks = {}
    edited_hashes = {}
    for eye in blink["eyes"]:
        source_mask = Image.new("L", original.size)
        ImageDraw.Draw(source_mask).polygon([tuple(p) for p in eye["polygon"]], fill=255)
        source_mask = source_mask.filter(ImageFilter.GaussianBlur(eye.get("feather_source", 2)))
        source_masks[eye["name"]] = np.asarray(source_mask, dtype=np.float32) / 255
        # Include the bicubic sampling footprint in the diagnostic support.
        output_mask = source_mask.filter(ImageFilter.MaxFilter(5)).transform(
            base.size, Image.Transform.AFFINE, camera["inverse_affine"],
            Image.Resampling.BILINEAR, fillcolor=0)
        masks[eye["name"]] = np.asarray(output_mask, dtype=np.float32) / 255
    union = np.maximum.reduce(list(masks.values()))
    for name in ("half", "closed"):
        state = blink["states"].get(name)
        if not state or not state.get("path") or not (ROOT / state["path"]).is_file():
            raise FileNotFoundError(f"Missing real {name} eye artwork; not exporting a blink placeholder")
        path = ROOT / state["path"]
        edited = Image.open(path).convert("RGBA")
        if edited.size != original.size:
            raise ValueError(f"{name} artwork must match {original.size}; use explicit source alignment")
        edited_hashes[name] = dict(path=state["path"], sha256=digest(path),
                                    alignment=state.get("alignment", {}),
                                    per_eye_alignment=state.get("per_eye_alignment", {}))
        composed = np.asarray(original).copy()
        for eye in blink["eyes"]:
            align = state.get("per_eye_alignment", {}).get(eye["name"], state.get("alignment", {}))
            aligned = aligned_state(edited, original.size, align)
            art = np.asarray(aligned)
            mask = source_masks[eye["name"]]
            active = mask > 0
            values = np.rint(composed[..., :3] * (1 - mask[..., None]) + art[..., :3] * mask[..., None]).astype(np.uint8)
            composed[active, :3] = values[active]
            # Original alpha stays intact, including on the face and margins.
        states[name], _ = fixed_camera(Image.fromarray(composed, "RGBA"), base.size, cfg["framing"])
    baseline = np.asarray(base).astype(np.int16)
    eye_metrics = {}
    for name, state in states.items():
        delta = np.max(np.abs(np.asarray(state).astype(np.int16) - baseline), axis=2)
        eye_metrics[name] = dict(changed_eye_pixels=int(np.count_nonzero(delta[union > 0])),
                                max_eye_rgba_difference=int(delta[union > 0].max()),
                                outside_eye_changed_pixels=int(np.count_nonzero(delta[union == 0])))
        if name != "open" and eye_metrics[name]["changed_eye_pixels"] < 24:
            raise ValueError(f"{name} eye artwork did not produce a visible local eye change")
    return states, masks, union, edited_hashes, eye_metrics


def validate_config(cfg, original):
    if [cfg.get(k) for k in ("frames", "width", "height", "fps")] != [19, 470, 668, 15]:
        raise ValueError("Current portrait preset is 19 frames, 470x668 at 15fps")
    if original.size != (1024, 1536):
        raise ValueError("v05 masks belong to the approved 1024x1536 v04 source")
    if len(cfg["blink"]["sequence"]) != cfg["frames"]:
        raise ValueError("Blink sequence must explicitly describe all frames")
    if cfg["blink"]["sequence"][0] != "open" or cfg["blink"]["sequence"][-1] != "open":
        raise ValueError("First and final frames must use the open eyes")
    if set(cfg["blink"]["sequence"]) != {"open", "half", "closed"}:
        raise ValueError("Blink requires genuine open/half/closed eye states")


def render(cfg, original):
    validate_config(cfg, original)
    size = (cfg["width"], cfg["height"])
    base, camera = fixed_camera(original, size, cfg["framing"])
    fields, protected, named = make_fields(cfg, original, base, camera)
    states, eyes, eye_union, art_hashes, eye_metrics = make_blinks(cfg, original, base, camera)
    metrics, frames, field_frames = [], [], []
    n = cfg["frames"]
    base_array = np.asarray(base).astype(np.int16)
    static = protected & (eye_union == 0)
    for k in range(n):
        dx, dy, region_info = displacement(fields, k, n, cfg.get("max_displacement_px", 3))
        state_name = cfg["blink"]["sequence"][k]
        frame = warp_local(states[state_name], dx, dy, protected)
        delta = np.max(np.abs(np.asarray(frame).astype(np.int16) - base_array), axis=2)
        stable_changes = int(np.count_nonzero(delta[static]))
        if stable_changes:
            raise ValueError(f"Frame {k} changed {stable_changes} protected pixels")
        # Comparing the deformed open image isolates motion from the blink.
        local_open = warp_local(base, dx, dy, protected)
        local_delta = np.max(np.abs(np.asarray(local_open).astype(np.int16) - base_array), axis=2)
        metrics.append(dict(frame=k, time_seconds=k / cfg["fps"], blink=state_name,
                            camera=camera, local_regions=region_info,
                            max_local_displacement_px=float(np.hypot(dx, dy).max()),
                            protected_changed_pixels=stable_changes,
                            local_motion_changed_pixels=int(np.count_nonzero(local_delta)),
                            alpha_bbox=frame.getchannel("A").getbbox(),
                            alpha_range=frame.getchannel("A").getextrema()))
        frames.append(frame)
        field_frames.append(np.stack([dx, dy], axis=-1))
    if np.any(np.asarray(frames[0]) != np.asarray(frames[-1])):
        raise ValueError("Local motion did not return to the first phase")
    if not any(x["local_motion_changed_pixels"] > 100 for x in metrics):
        raise ValueError("Local motion produced no visible deformation")
    all_fields = np.stack(field_frames)
    dxdy, dxdx = np.gradient(all_fields[..., 0], axis=(1, 2))
    dydy, dydx = np.gradient(all_fields[..., 1], axis=(1, 2))
    determinant = (1 - dxdx) * (1 - dydy) - dxdy * dydx
    if float(determinant.min()) < 0.35:
        raise ValueError("Local inverse warp compresses too sharply or folds; broaden the mask/pin transition")
    report = dict(camera_static=True, protected_pixels=int(np.count_nonzero(static)),
                  protected_max_rgba_difference=0,
                  protected_regions={name: int(np.count_nonzero(mask & (eye_union == 0))) for name, mask in named.items()},
                  eye_states=eye_metrics, first_last_max_rgba_difference=0,
                  max_local_displacement_px=max(x["max_local_displacement_px"] for x in metrics),
                  inverse_warp_jacobian_min=float(determinant.min()),
                  inverse_warp_jacobian_max=float(determinant.max()),
                  real_blink_inputs=art_hashes)
    return frames, metrics, report, fields, protected, eyes, field_frames, base


def build(config_path, source_path=None):
    cfg = json.loads(config_path.read_text("utf-8"))
    source_path = source_path or ROOT / cfg["source"]
    output = (ROOT / cfg["output"]).resolve()
    if (ROOT / "output").resolve() not in output.parents:
        raise ValueError("Output must stay inside the project's output directory")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Output is not empty; choose a new output folder")
    raw_hash = digest(source_path)
    original = Image.open(source_path).convert("RGBA")
    frames, metrics, report, fields, protected, eyes, transforms, base = render(cfg, original)
    n, width, height, fps = (cfg[k] for k in ("frames", "width", "height", "fps"))
    baseline = json.loads((ROOT / "kb/curated/buff_videos.json").read_text("utf-8"))
    by_target = {f"{x['folder']}/{x['file']}": x for x in baseline["files"]}
    targets = []
    for name in cfg.get("targets", []):
        if name not in by_target or by_target[name]["profession"] != cfg["profession"]:
            raise ValueError("Unknown target video or profession mismatch")
        targets.append(dict(relative_to_video_character=name, official_sha256=by_target[name]["sha256"]))
    output.mkdir(parents=True, exist_ok=True)
    (output / "frames").mkdir()
    (output / "motion_masks").mkdir()
    shutil.copyfile(source_path, output / "source.png")
    base.save(output / "static_base.png")
    for k, frame in enumerate(frames):
        frame.save(output / "frames" / f"frame_{k:04d}.png")
    durations = [round((k + 1) * 1000 / fps) - round(k * 1000 / fps) for k in range(n)]
    frames[0].save(output / "preview.webp", save_all=True, append_images=frames[1:],
                   duration=durations, lossless=True, loop=0, exact=True)
    cols, rows = 4, math.ceil(n / 4)
    sheet = Image.new("RGBA", (cols * width, rows * height))
    contact = Image.new("RGB", (cols * 188, rows * 285), "#242a30")
    draw = ImageDraw.Draw(contact)
    for k, frame in enumerate(frames):
        sheet.alpha_composite(frame, (k % cols * width, k // cols * height))
        thumb = frame.resize((188, 267), Image.Resampling.LANCZOS)
        xy = (k % cols * 188, k // cols * 285 + 18)
        contact.paste(thumb, xy, thumb)
        draw.text((xy[0] + 6, xy[1] - 15), f"{k + 1} {metrics[k]['blink']}", fill="white")
    sheet.save(output / "sheet.png")
    contact.save(output / "contact.jpg", quality=94)
    for field in fields:
        Image.fromarray(np.rint(field["weight"] * 255).astype(np.uint8)).save(output / "motion_masks" / f"{field['config']['name']}.png")
    Image.fromarray(protected.astype(np.uint8) * 255).save(output / "motion_masks" / "protected.png")
    for name, mask in eyes.items():
        Image.fromarray(np.rint(mask * 255).astype(np.uint8)).save(output / "motion_masks" / f"eye_{name}.png")
    np.savez_compressed(output / "local_displacement.npz", xy=np.stack(transforms).astype(np.float32))
    (output / "motion_parameters.json").write_text(json.dumps({"local_motion": cfg["local_motion"], "protected": cfg["protected"], "blink": cfg["blink"], "frame_metrics": metrics}, ensure_ascii=False, indent=2), "utf-8")
    mov = write_mov(frames, output / "portrait_rgba.mov", fps)
    if digest(source_path) != raw_hash or digest(output / "source.png") != raw_hash:
        raise ValueError("Source illustration changed during rendering")
    report["mov_roundtrip"] = mov
    (output / "motion_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    manifest = dict(title=cfg["title"], frames=n, size=[width, height], fps=fps,
                    duration_seconds=n / fps, preview_duration_ms=sum(durations),
                    generation={**cfg.get("generation", {}), "method": "static approved hero with local root-pinned displacement and independently edited eye patches"},
                    source_reference=cfg.get("reference"), source_raw_sha256=raw_hash,
                    source_illustration="source.png", source_size=list(original.size),
                    sheet_sha256=digest(output / "sheet.png"), sheet_size=list(sheet.size),
                    frame_sha256=[digest(output / "frames" / f"frame_{k:04d}.png") for k in range(n)],
                    frame_metrics=metrics, mov_roundtrip=mov, targets=targets, installed=False,
                    status="prepared_for_review_not_bink_encoded", license_note=cfg.get("license_note"), warnings=[],
                    composition=dict(mode="hero_closeup", framing=cfg["framing"], intentional_canvas_crop=True),
                    alignment=dict(anchor=None, method="Locked uniform camera; local material masks and per-eye aligned patches", validation="motion_validation.json"),
                    local_motion=dict(parameters="motion_parameters.json", masks="motion_masks", displacement="local_displacement.npz", validation="motion_validation.json"),
                    motion_limitations="One approved hero with small local image deformations and an eye-patch blink. First and last local phases match; this does not establish in-game playback or a seamless production loop.",
                    bink_encoding=dict(format="Bink 1", fps_override=fps, alpha="include straight alpha", audio=False,
                                       source="frames/frame_0000.png (numbered sequence)"))
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    return dict(output=str(output.relative_to(ROOT)), frames=n, first_frame_visible=True,
                validation=report, source_raw_sha256=raw_hash)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("source", type=Path, nargs="?")
    args = parser.parse_args()
    print(json.dumps(build(args.config, args.source), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
