"""Turn an H3 repaint trial into native frames: silhouette-matched frame choice, two downscales.

Frame choice maximizes overlap with the layered frame of the same slot, so a wrong pose
cannot be picked just because it sits at the expected time. Run with the ComfyUI venv python.
"""
from __future__ import annotations

import json
import sys

import av
import numpy as np
from PIL import Image

from fatfish_doll import ROOT
from fatfish_h3_repaint import CLIPS, DOLL, RUN
from process_full_ref2va import matte

OUT = RUN / "processed"
SCALE = (213.3333 / 608, 128 / 352)
ORIGIN = (143, 272)
SIZE = (round(608 * SCALE[0]), 128)


def video_cutouts(path):
    frames = []
    with av.open(str(path)) as video:
        for frame in video.decode(video=0):
            frames.append(matte(frame.to_image()))
    return frames


def small_alpha(image):
    return np.asarray(image.getchannel("A").resize(SIZE, Image.Resampling.BOX)) > 110


def target_mask(slot):
    alpha = np.asarray(Image.open(DOLL / f"{slot:04d}.png").getchannel("A")) > 0
    return alpha[ORIGIN[1]:ORIGIN[1] + SIZE[1], ORIGIN[0]:ORIGIN[0] + SIZE[0]]


def iou(a, b, dx=0, dy=0):
    moved = np.roll(np.roll(a, dy, 0), dx, 1)
    union = (moved | b).sum()
    return (moved & b).sum() / max(union, 1)


def choose(scores, cycle):
    slots, frames = scores.shape
    if cycle:
        best = None
        for period in range(18, 60):
            for start in range(8, frames - period):
                picks = [start + round(k * period / slots) for k in range(slots)]
                value = sum(scores[k, picks[k]] for k in range(slots))
                if best is None or value > best[0]:
                    best = (value, picks)
        return best[1]
    # Monotonic path through the video: frames only move forward with the slots.
    table = np.full((slots, frames), -1e9)
    back = np.zeros((slots, frames), int)
    table[0] = scores[0]
    for k in range(1, slots):
        running = np.maximum.accumulate(table[k - 1])
        where = np.zeros(frames, int)
        top = 0
        for f in range(frames):
            if table[k - 1, f] >= table[k - 1, top]:
                top = f
            where[f] = top
        table[k] = running + scores[k]
        back[k] = where
    path = [int(table[-1].argmax())]
    for k in range(slots - 1, 0, -1):
        path.append(int(back[k, path[-1]]))
    return path[::-1]


def soft(image):
    """Previous route: premultiplied Lanczos."""
    return image.convert("RGBa").resize(SIZE, Image.Resampling.LANCZOS).convert("RGBA")


def crisp(image, palette):
    """Box-down, hard alpha, one palette per clip: reads as pixels instead of a blurred photo."""
    small = np.array(image.convert("RGBa").resize(SIZE, Image.Resampling.BOX).convert("RGBA"))
    solid = small[..., 3] > 110
    flat = Image.fromarray(small[..., :3], "RGB").quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB")
    out = np.zeros_like(small)
    out[..., :3] = np.array(flat)
    out[..., 3] = solid * 255
    return Image.fromarray(out, "RGBA")


def clip_palette(images, colors=56):
    pixels = []
    for image in images:
        small = np.array(image.convert("RGBa").resize(SIZE, Image.Resampling.BOX).convert("RGBA"))
        pixels.append(small[small[..., 3] > 110][:, :3])
    stack = np.concatenate(pixels)
    return Image.fromarray(stack.reshape(-1, 1, 3), "RGB").quantize(colors, method=Image.Quantize.MEDIANCUT, kmeans=4)


def process(name, video):
    ident, _, start, end, cycle = CLIPS[name]
    cutouts = video_cutouts(video)
    slots = list(range(start, end + 1))
    targets = [target_mask(s) for s in slots]
    masks = [small_alpha(c) for c in cutouts]
    # One fixed offset per clip: the camera is locked, so per-frame shifts would only add jitter.
    probe = masks[::6]
    best = max(((dx, dy) for dx in range(-8, 9, 2) for dy in range(-8, 9, 2)),
               key=lambda d: sum(max(iou(m, t, *d) for m in probe) for t in targets[::2]))
    scores = np.array([[iou(m, t, *best) for m in masks] for t in targets])
    picks = choose(scores, cycle)
    chosen = [cutouts[i] for i in picks]
    palette = clip_palette(chosen)
    folder = OUT / name
    (folder / "soft").mkdir(parents=True, exist_ok=True)
    (folder / "crisp").mkdir(parents=True, exist_ok=True)
    for slot, image in zip(slots, chosen):
        for label, small in (("soft", soft(image)), ("crisp", crisp(image, palette))):
            world = Image.new("RGBA", (500, 500))
            world.paste(small, (ORIGIN[0] + best[0], ORIGIN[1] + best[1]))
            world.save(folder / label / f"{slot:04d}.png")
    report = dict(clip=name, video=str(video), offset=best, picks=picks,
                  overlap=[round(float(scores[k, f]), 3) for k, f in enumerate(picks)],
                  mean_overlap=round(float(np.mean([scores[k, f] for k, f in enumerate(picks)])), 3))
    (folder / "report.json").write_text(json.dumps(report, indent=1), "utf-8")
    print(json.dumps({k: report[k] for k in ("clip", "offset", "mean_overlap", "picks")}), flush=True)


if __name__ == "__main__":
    for line in sys.stdin:
        row = json.loads(line)
        process(row["clip"], row["video"])
