"""Boards for checking by eye, and numbers for what the eye misses. Look at these before showing anything to the user."""
from __future__ import annotations

import colorsys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from .config import P
from .hands import sprite_hands
from .source import armed, figure_mask, layer_world, native_world, weapon_layers


def frames_from(spec):
    frames = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        frames += list(range(int(a), int(b or a) + 1))
    return frames


def _dev():
    (P.out / "dev").mkdir(parents=True, exist_ok=True)
    return P.out / "dev"


def _save_path(name):
    """Boards live in dev/; a folder given by mistake must not double it."""
    return _dev() / Path(name).name


def _new(i):
    return Image.open(P.out / f"native_frames/{i:04d}.png").convert("RGBA")


def board(name, spec, cols=8, zoom=3, width=170, height=170):
    """Source above, new below, both with the weapon, on a crop that follows the source sprite."""
    frames = frames_from(spec)
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width * zoom, rows * 2 * height * zoom), (86, 97, 122))
    draw = ImageDraw.Draw(sheet)
    for k, i in enumerate(frames):
        native = native_world(i)
        box = native.getbbox()
        cx = (box[0] + box[2]) // 2
        crop = (cx - width // 2, box[3] + 12 - height, cx + width // 2, box[3] + 12)
        x, y = (k % cols) * width * zoom, (k // cols) * 2 * height * zoom
        for row, image in enumerate((armed(native, i), armed(_new(i), i))):
            big = image.crop(crop).resize((width * zoom, height * zoom), Image.NEAREST)
            sheet.paste(big, (x, y + row * height * zoom), big)
        draw.text((x + 3, y + 2), f"{i} (user {i + 1})", fill="yellow")
    path = _save_path(name)
    sheet.save(path)
    print(path)


def hands_board(name, spec=None, cols=8, zoom=5, side=56):
    """Close-up of every armed hand. With no finished frames yet, shows only the source with the detected hand marked, to catch false hands."""
    frames = frames_from(spec) if spec else list(range(P.frames))
    items = [(i, n, h) for i in frames for n, h in enumerate(sprite_hands(i))]
    if not items:
        raise SystemExit("no armed hands in these frames")
    finished = (P.out / "native_frames/0000.png").exists()
    cell = side * zoom
    columns = 2 if finished else 1
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell * columns + 8), rows * (cell + 8)), (86, 97, 122))
    pen = ImageDraw.Draw(sheet)
    for k, (i, n, h) in enumerate(items):
        x, y = (k % cols) * (cell * columns + 8), (k // cols) * (cell + 8)
        cx, cy = int(h[0]), int(h[1])
        crop = (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
        for col, image in enumerate((native_world(i), _new(i)) if finished else (native_world(i),)):
            big = armed(image, i).crop(crop).resize((cell, cell), Image.NEAREST)
            sheet.paste(big, (x + col * cell, y), big)
        if not finished:
            pen.ellipse((x + cell // 2 - 6, y + cell // 2 - 6, x + cell // 2 + 6, y + cell // 2 + 6), outline=(255, 60, 60), width=2)
        pen.text((x + 3, y + 2), f"{i}.{n}", fill="yellow")
    path = _save_path(name)
    sheet.save(path)
    print(len(items), "hands in", len({i for i, _, _ in items}), "frames", path)


def stats():
    """Per clip: height against the sprite (a jump between neighbors is a visible pop), sole gap, cover, and frozen runs."""
    gaps, covers, tall, frozen = [], [], [], []
    previous = None
    for clip in P.clips():
        ratios, soles, cover = [], [], []
        for i in range(clip["start"], clip["end"] + 1):
            # A trial run composites only some clips.
            if not (P.out / f"native_frames/{i:04d}.png").exists():
                continue
            pixels = np.asarray(_new(i))
            alpha = pixels[..., 3] > 128
            rows = np.nonzero(alpha.any(1))[0]
            target = figure_mask(i)
            target_rows = np.nonzero(target.any(1))[0]
            native = native_world(i).getbbox()
            ratio = (rows.max() - rows.min() + 1) / (native[3] - native[1])
            ratios.append(ratio)
            soles.append(int(rows.max() - target_rows.max()))
            cover.append((alpha & target).sum() / target.sum())
            if ratio > 1.3:
                tall.append((i, round(float(ratio), 2)))
            if previous is not None and np.array_equal(previous, pixels):
                frozen.append(i)
            previous = pixels
        if not ratios:
            continue
        gaps.extend(soles)
        covers.extend(cover)
        print(f"{clip['name']:<10} {clip['start']:>3}-{clip['end']:<3} height/native {min(ratios):.2f}-{max(ratios):.2f} sole {min(soles)}..{max(soles)} cover {np.mean(cover):.3f} worst {min(cover):.3f}")
    gaps = np.abs(gaps)
    print("sole gap median", float(np.median(gaps)), "p90", float(np.percentile(gaps, 90)), "max", int(gaps.max()))
    print("overall cover", round(float(np.mean(covers)), 3), "worst", round(float(min(covers)), 3))
    print("much taller than sprite", tall)
    print("identical to the previous frame", frozen)


def sizes():
    """Each sheet's size against the sprite, by figure area. Height misleads: an arm drawn lower than the sprite's reads as a short figure, and the sheet scales up.

    Linear size is relative to the median sheet. Past about 6%, write a clip_scales.json goal of (its current height ratio) times the factor printed, on a fresh cut.
    """
    import json
    sheets, mixed = {}, []
    # A reused frame is another frame's picture, so it says nothing about the sheet that drew its own row.
    reuse_path = P.run / "reuse.json"
    reused = set(json.loads(reuse_path.read_text("utf-8"))) if reuse_path.exists() else set()
    for clip in P.clips():
        path = P.out / "clips" / clip["id"] / "selection.json"
        if not path.exists():
            continue
        used = set()
        for row in json.loads(path.read_text("utf-8"))["frames"]:
            if str(row["slot"]) in reused or not (P.out / f"native_frames/{row['slot']:04d}.png").exists():
                continue
            # "walk:3" on a sheet; a video frame is a bare number, and its whole clip shares one scale.
            source = str(row.get("video_frame", ""))
            sheet = source.split(":")[0] if ":" in source else clip["id"]
            used.add(sheet)
            new_area = (np.asarray(_new(row["slot"]).getchannel("A")) > 128).sum()
            old_area = (np.asarray(native_world(row["slot"]).getchannel("A")) > 128).sum()
            sheets.setdefault(sheet, []).append(new_area / old_area)
        if len(used) > 1:
            mixed.append((clip["id"], sorted(used)))
    if not sheets:
        raise SystemExit("nothing composited yet: run final first")
    middle = float(np.median([np.median(v) for v in sheets.values()]))
    for sheet, values in sheets.items():
        size = float(np.sqrt(np.median(values) / middle))
        print(f"{sheet:<12} {len(values):>3} frames  linear size {size:.3f}  factor {1 / size:.3f}" + ("   <- off" if abs(size - 1) > 0.06 else ""))
    if mixed:
        print("clips mixing sheets, which one clip_scales goal cannot size: split them in clips.json", mixed)


def repeats(limit=200):
    """Source frames that repeat: drawing one and reusing it (reuse.json) is cheaper, and a repeated action then cannot change size or detail."""
    pixels = {i: np.asarray(native_world(i)).astype(int) for i in range(P.frames)}
    used, groups = set(), []
    for i in range(P.frames):
        if i in used:
            continue
        group = [(j, int((np.abs(pixels[j] - pixels[i]).max(2) > 0).sum())) for j in range(i + 1, P.frames) if j not in used and (np.abs(pixels[j] - pixels[i]).max(2) > 0).sum() <= limit]
        if group:
            used.update(j for j, _ in group)
            groups.append((i, group))
    print(f"frame: repeats with changed pixels, up to {limit}. grip is the weapon hand: reuse only when it is the same or absent")
    for i, group in groups:
        grip = lambda f: [(round(h[0]), round(h[1])) for h in sprite_hands(f)]
        print(f"{i} grip {grip(i)}:", [(j, n, grip(j)) for j, n in group])
    print(sum(len(g) for _, g in groups), "frames could reuse another frame")


def moving(spec):
    """What the source moves in these frames, against the first: by height and by layer. A small motion is copied from this, with micro, instead of guessed."""
    frames = frames_from(spec)
    first = np.asarray(native_world(frames[0])).astype(int)
    box = native_world(frames[0]).getbbox()
    print("frames", frames, "first bbox", box, "(user numbers are one higher)")
    union = np.zeros(first.shape[:2], bool)
    for i in frames[1:]:
        changed = np.abs(np.asarray(native_world(i)).astype(int) - first).max(2) > 0
        union |= changed
        print(f"{i}: bbox {native_world(i).getbbox()} changed {int(changed.sum())} px")
    height = box[3] - box[1]
    for start in range(0, 100, 10):
        a, b = box[1] + start * height // 100, box[1] + (start + 10) * height // 100
        print(f"  height {start:>2}-{start + 10:<3}%  changed {int(union[a:b].sum())}")
    for layer in P.order:
        base = np.asarray(layer_world(layer, frames[0])).astype(int)
        total = sum(int((np.abs(np.asarray(layer_world(layer, i)).astype(int) - base).max(2) > 0).sum()) for i in frames[1:])
        if total:
            print(f"  layer {layer}: {total}")
    labels, count = ndimage.label(ndimage.binary_dilation(union, iterations=2))
    print("  moving regions (x0, y0, x1, y1):", [(s[1].start, s[0].start, s[1].stop, s[0].stop) for s in ndimage.find_objects(labels)])
    base = Image.new("RGB", (P.canvas, P.canvas), (86, 97, 122))
    image = native_world(frames[0])
    base.paste(image, (0, 0), image)
    marked = np.asarray(base).copy()
    marked[union] = (255, 0, 255)
    crop = (box[0] - 8, box[1] - 6, box[2] + 8, box[3] + 6)
    path = _save_path(f"moving_{frames[0]}_{frames[-1]}.png")
    Image.fromarray(marked).crop(crop).resize(((crop[2] - crop[0]) * 5, (crop[3] - crop[1]) * 5), Image.NEAREST).save(path)
    print("  magenta is what moves:", path)


def grips(name, spec, zoom=6, side=74):
    """The waist of each frame, large: sprite with weapon, new with weapon, new without, with the grip ringed. Boards with many hands shrink too far to see a gap."""
    frames = frames_from(spec)
    cell = side * zoom
    sheet = Image.new("RGB", (cell * 3, cell * len(frames)), (62, 70, 92))
    pen = ImageDraw.Draw(sheet)
    for row, i in enumerate(frames):
        native = native_world(i)
        hands = sprite_hands(i)
        box = native.getbbox()
        cx, cy = (int(hands[0][0]), int(hands[0][1])) if hands else ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
        crop = (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
        for col, image in enumerate((armed(native, i), armed(_new(i), i), _new(i))):
            big = image.crop(crop).resize((cell, cell), Image.NEAREST)
            sheet.paste(big, (col * cell, row * cell), big)
        for hand in hands:
            x, y = (hand[0] - crop[0]) * zoom, row * cell + (hand[1] - crop[1]) * zoom
            pen.ellipse((x - 12, y - 12, x + 12, y + 12), outline=(255, 60, 60), width=2)
        pen.text((4, row * cell + 2), f"frame {i} (user {i + 1})", fill="yellow")
    path = _save_path(name)
    sheet.save(path)
    print(path)


def anim(name, spec, zoom=3, ms=100):
    """Sprite and new side by side as a GIF, both armed. Cloth that jumps between frames and sizes that pop only show in motion."""
    frames = frames_from(spec)
    boxes = [armed(image, i).getbbox() for i in frames for image in (native_world(i), _new(i))]
    crop = (min(b[0] for b in boxes) - 4, min(b[1] for b in boxes) - 4, max(b[2] for b in boxes) + 4, max(b[3] for b in boxes) + 4)
    w, h = (crop[2] - crop[0]) * zoom, (crop[3] - crop[1]) * zoom
    pages = []
    for i in frames:
        page = Image.new("RGB", (w * 2, h), (62, 70, 92))
        for col, image in enumerate((native_world(i), _new(i))):
            big = armed(image, i).crop(crop).resize((w, h), Image.NEAREST)
            page.paste(big, (col * w, 0), big)
        pages.append(page)
    path = _save_path(name)
    pages[0].save(path, save_all=True, append_images=pages[1:], duration=ms, loop=0)
    print(path)


def _cool_hue(image, flat_gray=False):
    """Median hue of her colored shades: blue-dominant and not skin. Returns (hue, saturation, share of cyan)."""
    rgba = np.asarray(image.convert("RGBA"), np.float64)
    rgb, solid = rgba[..., :3], rgba[..., 3] > 128
    if flat_gray:
        solid = solid & (np.abs(rgb - np.median(rgb[:8].reshape(-1, 3), axis=0)).max(2) > 14)
    top, low = rgb.max(2), rgb.min(2)
    saturation = (top - low) / np.maximum(top, 1)
    mask = solid & (saturation > 0.08) & (top > 90) & (rgb[..., 2] >= rgb[..., 0]) & (rgb[..., 2] >= rgb[..., 1])
    if mask.sum() < 50:
        return None
    pixels = rgb[mask] / 255
    hues = np.array([colorsys.rgb_to_hsv(*p)[0] * 360 for p in pixels[:: max(1, len(pixels) // 4000)]])
    return round(float(np.median(hues)), 1), round(float(saturation[mask].mean()), 3), round(float(((hues >= 170) & (hues < 215)).mean()), 3)


def colors():
    """Reference against master against finished frames: hue, saturation, cyan. A drift of more than about 10 degrees reads as a different color to the user."""
    print("reference", _cool_hue(Image.open(P.character["reference_image"])), "(hue, saturation, cyan share)")
    print("master   ", _cool_hue(Image.open(P.master), flat_gray=True))
    if not (P.run / "clips.json").exists():
        return
    rows = [_cool_hue(_new(c["start"])) for c in P.clips() if (P.out / f"native_frames/{c['start']:04d}.png").exists()]
    rows = [r for r in rows if r]
    if rows:
        print("frames   ", "hue", min(r[0] for r in rows), "to", max(r[0] for r in rows), "saturation", round(float(np.mean([r[1] for r in rows])), 3), "cyan", max(r[2] for r in rows))


def check():
    """Every frame in exactly one clip; every sheet clip cut; every other clip selected. Run before final."""
    if not (P.run / "clips.json").exists():
        raise SystemExit("no clips.json yet: run composites, read contact_all.png and write it first")
    clips = P.clips()
    slots = [s for c in clips for s in range(c["start"], c["end"] + 1)]
    missing = sorted(set(range(P.frames)) - set(slots))
    doubled = sorted({s for s in slots if slots.count(s) > 1})
    pending = [c["id"] for c in clips if not (P.out / "clips" / c["id"] / "selection.json").exists()]
    stale = [p.name for p in (P.out / "clips").iterdir() if p.name not in {c["id"] for c in clips}] if (P.out / "clips").exists() else []
    print("frames", P.frames, "missing", missing, "in two clips", doubled)
    print("clips without a selection", pending)
    print("clip folders not in clips.json", stale)
    if weapon_layers():
        print("weapon", P.weapon["kind"], weapon_layers())
    return not (missing or doubled or pending or stale)
