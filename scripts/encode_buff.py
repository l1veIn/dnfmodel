"""Encode a prepared buff portrait with the official RAD tool, then decode it.

No game writes or downloads. The user must authorize acquiring/running RAD first.
Usage: python scripts/encode_buff.py design/claude_gunner/buff_v03.json
       python scripts/encode_buff.py CONFIG --verify-only
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import av
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOOL = ROOT / "tools/downloads/rad_video_tools_2026-10-28/bin/radvideo64.exe"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def output_path(value):
    path = (ROOT / value).resolve()
    if (ROOT / "output").resolve() not in path.parents:
        raise ValueError("Encoding output must be within the project's output directory")
    return path


def verify(folder, manifest, movie):
    width, height = manifest["size"]
    expected_count, fps = manifest["frames"], manifest["fps"]
    if not 1 <= expected_count <= 64 or width * height * expected_count > 40_000_000:
        raise ValueError("Portrait exceeds verification limits")
    with movie.open("rb") as stream:
        magic = stream.read(4)
    if magic[:3] != b"BIK":
        raise ValueError("Output is not an ordinary Bink 1 stream")
    decoded, times = [], []
    with av.open(str(movie)) as container:
        video = container.streams.video
        if len(video) != 1 or container.streams.audio:
            raise ValueError("Expected one video stream and no audio")
        stream = video[0]
        actual_fps = stream.average_rate
        pix_fmt = stream.codec_context.format.name
        if stream.codec_context.name != "binkvideo" or (stream.width, stream.height) != (width, height):
            raise ValueError("Encoded codec or dimensions differ from the prepared portrait")
        if actual_fps != Fraction(fps, 1) or "a" not in pix_fmt:
            raise ValueError("Encoded frame rate or alpha plane is incorrect")
        for frame in container.decode(video=0):
            if len(decoded) >= expected_count:
                raise ValueError("Bink output has too many frames")
            if (frame.width, frame.height) != (width, height):
                raise ValueError("Frame dimensions changed within the movie")
            decoded.append(Image.fromarray(frame.to_ndarray(format="rgba")))
            times.append(float(frame.pts * frame.time_base) if frame.pts is not None else None)
        if len(decoded) != expected_count:
            raise ValueError("Bink output has the wrong frame count")
    decoded_dir = folder / "encoded_frames"
    decoded_dir.mkdir(exist_ok=True)
    alpha_errors, visible_rgb_errors, alpha_ranges = [], [], []
    source_hashes = []
    for k, image in enumerate(decoded):
        original_path = folder / "frames" / f"frame_{k:04d}.png"
        original = Image.open(original_path).convert("RGBA")
        source_hashes.append(sha256(original_path))
        a, b = np.asarray(original).astype(np.int16), np.asarray(image).astype(np.int16)
        if a.shape != b.shape:
            raise ValueError("Source dimensions differ from the prepared manifest")
        visible = a[..., 3] > 16
        alpha_errors.append(float(np.abs(a[..., 3] - b[..., 3]).mean()))
        visible_rgb_errors.append(float(np.abs(a[..., :3] - b[..., :3])[visible].mean()) if visible.any() else 0)
        alpha_ranges.append([int(b[..., 3].min()), int(b[..., 3].max())])
        image.save(decoded_dir / f"frame_{k:04d}.png")
    if source_hashes != manifest["frame_sha256"]:
        raise ValueError("Source frame hashes no longer match the prepared manifest")
    if any(lo > 8 or hi < 240 for lo, hi in alpha_ranges):
        raise ValueError("Decoded alpha no longer contains both transparent and opaque content")
    if any(value > 4 for value in alpha_errors):
        raise ValueError("Decoded alpha differs too much from the source")
    durations = [round((k + 1) * 1000 / fps) - round(k * 1000 / fps) for k in range(expected_count)]
    decoded[0].save(folder / "encoded_preview.webp", save_all=True, append_images=decoded[1:],
                    lossless=True, duration=durations, loop=0, exact=True)
    return dict(status="encoded", file=movie.name, codec="binkvideo", pixel_format=pix_fmt,
                magic=magic.decode("ascii"), width=width, height=height, frames=expected_count,
                fps=fps, alpha=True, has_alpha=True, audio_streams=0, verified=True,
                validation_scope="Bink1, frame count, dimensions, fps, no audio, alpha plane and bounded alpha error",
                visual_review="pending", ingame_verified=False, source_manifest_sha256=sha256(folder / "manifest.json"),
                source_frame_sha256=source_hashes, source_frames_sha256=source_hashes,
                file_sha256=sha256(movie), sha256=sha256(movie), size=movie.stat().st_size,
                decoded_preview="encoded_preview.webp", decoded_frames="encoded_frames", frame_times_seconds=times,
                quality=dict(alpha_mae_mean=float(np.mean(alpha_errors)), alpha_mae_worst=max(alpha_errors),
                             visible_rgb_mae_mean=float(np.mean(visible_rgb_errors)), visible_rgb_mae_worst=max(visible_rgb_errors),
                             note="Bink1 is lossy; visible RGB is measured, not required to be identical",
                             alpha_ranges=alpha_ranges))


def encode(config, tool=DEFAULT_TOOL, verify_only=False):
    cfg = json.loads(config.read_text("utf-8"))
    folder = output_path(cfg["output"])
    manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
    movie, report_path = folder / "portrait.bik", folder / "encoding_report.json"
    command = []
    if not verify_only:
        if movie.exists():
            raise FileExistsError("Bink already exists; use --verify-only or prepare a new version")
        if not tool.is_file():
            raise FileNotFoundError("Official RAD tool is not present")
        # An explicit file list also handles frame_0000 without relying on the
        # compressor's automatic numbered-sequence detection.
        sequence = folder / "input_frames.lst"
        sequence.write_text("\n".join(str(folder / "frames" / f"frame_{k:04d}.png")
                                      for k in range(manifest["frames"])) + "\n", encoding="utf-8")
        source = str(sequence)
        command = [str(tool.resolve()), "binkc", source, str(movie), "/Bink1", "/Alpha",
                   f"/ForceFrameRate{manifest['fps']}", "/NoSound", "/DataRate1000000", "/CPUs4", "/AutoClose"]
        options = {}
        if os.name == "nt":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            options.update(startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
        completed = subprocess.run(command, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=30, check=False, **options)
        if completed.returncode or not movie.is_file():
            raise RuntimeError(f"RAD did not produce the Bink file (exit {completed.returncode})")
    previous = json.loads(report_path.read_text("utf-8")) if verify_only and report_path.exists() else {}
    report = verify(folder, manifest, movie)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    encoder = previous.get("encoder") if verify_only else dict(
        name="RAD Video Tools", version="2026.10", file=str(tool.relative_to(ROOT)) if tool.is_relative_to(ROOT) else tool.name,
        sha256=sha256(tool), download="https://www.radgametools.com/down/Bink/RADTools.7z",
        archive_sha1="93d2ec216865979065bfb01916007c3dc01cb905", command=command)
    # Re-verifying must not invent or replace the original encoding provenance.
    report.update(created=previous.get("created", now), verified_at=now, encoder=encoder)
    temporary = report_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    temporary.replace(report_path)
    return dict(file=str(movie.relative_to(ROOT)), bytes=report["size"], frames=report["frames"], fps=report["fps"],
                alpha=report["alpha"], verified=report["verified"], quality=report["quality"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--tool", type=Path, default=DEFAULT_TOOL)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(encode(args.config, args.tool, args.verify_only), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
