"""Read-only access to the game's character layers: composites of the source sprite, weapons, silhouettes."""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from dnf_resources import ImgArchive, read_npk

from .config import GAME, P

STREAK = 2
CUT = 0.42


@lru_cache(maxsize=None)
def _rows(pack):
    return {row["path"]: row for row in read_npk(GAME / pack)}


@lru_cache(maxsize=None)
def archive(layer):
    part = layer.split("/")[0]
    pack = f"{P.pack}_avatar_{part}.NPK"
    row = _rows(pack)[P.prefix + layer + ".img"]
    with (GAME / pack).open("rb") as stream:
        stream.seek(row["offset"])
        return ImgArchive(stream.read(row["length"]))


@lru_cache(maxsize=None)
def weapon_archive(kind, layer):
    pack = f"{P.pack}_weapon_{kind}.NPK"
    row = _rows(pack)[f"sprite/character/{P.cls}/{P.equipment}/weapon/{kind}/{layer}.img"]
    with (GAME / pack).open("rb") as stream:
        stream.seek(row["offset"])
        return ImgArchive(stream.read(row["length"]))


def place(source, index):
    world = Image.new("RGBA", (P.canvas, P.canvas))
    frame = source.resolve(index)
    if frame["width"] > 1 and frame["height"] > 1:
        world.alpha_composite(source.image(index).convert("RGBA"), (frame["x"], frame["y"]))
    return world


def layer_world(layer, index):
    return place(archive(layer), index)


def weapon_layers():
    return P.weapon["layers"] if P.weapon else []


def weapon_world(index, layer):
    return place(weapon_archive(P.weapon["kind"], layer), index)


def armed(image, index):
    world = image.copy()
    for layer in weapon_layers():
        world.alpha_composite(weapon_world(index, layer))
    return world


def native_world(index):
    return Image.open(P.composites / f"{index:04d}.png").convert("RGBA")


def solid(mask):
    """Remove thin motion-blur streaks drawn into some source frames, keeping limbs and their edges."""
    core = ndimage.binary_opening(mask, structure=np.ones((3, 3)), iterations=STREAK)
    labels, count = ndimage.label(core, structure=np.ones((3, 3)))
    if not count:
        return mask
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    near = ndimage.binary_dilation(labels == sizes.argmax(), iterations=12)
    # A real limb is large and stays near the body; what is left of a streak is small or floats away from it.
    keep = np.isin(labels, np.unique(labels[near & (labels > 0)])) & (sizes[labels] >= 24)
    return ndimage.binary_dilation(keep, iterations=STREAK + 1) & mask


@lru_cache(maxsize=None)
def _never_streak(index):
    """Motion blur is drawn into the clothes. A thin leg cut a shoe off from the body and a long hair ribbon looks like a streak, and solid alone deleted both, so only coat pixels may go."""
    keep = np.zeros((P.canvas, P.canvas), bool)
    for layer in P.order:
        if not layer.startswith("coat/"):
            keep |= np.asarray(layer_world(layer, index))[..., 3] > 0
    return keep


def figure_mask(index):
    mask = np.zeros((P.canvas, P.canvas), bool)
    for layer in P.figure:
        mask |= np.asarray(layer_world(layer, index))[..., 3] > 0
    return solid(mask) | (mask & _never_streak(index))


def export_composites():
    P.composites.mkdir(parents=True, exist_ok=True)
    for index in range(P.frames):
        world = Image.new("RGBA", (P.canvas, P.canvas))
        for layer in P.order:
            world.alpha_composite(layer_world(layer, index))
        pixels = np.array(world)
        pixels[~(solid(pixels[..., 3] > 0) | _never_streak(index))] = 0
        Image.fromarray(pixels, "RGBA").save(P.composites / f"{index:04d}.png")
    (P.materials / "reference_composite/reference.json").write_text(json.dumps(dict(frame_count=P.frames, canvas=P.canvas, layers_back_to_front=P.order), indent=1), "utf-8")
    print("composites", P.composites)


def draft_segments():
    """Draft clips from silhouette continuity, and a labelled contact sheet to check and name them by eye."""
    masks = [figure_mask(i) for i in range(P.frames)]
    values = []
    for a, b in zip(masks, masks[1:]):
        best = 0.0
        for dx in range(-12, 13, 3):
            moved = np.roll(b, dx, 1)
            best = max(best, (a & moved).sum() / max((a | moved).sum(), 1))
        values.append(float(best))
    cuts = [0] + [i + 1 for i, v in enumerate(values) if v < CUT] + [P.frames]
    clips = [(a, b - 1) for a, b in zip(cuts, cuts[1:])]
    P.run.mkdir(parents=True, exist_ok=True)
    (P.run / "segments_auto.json").write_text(json.dumps(dict(cut=CUT, continuity=[round(v, 3) for v in values], clips=clips), indent=1), "utf-8")
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)
    per_row, w, h = 16, 112, 140
    rows = (P.frames + per_row - 1) // per_row
    board = Image.new("RGB", (per_row * w, rows * h), (86, 97, 122))
    draw = ImageDraw.Draw(board)
    starts = {a for a, _ in clips}
    ground = int(np.median([native_world(i).getbbox()[3] for i in range(P.frames)]))
    for i in range(P.frames):
        x, y = (i % per_row) * w, (i // per_row) * h
        image = native_world(i)
        box = image.getbbox()
        center = (box[0] + box[2]) // 2
        crop = image.crop((center - w // 2, ground - h + 8, center + w // 2, ground + 8))
        board.paste(crop, (x, y), crop)
        draw.text((x + 2, y + 1), str(i), fill="yellow" if i in starts else "white", font=font)
        if i in starts:
            draw.line((x, y, x, y + h), fill=(255, 220, 0), width=2)
    path = P.materials / "reference_composite/contact_all.png"
    board.save(path)
    print(len(clips), "clips", clips)
    print("contact sheet", path)


def measure():
    """Body proportions at standing frames, for the master's prompt. Heads differ little between classes; bodies differ a lot."""
    frame = P.standing[0]
    body = np.asarray(layer_world(P.body, frame))[..., 3] > 0
    rows = np.nonzero(body.any(1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    height = bottom - top + 1
    print("frame", frame, "body", top, bottom, "height", height)
    for y in range(top, bottom + 1, 5):
        print(f"  {(y - top) / height:.2f} width {int(body[y].sum())}")
    box = native_world(frame).getbbox()
    print("composite bbox", box)
    # A sudden width change can be the bottom of an ear as easily as the chin, so read the chin off the picture, not off these numbers.
    zoom, tall = 8, box[3] - box[1]
    crop = native_world(frame).crop((box[0] - 30, box[1], box[2] + 30, box[3]))
    picture = Image.new("RGB", (crop.width * zoom, crop.height * zoom), (86, 97, 122))
    big = crop.resize(picture.size, Image.NEAREST)
    picture.paste(big, (0, 0), big)
    pen = ImageDraw.Draw(picture)
    for percent in range(5, 100, 5):
        y = round(percent / 100 * tall) * zoom
        pen.line((0, y, picture.width, y), fill=(255, 255, 0) if percent % 10 == 0 else (200, 200, 110))
        pen.text((3, y + 1), f"{percent / 100:.2f}", fill=(255, 255, 0))
    (P.out / "dev").mkdir(parents=True, exist_ok=True)
    picture.save(P.out / "dev/measure.png")
    print("read chin, waist and hem from", P.out / "dev/measure.png", "fractions of the composite height; check first that this standing frame has her arms down")
