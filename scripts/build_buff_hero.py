"""Render a short transparent buff portrait from one hero illustration.

This is motion graphics: one fixed character image, subtle camera motion and
abstract light effects. It does not synthesize acting, blinking or cloth motion.
No paid calls, downloads, external processes or game writes.

    python scripts/build_buff_hero.py design/claude_gunner/buff_v04.json HERO.png
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from buff_portrait import ROOT, digest, write_mov


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def motion(frame, count):
    """A fast, visible settling gesture, then a restrained continuing push-in."""
    t = frame / max(1, count - 1)
    settle = 1 - (1 - min(1.0, t / 0.24)) ** 3
    hold = smooth((t - 0.24) / 0.76)
    return dict(t=t, zoom=1.035 - 0.035 * settle + 0.022 * hold,
                x=-12.0 * (1 - settle) + 1.6 * math.sin(math.pi * hold),
                y=3.0 * (1 - settle) - 1.5 * math.sin(math.pi * hold),
                angle_degrees=-0.35 * (1 - settle), opacity=0.96 + 0.04 * settle,
                ribbon_alpha=0.09 + 0.12 * math.sin(math.pi * t),
                glint_alpha=max(0.0, math.sin(math.pi * (t - 0.12) / 0.76)))


def camera(image, size, framing, pose):
    width, height = size
    # All frames sample the original at one uniform scale. Intentional camera
    # crop is allowed; no silhouette fitting or registration is performed.
    fit = framing.get("fit", "cover")
    factor = max(width / image.width, height / image.height) if fit == "cover" else min(width / image.width, height / image.height)
    scale = factor * float(framing.get("zoom", 1)) * pose["zoom"]
    focus = framing.get("focus", [0.5, 0.5])
    target = framing.get("target", [0.5, 0.5])
    cx, cy = focus[0] * image.width, focus[1] * image.height
    tx, ty = target[0] * width + pose["x"], target[1] * height + pose["y"]
    theta = math.radians(pose["angle_degrees"])
    a, b = math.cos(theta) / scale, math.sin(theta) / scale
    d, e = -b, a
    affine = (a, b, cx - a * tx - b * ty, d, e, cy - d * tx - e * ty)
    result = image.transform(size, Image.Transform.AFFINE, affine,
                             Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
    if pose["opacity"] < 1:
        result.putalpha(result.getchannel("A").point(lambda alpha: round(alpha * pose["opacity"])))
    return result, dict(uniform_scale=scale, source_focus=[cx, cy], target_focus=[tx, ty],
                        inverse_affine=list(affine), **pose)


def lights(size, pose):
    """Small peripheral ribbons and glints, never an opaque background plate."""
    width, height = size
    ss = 2
    back = Image.new("RGBA", (width * ss, height * ss))
    front = Image.new("RGBA", back.size)
    bd, fd = ImageDraw.Draw(back), ImageDraw.Draw(front)
    t = pose["t"]
    alpha = round(255 * pose["ribbon_alpha"])
    ribbons = []
    for x, lean, strength in ((0.08 + 0.018 * t, 0.085, 1), (0.91 - 0.014 * t, -0.075, 0.75)):
        p0, p1 = (x * width, -height * 0.06), ((x + lean) * width, height * 1.06)
        bd.line(tuple(round(v * ss) for p in (p0, p1) for v in p),
                fill=(255, 119, 28, round(alpha * strength)), width=round(8 * ss))
        ribbons.append(dict(start=list(p0), end=list(p1), alpha=round(alpha * strength), width=8))
    back = back.filter(ImageFilter.GaussianBlur(5 * ss))
    sparks = []
    points = ((0.12, 0.17, 1.8), (0.88, 0.26, 2.2), (0.10, 0.68, 2.5),
              (0.86, 0.79, 1.9), (0.21, 0.87, 1.7))
    for index, (x, y, radius) in enumerate(points):
        px = (x + 0.006 * math.sin(t * math.pi * 1.4 + index)) * width
        py = (y - 0.015 * t) * height
        sparkle = 0.22 + 0.78 * max(0.0, math.sin(math.pi * (t + index * 0.16)))
        a = round(185 * sparkle * (0.7 + 0.3 * pose["glint_alpha"]))
        xx, yy, r = px * ss, py * ss, radius * ss
        fd.line((round(xx - r * 2), round(yy), round(xx + r * 2), round(yy)), fill=(255, 211, 139, a), width=ss)
        fd.line((round(xx), round(yy - r * 2), round(xx), round(yy + r * 2)), fill=(255, 211, 139, a), width=ss)
        sparks.append(dict(center=[px, py], alpha=a, radius=radius))
    back = back.resize(size, Image.Resampling.LANCZOS)
    front = front.resize(size, Image.Resampling.LANCZOS)
    return back, front, dict(ribbons=ribbons, sparks=sparks)


def validate(config, image):
    values = [config.get(k) for k in ("frames", "width", "height", "fps")]
    if values != [19, 470, 668, 15]:
        raise ValueError("The current v04 preset uses 19 frames, 470x668, 15fps; these are not asserted game-format limits")
    if image.width * image.height > 40_000_000 or min(image.size) < 128:
        raise ValueError("Unexpected hero illustration dimensions")
    extrema = image.getchannel("A").getextrema()
    if extrema[0] == 255 or extrema[1] < 240:
        raise ValueError("Hero illustration must contain genuine transparent and opaque pixels")
    framing = config.get("framing", {})
    if not isinstance(framing, dict) or framing.get("fit", "cover") not in ("cover", "contain"):
        raise ValueError("Bad framing")
    zoom = framing.get("zoom", 1)
    if isinstance(zoom, bool) or not isinstance(zoom, (int, float)) or not math.isfinite(zoom) or not 0.5 <= zoom <= 2:
        raise ValueError("Bad framing zoom")
    for name in ("focus", "target"):
        point = framing.get(name, [0.5, 0.5])
        if not isinstance(point, list) or len(point) != 2 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in point):
            raise ValueError(f"Bad framing {name}")
    return framing


def build(config_path, source_path):
    cfg = json.loads(config_path.read_text("utf-8"))
    output = (ROOT / cfg["output"]).resolve()
    if (ROOT / "output").resolve() not in output.parents:
        raise ValueError("Buff output must stay inside the project's output directory")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Output is not empty; choose a new version")
    raw_hash = digest(source_path)
    original = Image.open(source_path).convert("RGBA")
    framing = validate(cfg, original)
    n, width, height, fps = (cfg[k] for k in ("frames", "width", "height", "fps"))
    frames, metrics = [], []
    for k in range(n):
        pose = motion(k, n)
        figure, transform = camera(original, (width, height), framing, pose)
        behind, ahead, effects = lights((width, height), pose)
        behind.alpha_composite(figure)
        behind.alpha_composite(ahead)
        alpha = behind.getchannel("A")
        if alpha.getextrema()[0] > 8 or alpha.getbbox() is None:
            raise ValueError("Rendered buff lost transparency or visible content")
        frames.append(behind)
        metrics.append(dict(frame=k, time_seconds=k / fps, camera=transform, effects=effects,
                            alpha_bbox=alpha.getbbox(), alpha_range=alpha.getextrema()))
    baseline = json.loads((ROOT / "kb/curated/buff_videos.json").read_text("utf-8"))
    by_target = {f"{x['folder']}/{x['file']}": x for x in baseline["files"]}
    targets = []
    for name in cfg.get("targets", []):
        if name not in by_target or by_target[name]["profession"] != cfg["profession"]:
            raise ValueError("Unknown target video or profession mismatch")
        targets.append(dict(relative_to_video_character=name, official_sha256=by_target[name]["sha256"]))
    output.mkdir(parents=True, exist_ok=True)
    (output / "frames").mkdir()
    shutil.copyfile(source_path, output / "source.png")
    for k, frame in enumerate(frames):
        frame.save(output / "frames" / f"frame_{k:04d}.png")
    durations = [round((k + 1) * 1000 / fps) - round(k * 1000 / fps) for k in range(n)]
    frames[0].save(output / "preview.webp", save_all=True, append_images=frames[1:], duration=durations, lossless=True, loop=0, exact=True)
    cols, rows = 4, math.ceil(n / 4)
    sheet = Image.new("RGBA", (cols * width, rows * height))
    contact = Image.new("RGB", (cols * 188, rows * 285), "#242a30")
    draw = ImageDraw.Draw(contact)
    for k, frame in enumerate(frames):
        sheet.alpha_composite(frame, (k % cols * width, k // cols * height))
        thumb = frame.resize((188, 267), Image.Resampling.LANCZOS)
        xy = (k % cols * 188, k // cols * 285 + 18)
        contact.paste(thumb, xy, thumb)
        draw.text((xy[0] + 6, xy[1] - 15), str(k + 1), fill="white")
    sheet.save(output / "sheet.png")
    contact.save(output / "contact.jpg", quality=94)
    mov = write_mov(frames, output / "portrait_rgba.mov", fps)
    if digest(source_path) != raw_hash or digest(output / "source.png") != raw_hash:
        raise ValueError("Source illustration changed during rendering")
    manifest = dict(title=cfg["title"], frames=n, size=[width, height], fps=fps,
                    duration_seconds=n / fps, preview_duration_ms=sum(durations),
                    generation={**cfg.get("generation", {}), "method": "single AI hero illustration with deterministic camera and light effects"},
                    source_reference=cfg.get("reference"), source_raw_sha256=raw_hash,
                    source_illustration="source.png", source_size=list(original.size),
                    sheet_sha256=digest(output / "sheet.png"), sheet_size=list(sheet.size),
                    frame_sha256=[digest(output / "frames" / f"frame_{k:04d}.png") for k in range(n)],
                    frame_metrics=metrics, mov_roundtrip=mov, targets=targets, installed=False,
                    status="prepared_for_review_not_bink_encoded", license_note=cfg.get("license_note"), warnings=[],
                    composition=dict(mode="hero_closeup", framing=framing, intentional_canvas_crop=True),
                    alignment=dict(anchor=None, method="Camera movement only; no body, silhouette or foot registration", validation=None),
                    motion_limitations="One fixed character illustration. Motion is camera plus abstract light effects, not acting, blinking or cloth animation. Loop closure and in-game playback have not been verified.",
                    bink_encoding=dict(format="Bink 1", fps_override=fps, alpha="include straight alpha", audio=False,
                                       source="frames/frame_0000.png (numbered sequence)"))
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    return dict(output=str(output.relative_to(ROOT)), frames=n, first_frame_visible=True, mov_roundtrip=mov,
                source_raw_sha256=raw_hash, intentional_crop=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.config, args.source), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
