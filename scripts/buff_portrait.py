"""Prepare a transparent buff-portrait sheet for review and later Bink encoding.

No paid calls, external programs, downloads or game writes. PNG frames and an
alpha-preserving MOV are the encoding sources; a renamed MOV is NOT a Bink file.
Usage: python scripts/buff_portrait.py design/claude_gunner/buff.json SHEET.png
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path
import shutil

import av
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def project_path(value):
    path = (ROOT / value).resolve()
    if ROOT not in path.parents:
        raise ValueError("Path must stay inside the project")
    return path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def alpha_bounds(image, threshold=16):
    return image.getchannel("A").point(lambda alpha: 255 if alpha > threshold else 0).getbbox()


def feet_anchor(image, band_height=16):
    """Measure opaque shoes, excluding transparent background/soft edge noise.

    Three opaque pixels are required on a candidate bottom row. A fixed-height
    band immediately above that row supplies an alpha-weighted horizontal
    centroid; y is the bottom pixel edge. This is for stationary-foot portraits,
    not locomotion, and never determines a per-frame scale.
    """
    alpha = np.asarray(image.getchannel("A"))
    opaque = alpha > 128
    supported_rows = np.flatnonzero(np.count_nonzero(opaque, axis=1) >= 3)
    if not supported_rows.size:
        raise ValueError("Cannot locate opaque feet")
    bottom = int(supported_rows[-1]) + 1
    top = max(0, bottom - band_height)
    mask = opaque[top:bottom]
    weights = alpha[top:bottom].astype(np.float64) * mask
    if np.count_nonzero(mask) < 8:
        raise ValueError("Insufficient opaque pixels in the feet band")
    x = float((weights * (np.arange(image.width) + 0.5)).sum() / weights.sum())
    return {"x": x, "y": float(bottom), "alpha_threshold": 128,
            "band_height": band_height, "support_pixels": int(np.count_nonzero(mask))}


def render_cell(cell, size, scale, origin):
    # One affine resample uses the identical scalar for every frame and both
    # axes. Unlike resizing differently sized rounded cells, it cannot vary the
    # character scale by column. Translation is applied in this same resample.
    return cell.transform(size, Image.Transform.AFFINE,
                          (1 / scale, 0, -origin[0] / scale,
                           0, 1 / scale, -origin[1] / scale),
                          Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))


def write_mov(frames, path, fps):
    with av.open(str(path), "w", format="mov") as container:
        stream = container.add_stream("qtrle", rate=fps)
        stream.width, stream.height = frames[0].size
        stream.pix_fmt = "argb"
        stream.time_base = Fraction(1, fps)
        for k, image in enumerate(frames):
            frame = av.VideoFrame.from_ndarray(np.asarray(image), format="rgba")
            frame.pts, frame.time_base = k, Fraction(1, fps)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    # Decode the actual intermediate: check all RGBA values and exact ordering.
    with av.open(str(path)) as container:
        decoded = list(container.decode(video=0))
        if len(decoded) != len(frames):
            raise ValueError("MOV round-trip changed frame count")
        worst = max(int(np.abs(np.asarray(a).astype(np.int16) - b.to_ndarray(format="rgba").astype(np.int16)).max())
                    for a, b in zip(frames, decoded))
        if worst:
            raise ValueError(f"MOV round-trip changed RGBA values by {worst}")
    return {"codec": "qtrle", "pixel_format": "argb", "frames": len(frames), "max_rgba_difference": worst}


def prepare(config_path, sheet_path):
    config = json.loads(config_path.read_text("utf-8"))
    cols, rows, count = [config[k] for k in ("columns", "rows", "frames")]
    width, height, fps = [config[k] for k in ("width", "height", "fps")]
    if any(type(v) is not int or v < 1 for v in (cols, rows, count, width, height, fps)):
        raise ValueError("Grid, dimensions and frame rate must be positive integers")
    if cols * rows > 64 or not count <= cols * rows or width * height * count > 40_000_000 or fps > 60:
        raise ValueError("Sheet exceeds preparation limits")
    out = project_path(config["output"])
    if (out / "manifest.json").exists():
        raise FileExistsError("Version already prepared; choose a new output directory")
    source_raw_sha256 = digest(sheet_path)
    sheet = Image.open(sheet_path)
    if sheet.width * sheet.height > 40_000_000 or sheet.width < cols * 32 or sheet.height < rows * 32:
        raise ValueError("Unexpected sheet dimensions")
    sheet = sheet.convert("RGBA")
    if sheet.getchannel("A").getextrema()[0] == 255:
        raise ValueError("Sheet has no transparency; use an actual RGBA sheet")
    if (count, width, height, fps) != (19, 470, 668, 15):
        raise ValueError("Review player requires 19 frames, 470x668, 15 fps")
    anchor_mode = config.get("anchor")
    if anchor_mode not in (None, "feet"):
        raise ValueError("Supported anchor values are null or feet")
    frames, metrics, warnings, cells = [], [], [], []
    cell_width, cell_height = sheet.width / cols, sheet.height / rows
    scale = min(width / cell_width, height / cell_height)
    base_origin = ((width - cell_width * scale) / 2, (height - cell_height * scale) / 2)
    cell_ratio = (sheet.width / cols) / (sheet.height / rows)
    if abs(cell_ratio / (width / height) - 1) > 0.03:
        warnings.append("Generated cell aspect ratio differs from target; cells are uniformly fitted with transparent padding, never stretched")
    for k in range(count):
        col, row = k % cols, k // cols
        rectangle = (round(col * sheet.width / cols), round(row * sheet.height / rows),
                     round((col + 1) * sheet.width / cols), round((row + 1) * sheet.height / rows))
        cell = sheet.crop(rectangle)
        bounds = alpha_bounds(cell)
        if bounds is None:
            raise ValueError(f"Frame {k + 1} is empty: sheet does not match the configured grid")
        margin = min(bounds[0], bounds[1], cell.width - bounds[2], cell.height - bounds[3])
        alpha = np.asarray(cell.getchannel("A"))
        edge_max = int(max(alpha[0].max(), alpha[-1].max(), alpha[:, 0].max(), alpha[:, -1].max()))
        if edge_max > 128:
            raise ValueError(f"Frame {k + 1}: opaque subject reaches a source cell boundary")
        if margin < 2:
            warnings.append(f"Frame {k + 1}: soft alpha edge is {margin}px from the source cell boundary; boundary alpha is at most {edge_max}/255, not an opaque clipping edge")
        cells.append(cell)
        metrics.append({"frame": k, "source_rectangle": rectangle, "source_alpha_bbox": bounds,
                        "source_alpha_bbox_128": alpha_bounds(cell, 128),
                        "source_margin_gt16": margin, "source_boundary_max_alpha": edge_max,
                        "source_feet_anchor": feet_anchor(cell) if anchor_mode == "feet" else None})
    target = None
    if anchor_mode == "feet":
        target = [float(np.median([m["source_feet_anchor"][axis] * scale + base_origin[i]
                                   for m in metrics])) for i, axis in enumerate(("x", "y"))]
        # The measured bottom is a pixel edge, so use an integer output edge.
        target[1] = float(round(target[1]))
    for k, (cell, metric) in enumerate(zip(cells, metrics)):
        measured = metric["source_feet_anchor"]
        dx = target[0] - (measured["x"] * scale + base_origin[0]) if target else 0.0
        dy = target[1] - (measured["y"] * scale + base_origin[1]) if target else 0.0
        origin = (base_origin[0] + dx, base_origin[1] + dy)
        output_band = max(1, round(16 * scale))
        frame = render_cell(cell, (width, height), scale, origin)
        # Resampling can move an alpha>128 contour by a pixel even when its
        # geometric edge is aligned. Correct that integer y residual by another
        # render from the original cell, never by resampling the rendered frame.
        contour_dy = 0.0
        if target:
            contour_dy = target[1] - feet_anchor(frame, output_band)["y"]
            if contour_dy:
                dy += contour_dy
                origin = (origin[0], origin[1] + contour_dy)
                frame = render_cell(cell, (width, height), scale, origin)
        bounds = metric["source_alpha_bbox"]
        projected = [bounds[0] * scale + origin[0], bounds[1] * scale + origin[1],
                     bounds[2] * scale + origin[0], bounds[3] * scale + origin[1]]
        if min(projected[0], projected[1], width - projected[2], height - projected[3]) < 2:
            raise ValueError(f"Frame {k + 1}: aligned subject would be cropped or lack a 2px output margin")
        metric.update(scale=scale, translation={"dx": dx, "dy": dy},
                      resampled_contour_y_correction=contour_dy,
                      render_origin=list(origin), projected_visible_bbox=projected,
                      alpha_bbox=frame.getchannel("A").getbbox(),
                      alpha_bbox_16=alpha_bounds(frame), alpha_bbox_128=alpha_bounds(frame, 128),
                      output_feet_anchor=feet_anchor(frame, output_band) if target else None)
        frames.append(frame)
    alignment_check = None
    if target:
        anchors = [m["output_feet_anchor"] for m in metrics]
        x_range = max(a["x"] for a in anchors) - min(a["x"] for a in anchors)
        y_range = max(a["y"] for a in anchors) - min(a["y"] for a in anchors)
        row_jumps = [abs(anchors[k]["x"] - anchors[k - 1]["x"])
                     for k in range(cols, count, cols)]
        alignment_check = {"measurement_alpha_threshold": 128, "x_range_pixels": x_range,
                           "y_range_pixels": y_range, "row_transition_x_jumps_pixels": row_jumps,
                           "max_row_transition_x_jump_pixels": max(row_jumps, default=0),
                           "max_allowed_x_range_pixels": 1.0, "max_allowed_y_range_pixels": 1.0,
                           "passed": x_range <= 1 and y_range <= 1}
        if not alignment_check["passed"]:
            raise ValueError(f"Feet alignment verification failed: {alignment_check}")
    out.mkdir(parents=True, exist_ok=True)
    frame_dir = out / "frames"
    frame_dir.mkdir(exist_ok=True)
    if sheet_path.resolve() != (out / "sheet.png").resolve():
        shutil.copyfile(sheet_path, out / "sheet.png")
    if digest(sheet_path) != source_raw_sha256 or digest(out / "sheet.png") != source_raw_sha256:
        raise ValueError("Source sheet changed or its byte-preserving copy differs")
    for k, frame in enumerate(frames):
        frame.save(frame_dir / f"frame_{k:04d}.png")
    durations = [round((k + 1) * 1000 / fps) - round(k * 1000 / fps) for k in range(count)]
    frames[0].save(out / "preview.webp", save_all=True, append_images=frames[1:],
                   duration=durations, lossless=True, loop=0, exact=True)
    mov_check = write_mov(frames, out / "portrait_rgba.mov", fps)
    # A compact contact sheet is for visual checking, not an encoding source.
    contact = Image.new("RGB", (cols * 188, rows * 285), "#242a30")
    draw = ImageDraw.Draw(contact)
    for k, frame in enumerate(frames):
        thumb = frame.resize((188, 267), Image.Resampling.LANCZOS)
        at = (k % cols * 188, k // cols * 285 + 18)
        contact.paste(thumb, at, thumb)
        draw.text((at[0] + 6, at[1] - 15), str(k + 1), fill="white")
    contact.save(out / "contact.jpg", quality=94)
    baseline = json.loads((ROOT / "kb/curated/buff_videos.json").read_text("utf-8"))
    by_target = {f"{x['folder']}/{x['file']}": x for x in baseline["files"]}
    targets = []
    for target_video in config.get("targets", []):
        if target_video not in by_target or by_target[target_video]["profession"] != config["profession"]:
            raise ValueError("Unknown target video or profession mismatch")
        targets.append({"relative_to_video_character": target_video, "official_sha256": by_target[target_video]["sha256"]})
    manifest = {"title": config["title"], "sheet_sha256": digest(out / "sheet.png"), "sheet_size": sheet.size,
                "source_raw_sha256": source_raw_sha256,
                "source_sheet": str(sheet_path.resolve().relative_to(ROOT)) if sheet_path.resolve().is_relative_to(ROOT) else str(sheet_path.resolve()),
                "generation": config.get("generation"),
                "source_reference": config.get("reference"), "frames": count, "size": [width, height],
                "fps": fps, "duration_seconds": count / fps, "preview_duration_ms": sum(durations),
                "frame_metrics": metrics, "warnings": warnings, "mov_roundtrip": mov_check,
                "alignment": {"anchor": anchor_mode, "target_pixels": target,
                              "common_scale": scale, "base_origin_pixels": list(base_origin),
                              "method": "Single uniform affine scale; per-frame translation only",
                              "validation": alignment_check,
                              "limitation": "Foot registration does not validate hand/face continuity, animation flow, loop closure, Bink encoding or in-game playback."},
                "frame_sha256": [digest(frame_dir / f"frame_{k:04d}.png") for k in range(count)],
                "targets": targets, "status": "prepared_for_review_not_bink_encoded", "installed": False,
                "license_note": config.get("license_note"),
                "bink_encoding": {"format": "Bink 1", "fps_override": fps, "alpha": "include straight alpha",
                                  "audio": False, "source": "frames/frame_0000.png (numbered sequence)",
                                  "help": "https://www.radgametools.com/binkhcwb.htm"}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    page = '''<!doctype html><meta charset="utf-8"><title>__TITLE__</title>
<style>body{margin:24px;background:#14191e;color:#e7eaf0;font:16px system-ui}main{display:flex;gap:24px;flex-wrap:wrap}canvas{width:470px;height:668px;max-width:100%;image-rendering:auto}button,input,select{font:inherit;margin:8px}a{color:#ffbb68}p{max-width:660px;line-height:1.7}</style>
<h1>__TITLE__</h1><p>同一张图的 19 帧试作 · 470×668 · 15 fps · 尚未编码 Bink，未安装、未实机验证。重点检查脸、手、花饰和裙摆是否跳变。__ALIGNMENT__</p>
<main><section><canvas id="stage" width="470" height="668"></canvas><div><button id="play">暂停</button><input id="frame" type="range" min="0" max="18" value="0"><span id="number"></span></div><select id="bg"><option value="#252c36">深色</option><option value="#b8b9bd">浅色</option><option value="#64768a">灰蓝</option></select></section><section><p><a href="contact.jpg">19 帧总览</a> · <a href="sheet.png">原始动作表</a> · <a href="preview.webp">透明动图</a> · <a href="portrait_rgba.mov">无损透明 MOV</a> · <a href="manifest.json">来源与编码参数</a></p><p>编码源为透明 PNG 序列或透明 MOV。RAD 中选择 Bink 1，包含 alpha，覆盖帧率为 15，无声；成片应解码核对 19 帧、尺寸及 alpha，再准备替换包。</p><p>民间二创形象，作者和授权未核实，仅自用。</p></section></main>
<script>
const frames=Array.from({length:19},(_,k)=>{const image=new Image();image.src=`frames/frame_${String(k).padStart(4,'0')}.png`;return image});
let k=0,playing=false,ready=false;
const c=document.querySelector('canvas'),g=c.getContext('2d'),slider=document.querySelector('#frame'),button=document.querySelector('#play'),number=document.querySelector('#number');
button.disabled=slider.disabled=true;number.textContent='正在加载19帧…';
function draw(){g.fillStyle=document.querySelector('#bg').value;g.fillRect(0,0,470,668);if(ready){g.drawImage(frames[k],0,0);slider.value=k;number.textContent=`${k+1}/19`}}
button.onclick=()=>{playing=!playing;button.textContent=playing?'暂停':'播放'};
slider.oninput=()=>{playing=false;k=Number(slider.value);button.textContent='播放';draw()};
document.querySelector('#bg').onchange=draw;
Promise.all(frames.map(image=>image.decode())).then(()=>{ready=playing=true;button.disabled=slider.disabled=false;draw()}).catch(()=>{number.textContent='帧加载失败，请刷新后重试'});
setInterval(()=>{if(playing&&ready){k=(k+1)%19;draw()}},1000/15);
</script>'''
    alignment_note = "脚底定位已校正；手脸连续性、动作流畅度和循环衔接仍待动态审核。" if target else ""
    (out / "index.html").write_text(page.replace("__TITLE__", html.escape(config["title"])).replace("__ALIGNMENT__", alignment_note), "utf-8")
    return {"output": str(out.relative_to(ROOT)), "frames": count, "warnings": warnings, "mov_roundtrip": mov_check}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("sheet", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.config, args.sheet), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
