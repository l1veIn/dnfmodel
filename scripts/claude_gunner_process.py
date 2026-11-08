"""Video to native frames for the Claude gunner patch.

Shares matting and downscaling with the Fatfish v06 pipeline. The difference is scoring: her gown and
hair are far larger than the source costume, so pixels outside the sprite cost much less than missing
it, otherwise frame choice and scale fit would simply favor the smallest figure.

Usage (ComfyUI venv python):
  claude_gunner_process.py clip <id> [--attempt=N]   choose frames for clips
  claude_gunner_process.py final                     ground, borrow and render everything with one palette
  claude_gunner_process.py sheet <id> ...            review sheets for clips (native / new / new with gun)
"""
from __future__ import annotations

import json
import shutil
import sys

import av
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from claude_gunner import OUT, RUN, figure_mask, native_world, weapon_world
from claude_gunner_gen import clips
from claude_gunner_hands import fit_clip, graft
from fatfish_final_post import build_palette, downscale, finish, grade, sharpen
from fatfish_final_process import looping, matte, monotonic, placed_mask, placement

SCALES = np.arange(0.60, 1.13, 0.02)
OUTSIDE_COST = 0.3
PAD = 200
REACH = 14
BAND = 0.2
MARGIN = 6


def shape_score(generated, target):
    hit = (generated & target).sum()
    return hit / max(target.sum() + OUTSIDE_COST * (generated & ~target).sum(), 1)


def best_shift(generated, target, reach, step):
    best = (-1.0, 0, 0)
    for dy in range(-reach, reach + 1, step):
        for dx in range(-reach, reach + 1, step):
            value = shape_score(np.roll(np.roll(generated, dy, 0), dx, 1), target)
            if value > best[0]:
                best = (float(value), dx, dy)
    return best


def process_clip(ident, attempt=1, first_frame=12):
    """first_frame skips the start of the video, where the model is still holding its reference pose."""
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
    track = reference["shifts"]
    # Compare in the camera's coordinates; the shift returns when the frame is placed.
    targets = [np.roll(np.roll(figure_mask(s), -track[str(s)][1], 0), -track[str(s)][0], 1) for s in range(start, end + 1)]
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
    picks = looping(scores) if "loop" in clip else monotonic(scores)
    raw = []
    for pick, target in zip(picks, targets):
        options = [s for s in SCALES if abs(s - base) <= 0.1001]
        raw.append(max(options, key=lambda s: best_shift(placed_mask(alphas[pick], window, float(s), base_dx, base_dy), target, 6, 3)[0]))
    smooth = ndimage.median_filter(np.array(raw, float), size=min(5, max(1, len(raw) | 1)), mode="nearest")
    if "loop" in clip:
        smooth[:] = np.median(raw)
    records = []
    out = OUT / "clips" / ident
    (out / "hd").mkdir(parents=True, exist_ok=True)
    for slot, pick, target, scale in zip(range(start, end + 1), picks, targets, smooth):
        placed = placed_mask(alphas[pick], window, float(scale), base_dx, base_dy)
        value, dx, dy = best_shift(placed, target, 6, 1)
        frames[pick].save(out / f"hd/{slot:04d}.png")
        records.append(dict(slot=slot, video_frame=pick, scale=round(float(scale), 3), offset=[base_dx + dx, base_dy + dy], track=track[str(slot)], score=round(value, 3)))
    shifts = np.array([r["offset"] for r in records], float)
    calm = ndimage.median_filter(shifts, size=(min(3, len(records) | 1), 1), mode="nearest")
    for row, shift in zip(records, calm):
        row["offset"] = [int(shift[0]), int(shift[1])]
    report = dict(clip=ident, attempt=attempt, window=window, base_scale=base, frames=records, mean_score=round(float(np.mean([r["score"] for r in records])), 3))
    (out / "selection.json").write_text(json.dumps(report, indent=1), "utf-8")
    print(json.dumps(dict(clip=ident, attempt=attempt, base=round(base, 2), mean=report["mean_score"], picks=picks, scales=[r["scale"] for r in records]), ensure_ascii=False), flush=True)


def graded(ident, row, window):
    fitted = OUT / "clips" / ident / f"hdfit/{row['slot']:04d}.png"
    hd = Image.open(fitted if fitted.exists() else OUT / "clips" / ident / f"hd/{row['slot']:04d}.png").convert("RGBA")
    size = int(round(window[2] * row["scale"]))
    color, a = downscale(hd, (size, size))
    return sharpen(grade(color)), a


def render_clip(ident, palette=None, hands=False):
    report = json.loads((OUT / "clips" / ident / "selection.json").read_text("utf-8"))
    window = report["window"]
    (OUT / "native_frames").mkdir(parents=True, exist_ok=True)
    for row in report["frames"]:
        color, a = graded(ident, row, window)
        sprite = finish(color, a, palette)
        left, top = placement(window, row["scale"], row["offset"][0] + row["track"][0], row["offset"][1] + row["track"][1])
        world = Image.new("RGBA", (500 + PAD * 2, 500 + PAD * 2))
        world.paste(sprite, (left + PAD, top + PAD))
        result = world.crop((PAD, PAD, PAD + 500, PAD + 500))
        if hands:
            result = graft(result, row["slot"], palette)
        result.save(OUT / f"native_frames/{row['slot']:04d}.png")


def collect_palette(idents, count=96):
    samples = []
    for ident in idents:
        report = json.loads((OUT / "clips" / ident / "selection.json").read_text("utf-8"))
        for row in report["frames"][::3]:
            samples.append(graded(ident, row, report["window"]))
    return build_palette(samples, count)


def sole_shift(alpha, target):
    """Vertical shift that puts her soles on the sprite's soles, looking only under the sprite's lower body."""
    rows = np.nonzero(target.any(1))[0]
    bottom, height = int(rows.max()), int(rows.max() - rows.min() + 1)
    band = target[bottom - int(height * BAND):bottom + 1]
    columns = np.nonzero(band.any(0))[0]
    left, right = int(columns.min()) - MARGIN, int(columns.max()) + MARGIN + 1
    found = np.nonzero(alpha[:, left:right].any(1))[0]
    if not len(found):
        return 0
    dy = bottom - int(found.max())
    return dy if abs(dy) <= REACH else 0


def final(idents):
    for name in idents:
        path = OUT / "clips" / name / "selection.json"
        report = json.loads(path.read_text("utf-8"))
        for row in report["frames"]:
            if "offset_before_ground" in row:
                row["offset"] = row["offset_before_ground"]
        path.write_text(json.dumps(report, indent=1), "utf-8")
        shutil.rmtree(OUT / "clips" / name / "hdfit", ignore_errors=True)
    palette = collect_palette(idents)
    moved = {}
    for name in idents:
        render_clip(name, palette)
        path = OUT / "clips" / name / "selection.json"
        report = json.loads(path.read_text("utf-8"))
        raw = []
        for row in report["frames"]:
            alpha = np.asarray(Image.open(OUT / f"native_frames/{row['slot']:04d}.png").getchannel("A")) > 128
            raw.append(sole_shift(alpha, figure_mask(row["slot"])))
        calm = ndimage.median_filter(np.array(raw), size=min(3, len(raw) | 1), mode="nearest")
        for row, dy in zip(report["frames"], calm):
            row["offset_before_ground"] = row.get("offset_before_ground", row["offset"])
            row["offset"] = [row["offset"][0], row["offset"][1] + int(dy)]
            if dy:
                moved[row["slot"]] = int(dy)
        path.write_text(json.dumps(report, indent=1), "utf-8")
        # Hands last, because they need the final grounded position.
        for slot, hands in fit_clip(name):
            print("hands", slot, hands, flush=True)
        render_clip(name, palette, hands=True)
    print("grounded", len(moved), "largest", max(moved.values(), key=abs, default=0))
    borrow_path = OUT / "borrow.json"
    for slot, source in (json.loads(borrow_path.read_text("utf-8")) if borrow_path.exists() else {}).items():
        shutil.copy2(OUT / f"native_frames/{int(source):04d}.png", OUT / f"native_frames/{int(slot):04d}.png")
        print("borrowed", slot, "<-", source)


def sheet(ident, zoom=2, width=170, height=160):
    start, end = int(ident.split("_")[1]), int(ident.split("_")[2])
    frames = list(range(start, end + 1))
    cols = min(10, len(frames))
    rows = (len(frames) + cols - 1) // cols
    board = Image.new("RGB", (cols * width * zoom, rows * 3 * height * zoom), (86, 97, 122))
    draw = ImageDraw.Draw(board)
    for k, i in enumerate(frames):
        native = native_world(i)
        box = native.getbbox()
        cx = (box[0] + box[2]) // 2
        crop = (cx - width // 2, 348 - height, cx + width // 2, 348)
        new = Image.open(OUT / f"native_frames/{i:04d}.png").convert("RGBA")
        armed = new.copy()
        armed.alpha_composite(weapon_world(i))
        x, y = (k % cols) * width * zoom, (k // cols) * 3 * height * zoom
        for row, image in enumerate((native, new, armed)):
            big = image.crop(crop).resize((width * zoom, height * zoom), Image.NEAREST)
            board.paste(big, (x, y + row * height * zoom), big)
        draw.text((x + 3, y + 2), str(i), fill="yellow")
    (OUT / "qa").mkdir(parents=True, exist_ok=True)
    board.save(OUT / f"qa/{start:03d}_{end:03d}.png")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    action, args = sys.argv[1], sys.argv[2:]
    attempt = next((int(a.split("=")[1]) for a in args if a.startswith("--attempt=")), 1)
    names = [a for a in args if not a.startswith("--")]
    if action == "clip":
        for name in names:
            process_clip(name, attempt)
    elif action == "final":
        final(names or [c["id"] for c in clips() if (OUT / "clips" / c["id"] / "selection.json").exists()])
    else:
        for name in names or [c["id"] for c in clips()]:
            sheet(name)
