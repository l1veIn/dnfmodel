"""Clip selections to finished sprites: frame choice from video, cleanup passes, grounding, palette, hand fit."""
from __future__ import annotations

import json
import shutil

import av
import numpy as np
from PIL import Image
from scipy import ndimage

from .art import build_palette, downscale, finish, grade, looping, matte, monotonic, placed_mask, placement, sharpen
from .config import P
from .hands import fit_clip, graft
from .source import figure_mask, layer_world, native_world

SCALES = np.arange(0.60, 1.13, 0.02)
OUTSIDE_COST = 0.3
PAD = 200
REACH = 14
BAND = 0.2
MARGIN = 6
STEP = 3
CLIPS = P.out / "clips"
FRAMES_DIR = P.out / "native_frames"


def shape_score(generated, target):
    """A costume and hair larger than the source sprite should cost little, or fitting would favor the smallest figure."""
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


def selection(ident):
    return json.loads((CLIPS / ident / "selection.json").read_text("utf-8"))


def store(ident, report):
    (CLIPS / ident / "selection.json").write_text(json.dumps(report, indent=1), "utf-8")


def process_clip(ident, attempt=1, first_frame=12):
    """first_frame skips the start of the video, where the model is still holding its reference pose."""
    folder = P.run / "jobs" / ident / f"attempt_{attempt:02d}"
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
    records = []
    out = CLIPS / ident
    (out / "hd").mkdir(parents=True, exist_ok=True)
    for slot, pick, target in zip(range(start, end + 1), picks, targets):
        placed = placed_mask(alphas[pick], window, float(base), base_dx, base_dy)
        value, dx, dy = best_shift(placed, target, 6, 1)
        frames[pick].save(out / f"hd/{slot:04d}.png")
        records.append(dict(slot=slot, video_frame=pick, scale=round(float(base), 3), offset=[base_dx + dx, base_dy + dy], track=track[str(slot)], score=round(value, 3)))
    shifts = np.array([r["offset"] for r in records], float)
    calm = ndimage.median_filter(shifts, size=(min(3, len(records) | 1), 1), mode="nearest")
    for row, shift in zip(records, calm):
        row["offset"] = [int(shift[0]), int(shift[1])]
    report = dict(clip=ident, attempt=attempt, window=window, base_scale=base, frames=records, mean_score=round(float(np.mean([r["score"] for r in records])), 3))
    store(ident, report)
    print(json.dumps(dict(clip=ident, attempt=attempt, base=round(base, 2), mean=report["mean_score"], picks=picks), ensure_ascii=False), flush=True)


def split(ident, *ranges):
    """Carve kept frames out of a clip once its other frames moved to a sheet. Ranges look like 14-20."""
    report = selection(ident)
    for text in ranges:
        start, end = map(int, text.split("-"))
        name = f"clip_{start:03d}_{end:03d}"
        (CLIPS / name / "hd").mkdir(parents=True, exist_ok=True)
        rows = [r for r in report["frames"] if start <= r["slot"] <= end]
        for row in rows:
            shutil.copy2(CLIPS / ident / f"hd/{row['slot']:04d}.png", CLIPS / name / f"hd/{row['slot']:04d}.png")
        store(name, dict(report, clip=name, source_clip=report.get("source_clip", ident), frames=rows))
    shutil.rmtree(CLIPS / ident)


def refit(row, ident, window, scale):
    alpha = Image.open(CLIPS / ident / f"hd/{row['slot']:04d}.png").getchannel("A")
    offset = row.get("offset_before_ground", row["offset"])
    target = np.roll(np.roll(figure_mask(row["slot"]), -row["track"][1], 0), -row["track"][0], 1)
    placed = placed_mask(alpha, window, scale, offset[0], offset[1])
    _, dx, dy = best_shift(placed, target, 8, 1)
    return [offset[0] + dx, offset[1] + dy]


def match_sizes(most=1.03, goal=0.99):
    """Video clips drawn taller than the sheets pop in size at the cut; bring upright ones to the sheets' height against the sprite. Needs rendered frames."""
    for clip in P.clips():
        ident = clip["id"]
        report = selection(ident)
        if "sheet" in report:
            continue
        ratios = []
        for row in report["frames"]:
            box = Image.open(FRAMES_DIR / f"{row['slot']:04d}.png").getchannel("A").getbbox()
            native = native_world(row["slot"]).getbbox()
            ratios.append((box[3] - box[1]) / (native[3] - native[1]))
        typical = float(np.median(ratios))
        if typical <= most or max(ratios) - min(ratios) > 0.1:
            continue
        scale = round(report["frames"][0]["scale"] * goal / typical, 3)
        for row in report["frames"]:
            row["offset"] = refit(row, ident, report["window"], scale)
            row.pop("offset_before_ground", None)
            row["scale"] = scale
        print(ident, "height", round(typical, 3), "scale ->", scale)
        store(ident, report)


def unfreeze():
    """A repeated video frame freezes her; the neighboring frames hold the pose while hair and cloth keep moving."""
    for clip in P.clips():
        ident = clip["id"]
        report = selection(ident)
        if "sheet" in report:
            continue
        rows = report["frames"]
        picks = [r["video_frame"] for r in rows]
        if len(set(picks)) == len(picks):
            continue
        folder = P.run / "jobs" / report.get("source_clip", ident) / f"attempt_{report['attempt']:02d}"
        job = json.loads((folder / "job.json").read_text("utf-8"))
        with av.open(job["stages"][0]["videos"][0]) as video:
            frames = [f.to_image() for f in video.decode(video=0)]
        new = list(picks)
        i = 0
        while i < len(new):
            j = i
            while j + 1 < len(new) and picks[j + 1] == picks[i]:
                j += 1
            if j > i:
                ceiling = picks[j + 1] - 1 if j + 1 < len(picks) else len(frames) - 1
                floor = new[i - 1] + 1 if i else 12
                span = (j - i) * STEP
                first = int(np.clip(picks[i] - span // 2, floor, max(floor, ceiling - span)))
                for k in range(i, j + 1):
                    new[k] = min(first + (k - i) * STEP, ceiling)
            i = j + 1
        for row, pick, old in zip(rows, new, picks):
            if pick != old:
                matte(frames[pick]).save(CLIPS / ident / f"hd/{row['slot']:04d}.png")
                row["video_frame"] = pick
        print(ident, picks, "->", new)
        store(ident, report)


def graded(ident, row, window):
    fitted = CLIPS / ident / f"hdfit/{row['slot']:04d}.png"
    hd = Image.open(fitted if fitted.exists() else CLIPS / ident / f"hd/{row['slot']:04d}.png").convert("RGBA")
    size = int(round(window[2] * row["scale"]))
    color, a = downscale(hd, (size, size))
    return sharpen(grade(color)), a


def render_clip(ident, palette=None, hands=False):
    report = selection(ident)
    window = report["window"]
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    side = P.canvas
    for row in report["frames"]:
        color, a = graded(ident, row, window)
        sprite = finish(color, a, palette)
        left, top = placement(window, row["scale"], row["offset"][0] + row["track"][0], row["offset"][1] + row["track"][1])
        world = Image.new("RGBA", (side + PAD * 2, side + PAD * 2))
        world.paste(sprite, (left + PAD, top + PAD))
        result = world.crop((PAD, PAD, PAD + side, PAD + side))
        if hands:
            result = graft(result, row["slot"], palette)
        result.save(FRAMES_DIR / f"{row['slot']:04d}.png")


def collect_palette(idents, count=96):
    samples = []
    for ident in idents:
        report = selection(ident)
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


def _match(reference, moving, rows, reach=8):
    """The shift that lays `moving` over `reference` in these rows, by color."""
    a = reference[rows[0]:rows[1]].astype(np.int32)
    best, score = (0, 0), float("inf")
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            b = np.roll(np.roll(moving, dy, 0), dx, 1)[rows[0]:rows[1]].astype(np.int32)
            solid = (a[..., 3] > 128) | (b[..., 3] > 128)
            cost = (np.abs(a - b).max(2) * solid).sum() / max(solid.sum(), 1) + 0.5 * (abs(dx) + abs(dy))
            if cost < score:
                best, score = (dx, dy), cost
    return best


def head_shifts(slots, head_px=16, drawn_px=24):
    """For a clip whose head should stay as steady as the source's. Soles are the wrong anchor there: a sprite that lifts its feet then pushes her head up, and every frame jitters.

    Returns the shift that puts each frame's head where the source's head goes, relative to the clip's first frame.
    """
    source = {i: np.asarray(layer_world(P.body, i)) for i in slots}
    drawn = {i: np.asarray(Image.open(FRAMES_DIR / f"{i:04d}.png").convert("RGBA")) for i in slots}
    first = slots[0]
    rows = np.nonzero((source[first][..., 3] > 0).any(1))[0]
    source_rows = (int(rows.min()), int(rows.min()) + head_px)
    rows = np.nonzero((drawn[first][..., 3] > 128).any(1))[0]
    drawn_rows = (int(rows.min()), int(rows.min()) + drawn_px)
    shifts = {}
    for i in slots:
        sx, sy = _match(source[first], source[i], source_rows)
        nx, ny = _match(drawn[first], drawn[i], drawn_rows)
        shifts[i] = (nx - sx, ny - sy)
    return shifts


def final(idents=None):
    idents = idents or [c["id"] for c in P.clips() if (CLIPS / c["id"] / "selection.json").exists()]
    anchored = {c["id"]: c for c in P.clips() if c.get("anchor") == "head"}
    for name in idents:
        report = selection(name)
        for row in report["frames"]:
            if "offset_before_ground" in row:
                row["offset"] = row["offset_before_ground"]
        store(name, report)
        shutil.rmtree(CLIPS / name / "hdfit", ignore_errors=True)
    palette = collect_palette(idents)
    moved, stretched, unreachable, fits = {}, [], [], {}
    for name in idents:
        render_clip(name, palette)
        report = selection(name)
        raw = []
        for row in report["frames"]:
            alpha = np.asarray(Image.open(FRAMES_DIR / f"{row['slot']:04d}.png").getchannel("A")) > 128
            raw.append(sole_shift(alpha, figure_mask(row["slot"])))
        calm = ndimage.median_filter(np.array(raw), size=min(3, len(raw) | 1), mode="nearest")
        for row, dy in zip(report["frames"], calm):
            row["offset_before_ground"] = row.get("offset_before_ground", row["offset"])
            row["offset"] = [row["offset"][0], row["offset"][1] + int(dy)]
            if dy:
                moved[row["slot"]] = int(dy)
        if name in anchored:
            # Only the first frame stands on the sole; the rest follow its head.
            # "anchor_px": horns or hair blown above the head fill the top rows, so match a taller band that reaches the face.
            shifts = head_shifts([row["slot"] for row in report["frames"]], drawn_px=anchored[name].get("anchor_px", 24))
            ground = int(calm[0])
            for row in report["frames"]:
                dx, dy = shifts[row["slot"]]
                row["offset"] = [row["offset_before_ground"][0] + dx, row["offset_before_ground"][1] + dy + ground]
            print("head anchored", name, {s: v for s, v in shifts.items()}, flush=True)
        store(name, report)
        # Hands last, because they need the final grounded position.
        for slot, hands in fit_clip(name):
            print("hands", slot, hands, flush=True)
            for hand in hands:
                fits[hand.get("state")] = fits.get(hand.get("state"), 0) + 1
                if hand.get("state") == "too far":
                    unreachable.append(slot)
                elif hand.get("gap", 0) > 12:
                    stretched.append((slot, hand["gap"]))
        render_clip(name, palette, hands=True)
    # design/<id>/reuse.json, {"26": 22}: a frame the source repeats is the same picture here too, so it cannot flicker or differ in size.
    reuse = P.run / "reuse.json"
    if reuse.exists():
        for target, origin in json.loads(reuse.read_text("utf-8")).items():
            shutil.copyfile(FRAMES_DIR / f"{origin:04d}.png", FRAMES_DIR / f"{int(target):04d}.png")
    print("grounded", len(moved), "largest", max(moved.values(), key=abs, default=0))
    # A long stretch can drag the head or feet, and the log above is too long to notice it. Look at these frames.
    print("arm stretched over 12px, check by eye:", stretched)
    print("hand too far, left as drawn, redraw if it shows:", unreachable)
    print("how hands were fitted:", fits)
    # "nearest" drags whatever edge is closest, and "no hand near" does not move anything: most of either means her skin is not being recognized.
    weak = fits.get("nearest", 0) + fits.get("no hand near", 0)
    if weak > 0.3 * max(sum(fits.values()), 1):
        print(f"WARNING {weak} of {sum(fits.values())} hands were not recognized: measure her hand's RGB on the master and set skin_rule in patch.json, then run final again")
