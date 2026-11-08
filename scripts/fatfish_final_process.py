"""Video -> native frames for v06: pose-matched frame choice, scale and position fit, crisp downscale.

Frame choice compares each video frame to the native sprite minus its hair and hat, so a wrong
pose cannot win just by sitting at the expected time. The model also drifts in scale during a
clip, so each chosen frame gets a fitted, smoothed scale. Run with the ComfyUI venv python.
"""
from __future__ import annotations

import json
import sys

import av
import numpy as np
from PIL import Image
from scipy import ndimage

from fatfish_doll import ROOT, layer_world
from fatfish_final import OUT, RUN, clips
from fatfish_final_post import build_palette, downscale, finish, grade, sharpen

FIGURE = ("mg_body0000", "mg_coat0000a", "mg_coat0000b", "mg_coat0000c", "mg_pants0000a", "mg_shoes0000a", "mg_shoes0000b")
LOOPING = {0, 10, 14, 18, 53, 155, 163}
SCALES = np.arange(0.76, 1.13, 0.02)
PAD = 200


def matte(frame):
    """Cut the flat gray background; keep the main figure and things close to it."""
    rgb = np.asarray(frame.convert("RGB"), np.float32)
    border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3), rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
    background = np.median(border, axis=0)
    distance = np.abs(rgb - background).max(2)
    chroma = rgb.max(2) - rgb.min(2)
    luma = rgb.mean(2)
    solid = (distance > 12) & ((chroma > 10) | (luma > 185) | (luma < 62))
    solid = ndimage.binary_opening(solid, iterations=1)
    labels, count = ndimage.label(solid, structure=np.ones((3, 3)))
    if not count:
        raise RuntimeError("no subject")
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    main = sizes.argmax()
    near = ndimage.binary_dilation(labels == main, iterations=10)
    keep = np.isin(labels, np.unique(labels[near & (labels > 0)]))
    keep &= sizes[labels] >= 60
    # Small holes are shaded fabric the keying missed; real gaps between limbs are much larger.
    holes = ndimage.binary_fill_holes(keep) & ~keep
    hole_labels, hole_count = ndimage.label(holes)
    if hole_count:
        hole_sizes = np.bincount(hole_labels.ravel())
        keep |= (hole_sizes[hole_labels] < 260) & (hole_labels > 0)
    alpha = np.clip(ndimage.gaussian_filter(keep.astype(np.float32), 0.7) * 1.15, 0, 1) * ndimage.binary_dilation(keep)
    out = np.zeros((*keep.shape, 4), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = (alpha * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def figure_mask(slot):
    mask = np.zeros((500, 500), bool)
    for layer in FIGURE:
        mask |= np.asarray(layer_world(layer, slot))[..., 3] > 0
    return mask


def placed_mask(alpha, window, scale, dx=0, dy=0):
    """Generated alpha at native scale in world coordinates, scaled about the window's bottom center."""
    x, y, side = window
    size = int(round(side * scale))
    small = np.asarray(alpha.resize((size, size), Image.Resampling.BOX)) > 110
    left, top = placement(window, scale, dx, dy)
    world = np.zeros((500 + PAD * 2, 500 + PAD * 2), bool)
    world[top + PAD:top + PAD + size, left + PAD:left + PAD + size] = small
    return world[PAD:PAD + 500, PAD:PAD + 500]


def placement(window, scale, dx=0, dy=0):
    x, y, side = window
    size = int(round(side * scale))
    return int(round(x + side / 2 - size / 2)) + dx, y + side - size + dy


def shape_score(generated, target):
    """Overlap with the sprite. Hair and tail may extend behind her; anything else counts against."""
    xs = np.nonzero(target.any(0))[0]
    rear = np.zeros_like(target)
    rear[:, :max(xs.min() - 2, 0)] = True
    considered = generated & ~rear
    union = (considered | target).sum()
    return (considered & target).sum() / max(union, 1)


def best_shift(generated, target, reach, step):
    best = (-1.0, 0, 0)
    for dy in range(-reach, reach + 1, step):
        for dx in range(-reach, reach + 1, step):
            value = shape_score(np.roll(np.roll(generated, dy, 0), dx, 1), target)
            if value > best[0]:
                best = (float(value), dx, dy)
    return best


def monotonic(scores):
    slots, frames = scores.shape
    best = scores[0].copy()
    back = np.zeros((slots, frames), int)
    for k in range(1, slots):
        top = np.maximum.accumulate(best)
        where = np.zeros(frames, int)
        pick = 0
        for f in range(frames):
            if best[f] >= best[pick]:
                pick = f
            where[f] = pick
        best = top + scores[k]
        back[k] = where
    path = [int(best.argmax())]
    for k in range(slots - 1, 0, -1):
        path.append(int(back[k, path[-1]]))
    return path[::-1]


def looping(scores):
    slots, frames = scores.shape
    best = None
    for period in range(max(12, slots * 2), 66):
        for start in range(6, frames - period):
            picks = [start + round(k * period / slots) for k in range(slots)]
            value = sum(scores[k, picks[k]] for k in range(slots))
            if best is None or value > best[0]:
                best = (value, picks)
    return best[1]


def process_clip(ident, attempt=1, first_frame=0):
    """first_frame excludes the start of the video when the model is still holding its reference pose there."""
    folder = RUN / "jobs" / ident / f"attempt_{attempt:02d}"
    reference = json.loads((folder / "reference.json").read_text("utf-8"))
    job = json.loads((folder / "job.json").read_text("utf-8"))
    clip, window = reference["clip"], reference["window"]
    start, end = clip["start"], clip["end"]
    frames = []
    with av.open(job["stages"][0]["videos"][0]) as video:
        for frame in video.decode(video=0):
            frames.append(matte(frame.to_image()))
    alphas = [f.getchannel("A") for f in frames]
    targets = [figure_mask(s) for s in range(start, end + 1)]
    # Clip-wide scale and offset from a sample, then every frame scored against every slot.
    samples = list(range(0, 124, 8))
    probes = targets[:: max(1, len(targets) // 5)]

    def clip_fit(scale):
        placed = [placed_mask(alphas[i], window, scale) for i in samples]
        total, shifts = 0.0, []
        for target in probes:
            value, dx, dy = max((best_shift(m, target, 8, 4) for m in placed), key=lambda r: r[0])
            total += value
            shifts.append((dx, dy))
        return total, int(np.median([s[0] for s in shifts])), int(np.median([s[1] for s in shifts]))

    fits = {float(s): clip_fit(float(s)) for s in SCALES[::2]}
    base = max(fits, key=lambda s: fits[s][0])
    base_dx, base_dy = fits[base][1], fits[base][2]
    masks = [placed_mask(a, window, base, base_dx, base_dy) for a in alphas]
    scores = np.array([[shape_score(m, t) for m in masks] for t in targets])
    scores[:, :first_frame] = -1.0
    picks = looping(scores) if start in LOOPING else monotonic(scores)
    # Per-frame scale fit, smoothed: wobble goes away, a real change across the clip remains.
    raw = []
    for pick, target in zip(picks, targets):
        options = [s for s in SCALES if abs(s - base) <= 0.1001]
        raw.append(max(options, key=lambda s: best_shift(placed_mask(alphas[pick], window, float(s), base_dx, base_dy), target, 6, 3)[0]))
    smooth = ndimage.median_filter(np.array(raw, float), size=min(5, max(1, len(raw) | 1)), mode="nearest")
    records = []
    out = OUT / "clips" / ident
    (out / "hd").mkdir(parents=True, exist_ok=True)
    for slot, pick, target, scale in zip(range(start, end + 1), picks, targets, smooth):
        placed = placed_mask(alphas[pick], window, float(scale), base_dx, base_dy)
        value, dx, dy = best_shift(placed, target, 6, 1)
        frames[pick].save(out / f"hd/{slot:04d}.png")
        records.append(dict(slot=slot, video_frame=pick, scale=round(float(scale), 3), offset=[base_dx + dx, base_dy + dy], score=round(value, 3)))
    # A shift that jumps against its neighbours is wobble, not motion.
    shifts = np.array([r["offset"] for r in records], float)
    calm = ndimage.median_filter(shifts, size=(min(3, len(records) | 1), 1), mode="nearest")
    for row, shift in zip(records, calm):
        row["offset"] = [int(shift[0]), int(shift[1])]
    report = dict(clip=ident, attempt=attempt, window=window, base_scale=base, video=job["stages"][0]["videos"][0], frames=records,
                  mean_score=round(float(np.mean([r["score"] for r in records])), 3))
    (out / "selection.json").write_text(json.dumps(report, indent=1), "utf-8")
    print(json.dumps(dict(clip=ident, base=round(base, 2), mean=report["mean_score"], worst=min(r["score"] for r in records),
                          picks=picks, scales=[r["scale"] for r in records]), ensure_ascii=False), flush=True)
    return report


def repick(ident, attempt, choices):
    """Replace chosen video frames by hand, e.g. to avoid a spell effect the model drew. choices: {slot: video_frame}."""
    job = json.loads((RUN / "jobs" / ident / f"attempt_{attempt:02d}/job.json").read_text("utf-8"))
    path = OUT / "clips" / ident / "selection.json"
    report = json.loads(path.read_text("utf-8"))
    frames = {}
    with av.open(job["stages"][0]["videos"][0]) as video:
        for index, frame in enumerate(video.decode(video=0)):
            if index in choices.values():
                frames[index] = matte(frame.to_image())
    for row in report["frames"]:
        if row["slot"] not in choices:
            continue
        pick = choices[row["slot"]]
        base = row.get("offset_before_ground", row["offset"])
        placed = placed_mask(frames[pick].getchannel("A"), report["window"], row["scale"], *base)
        value, dx, dy = best_shift(placed, figure_mask(row["slot"]), 6, 1)
        frames[pick].save(OUT / "clips" / ident / f"hd/{row['slot']:04d}.png")
        row.update(video_frame=pick, score=round(value, 3), offset=[base[0] + dx, base[1] + dy])
        row.pop("offset_before_ground", None)
    path.write_text(json.dumps(report, indent=1), "utf-8")


def graded(ident, row, window):
    hd = Image.open(OUT / "clips" / ident / f"hd/{row['slot']:04d}.png").convert("RGBA")
    size = int(round(window[2] * row["scale"]))
    color, a = downscale(hd, (size, size))
    return sharpen(grade(color)), a


def render_clip(ident, palette=None):
    """Write native world frames for a processed clip."""
    report = json.loads((OUT / "clips" / ident / "selection.json").read_text("utf-8"))
    window = report["window"]
    (OUT / "native_frames").mkdir(parents=True, exist_ok=True)
    for row in report["frames"]:
        color, a = graded(ident, row, window)
        sprite = finish(color, a, palette)
        left, top = placement(window, row["scale"], *row["offset"])
        world = Image.new("RGBA", (500 + PAD * 2, 500 + PAD * 2))
        world.paste(sprite, (left + PAD, top + PAD))
        world.crop((PAD, PAD, PAD + 500, PAD + 500)).save(OUT / f"native_frames/{row['slot']:04d}.png")


def collect_palette(idents, count=96):
    samples = []
    for ident in idents:
        report = json.loads((OUT / "clips" / ident / "selection.json").read_text("utf-8"))
        for row in report["frames"][::3]:
            samples.append(graded(ident, row, report["window"]))
    return build_palette(samples, count)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    names = [a for a in sys.argv[1:] if not a.startswith("--attempt=")]
    attempt = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--attempt=")), 1)
    for name in names:
        process_clip(name, attempt)
    palette = collect_palette(names)
    for name in names:
        render_clip(name, palette)
