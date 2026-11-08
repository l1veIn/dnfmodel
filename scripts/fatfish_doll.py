"""Native paper-doll compositor: recolor the hand-animated default layers into the maid costume.

Every limb, sleeve, skirt and shoe pixel comes from the official frame-by-frame layers,
so motion and weapon alignment are identical to the original sprite. Palette maps are
exact (each layer holds about a dozen colors), nothing is resampled.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ROOT / "materials/female_mage/layers"
CANVAS = 500
FRAMES = 174


def hexrgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


# Navy dress ramp, light to dark.
NAVY = ("3b4a9c", "2c3679", "212a60", "181e49", "11152f", "0c0f22")
# Blue-tinted whites for blouse, cuffs and frills.
WHITE = ("ffffff", "e6ebfa", "bcc7e8", "8693c6", "56619a")
GOLD = ("fff0a0", "f4cd5c", "d9a23a", "a06f28", "63421f")
SKIN = {"f7dfb7": "fff1e4", "f7b77f": "ffdccb", "cf875f": "f0b6a4", "af6f47": "c9877f", "7f472f": "7c4a5c",
        "cf5f5f": "e0707a", "8f3737": "8f3f55", "fff7f7": "ffffff", "f7bfbf": "ffc7cc", "e78f8f": "f49aa2"}

SKIRT = {"473f3f": NAVY[0], "372f2f": NAVY[1], "271f1f": NAVY[2], "1f1717": NAVY[3], "170f0f": NAVY[4],
         "27272f": NAVY[4], "1f171f": NAVY[4], "171717": NAVY[5],
         "df272f": GOLD[1], "b71f2f": GOLD[2], "871737": GOLD[3], "5f1f37": NAVY[3], "3f172f": NAVY[4]}

COAT = {"171717": NAVY[5], "1f171f": NAVY[4], "27272f": NAVY[3], "3f3f47": NAVY[1], "67676f": NAVY[0], "675f67": NAVY[0],
        "877f8f": "5a6cc0", "9f9fa7": "7f8fd8",
        # Red vest front becomes the white blouse.
        "df272f": WHITE[0], "b71f2f": WHITE[1], "871737": WHITE[2], "5f1f37": WHITE[3], "3f172f": WHITE[4],
        # Pumpkin and bow ornaments stay gold.
        "fff787": GOLD[0], "ffc707": GOLD[1], "ffa717": GOLD[1], "cf770f": GOLD[2], "8f3717": GOLD[3],
        "ffffff": WHITE[0], "e7dff7": WHITE[1], "c7c7c7": WHITE[1], "c7bfdf": WHITE[2], "9f9fbf": WHITE[3], "777797": WHITE[4]}
# Older-encoded neighbours of the same palette entries in layer b.
COAT.update({"ce7308": GOLD[2], "8c3110": GOLD[3], "ffa510": GOLD[1], "9c9cbd": WHITE[3], "ffc600": GOLD[1],
             "737394": WHITE[4], "101010": NAVY[5], "c6bdde": WHITE[2], "e7def7": WHITE[1], "212129": NAVY[3]})

SHOES = {"171717": NAVY[5], "170f0f": NAVY[5], "271717": NAVY[4], "1f171f": NAVY[4], "27272f": NAVY[3], "3f2727": NAVY[2],
         "572f2f": NAVY[1], "7f4747": NAVY[0], "3f3f47": NAVY[1], "675f67": "5a6cc0",
         # Red boot cuffs become the frilled white socks.
         "df272f": WHITE[0], "b71f2f": WHITE[1], "871737": WHITE[2], "5f1f37": WHITE[3], "3f172f": WHITE[4]}

# (layer, palette map) back to front. Hair, cap and face are replaced by painted parts.
STACK = [("mg_pants0000d", SKIRT), ("mg_body0000", SKIN), ("mg_shoes0000b", SHOES), ("mg_shoes0000a", SHOES),
         ("mg_pants0000a", SKIRT), ("mg_coat0000c", COAT), ("mg_coat0000b", COAT), ("mg_coat0000a", COAT)]


def _lut(mapping):
    return {hexrgb(k): hexrgb(v) for k, v in mapping.items()}


_meta = {}


def layer_meta(layer):
    if layer not in _meta:
        _meta[layer] = json.loads((LAYERS / layer / "frames.json").read_text("utf-8"))["frames"]
    return _meta[layer]


def layer_world(layer, index):
    """Layer pixels at world position; link frames resolve to their target."""
    frames = layer_meta(layer)
    frame = frames[frames[index].get("resolved_index", index)]
    world = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    if frame.get("png") and frame.get("width", 0) > 0:
        path = LAYERS / layer / frame["png"]
        if path.exists():
            world.alpha_composite(Image.open(path).convert("RGBA"), (frame["x"], frame["y"]))
    return world


def recolor(image, mapping):
    pixels = np.array(image)
    result = pixels.copy()
    packed = (pixels[..., 0].astype(np.uint32) << 16) | (pixels[..., 1].astype(np.uint32) << 8) | pixels[..., 2]
    visible = pixels[..., 3] > 0
    for source, target in _lut(mapping).items():
        code = (source[0] << 16) | (source[1] << 8) | source[2]
        hit = visible & (packed == code)
        result[hit, 0], result[hit, 1], result[hit, 2] = target
    return Image.fromarray(result, "RGBA")


def costume(index):
    """The recolored native costume for one frame, in world coordinates."""
    world = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    for layer, mapping in STACK:
        world.alpha_composite(recolor(layer_world(layer, index), mapping))
    return world


# ---- Painted parts: decoded to true art pixels, then rasterized with palette-mode sampling. ----

from scipy import ndimage  # noqa: E402

PARTS = ROOT / "output/Fatfish_Doll_v03/parts"
TRACK = ROOT / "design/fatfish/doll_v03/head_track.json"
INK = (14, 16, 44)
HEAD_SCALE = 0.84
SAMPLES = 6


def decode_art(image, cell=8):
    """Sample each 8x8 screen cell by its median color; hard alpha."""
    pixels = np.array(image.convert("RGBA"))
    rows, cols = pixels.shape[0] // cell, pixels.shape[1] // cell
    out = np.zeros((rows, cols, 4), np.uint8)
    for r in range(rows):
        for c in range(cols):
            block = pixels[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell].reshape(-1, 4)
            solid = block[block[:, 3] >= 128]
            if len(solid) * 2 >= len(block):
                out[r, c, :3] = np.median(solid[:, :3], axis=0)
                out[r, c, 3] = 255
    return out


class Sprite:
    """Indexed art: ``index`` is H x W palette indices, -1 where transparent."""

    def __init__(self, art, colors=24):
        art = np.array(art)
        solid = art[..., 3] > 0
        opaque = art[solid][:, :3]
        probe = Image.fromarray(opaque.reshape(-1, 1, 3), "RGB").quantize(colors, method=Image.Quantize.MEDIANCUT, kmeans=6)
        used = sorted({i for _, i in probe.getcolors()})
        self.palette = np.array(probe.getpalette(), np.uint8).reshape(-1, 3)[used]
        distance = ((art[..., :3, None].astype(np.int32).transpose(0, 1, 3, 2)
                     - self.palette[None, None].astype(np.int32)) ** 2).sum(3)
        self.index = np.where(solid, distance.argmin(2), -1).astype(np.int32)
        self.height, self.width = self.index.shape


def rasterize(sprite, mapping, outline=True, cover=0.5):
    """Forward-map art samples through ``mapping(u, v) -> (x, y)`` into a world RGBA layer.

    Each output pixel takes the most common palette color of the samples landing on it, so
    no in-between colors appear and silhouettes stay hard.
    """
    ys, xs = np.nonzero(sprite.index >= 0)
    colors = sprite.index[ys, xs]
    sub = (np.arange(SAMPLES) + 0.5) / SAMPLES
    uu, vv = np.meshgrid(sub, sub)
    u = (xs[:, None, None] + uu).ravel()
    v = (ys[:, None, None] + vv).ravel()
    c = np.repeat(colors, SAMPLES * SAMPLES)
    wx, wy = mapping(u, v)
    px, py = np.floor(wx).astype(np.int64), np.floor(wy).astype(np.int64)
    keep = (px >= 0) & (px < CANVAS) & (py >= 0) & (py < CANVAS)
    px, py, c = px[keep], py[keep], c[keep]
    key = py * CANVAS + px
    k = int(sprite.index.max()) + 1
    joint = np.bincount(key * k + c)
    nonzero = np.nonzero(joint)[0]
    cells, cc, counts = nonzero // k, nonzero % k, joint[nonzero]
    order = np.lexsort((counts, cells))
    cells, cc, counts = cells[order], cc[order], counts[order]
    last = np.r_[cells[1:] != cells[:-1], True]
    total = np.bincount(key)
    out = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    ty, tx = np.divmod(cells[last], CANVAS)
    out[ty, tx, :3] = sprite.palette[cc[last]]
    density = np.median(total[total > 0])
    out[ty, tx, 3] = (total[cells[last]] >= density * cover) * 255
    labels, count = ndimage.label(out[..., 3] > 0)
    if count > 1:
        sizes = np.bincount(labels.ravel())
        out[(sizes < 12)[labels] & (labels > 0), 3] = 0
    if outline:
        solid = out[..., 3] > 0
        edge = solid & ~ndimage.binary_erosion(solid, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
        out[edge, :3] = INK
    return Image.fromarray(out, "RGBA")


def rigid(pivot, world, scale, angle=0.0, flip=False):
    """Scale, rotate about sprite pivot, place pivot at world position."""
    ca, sa = np.cos(np.radians(angle)), np.sin(np.radians(angle))

    def mapping(u, v):
        dx, dy = (u - pivot[0]) * scale, (v - pivot[1]) * scale
        if flip:
            dx = -dx
        return world[0] + ca * dx - sa * dy, world[1] + sa * dx + ca * dy
    return mapping


def along(axis_u, center, target, scale, mirror=False):
    """Bend a sprite along a world polyline with a continuous graph parametrization.

    ``axis_u`` is (start, end) in art x or y ("v" when ``center`` has key "v"); ``center`` maps the
    running coordinate to the art centerline across it, so nearby pixels never tear apart.
    """
    target = np.asarray(target, float)
    tseg = np.diff(target, axis=0)
    tlen = np.maximum(np.hypot(tseg[:, 0], tseg[:, 1]), 1e-6)
    tcum = np.r_[0, np.cumsum(tlen)]
    tnorm = np.c_[-tseg[:, 1], tseg[:, 0]] / tlen[:, None]
    joint_norm = np.vstack([tnorm[0], (tnorm[:-1] + tnorm[1:]) / 2, tnorm[-1]])
    joint_norm /= np.maximum(np.hypot(joint_norm[:, 0], joint_norm[:, 1]), 1e-6)[:, None]
    fraction = tcum / tcum[-1]
    start, end = axis_u
    knots, values, vertical = center

    def mapping(u, v):
        run, across = (v, u) if vertical else (u, v)
        s = np.clip((run - start) / (end - start), 0, 1)
        offset = (across - np.interp(run, knots, values)) * scale
        if not vertical:
            offset = -offset
        if mirror:
            offset = -offset
        # Beyond the ends keep going straight so nothing folds.
        x = np.interp(s, fraction, target[:, 0])
        y = np.interp(s, fraction, target[:, 1])
        nx = np.interp(s, fraction, joint_norm[:, 0])
        ny = np.interp(s, fraction, joint_norm[:, 1])
        return x + offset * nx, y + offset * ny
    return mapping


HEAD_PIVOT = (30, 56)
MOUTH_DARK, MOUTH_RED, FANG = (92, 28, 52), (206, 66, 78), (255, 255, 255)
# Hand-placed mouths at game scale, (x, y, rows); rows use D=line R=interior W=fang .=skin ' '=keep.
OPEN_SMILE = ["DDDDDD", ".DRWRD", "..DRD."]
FACE_PATCHES = {
    "smile": (33, 47, OPEN_SMILE),
    "happy": (33, 47, OPEN_SMILE),
    "front": (27, 48, ["DDDDDD", "DRWRRD", ".DRRD."]),
}


def bake_head(part, pivot, patch, scale=HEAD_SCALE):
    """Rasterize one expression at game scale, then lay in the hand-placed mouth."""
    image = np.array(rasterize(part, rigid(pivot, HEAD_PIVOT, scale), outline=False))[:60, :60].copy()
    sprite = Sprite(image, colors=32)
    if patch:
        # Mouth colors join the palette only after quantizing, so they never leak into the hair.
        x, y, rows = patch
        skin = image[y - 3, x + 2, :3].copy()
        base = len(sprite.palette)
        sprite.palette = np.vstack([sprite.palette, skin, MOUTH_DARK, MOUTH_RED, FANG]).astype(np.uint8)
        codes = {".": base, "D": base + 1, "R": base + 2, "W": base + 3}
        for r in range(-1, len(rows) + 2):
            for c in range(-1, len(rows[0]) + 1):
                sprite.index[y + r, x + c] = base
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                sprite.index[y + r, x + c] = codes[ch]
    return sprite


class Library:
    def __init__(self):
        first = decode_art(Image.open(PARTS / "raw/heads_a_0.png"))
        second = decode_art(Image.open(PARTS / "raw/heads_b_0.png"))
        cell = lambda sheet, r, c: sheet[r * 64:(r + 1) * 64, c * 64:(c + 1) * 64]
        # Name: (art, chin pivot). Second sheet's bottom row replaces the muddier first mouths.
        table = {"fierce": (cell(first, 0, 2), (38, 58)), "hurt": (cell(first, 1, 0), (38, 58)),
                 "happy": (cell(first, 1, 1), (38, 58)), "dizzy": (cell(first, 1, 2), (38, 58)),
                 "back": (cell(second, 0, 0), (32, 55)), "front": (cell(second, 0, 1), (33, 54)),
                 "frontshout": (cell(second, 0, 2), (33, 54)), "shout": (cell(second, 1, 0), (40, 57)),
                 "cry": (cell(second, 1, 1), (40, 57)), "smile": (cell(second, 1, 2), (40, 57))}
        # One shared palette over all expressions: quantize them together.
        family = Sprite(np.concatenate([art for art, _ in table.values()], axis=1), colors=32)
        self.heads = {}
        self.pivots = {}
        for i, (name, (_, pivot)) in enumerate(table.items()):
            part = Sprite.__new__(Sprite)
            part.palette = family.palette
            part.index = family.index[:, i * 64:(i + 1) * 64]
            part.height, part.width = part.index.shape
            self.heads[name] = bake_head(part, pivot, FACE_PATCHES.get(name))
            self.pivots[name] = HEAD_PIVOT
        art = decode_art(Image.open(PARTS / "raw/parts_a_0.png"))
        crop = lambda x0, y0, x1, y1: art[y0 // 8:y1 // 8, x0 // 8:x1 // 8]
        hair = crop(16, 112, 640, 960).copy()
        labels, _ = ndimage.label(hair[..., 3] > 0)
        hair[labels != np.bincount(labels[labels > 0]).argmax()] = 0
        self.hair = Sprite(hair, colors=20)
        tail = crop(584, 112, 1136, 496)
        body, fluke = tail.copy(), tail.copy()
        # Fluke stays rigid so its two lobes always read; 2 rows of overlap hide the seam.
        fluke[25:] = 0
        body[:23] = 0
        self.tail_body = Sprite(body, colors=10)
        self.tail_fluke = Sprite(fluke, colors=10)
        apron = crop(664, 568, 1112, 952).copy()
        # The painted emblem is replaced by a hand-placed one that survives at this scale.
        blue = (apron[..., 2].astype(int) - apron[..., 0].astype(int) > 60) & (apron[..., 3] > 0)
        apron[blue, :3] = (246, 248, 255)
        self.apron = Sprite(apron, colors=8)
        self.bow = Sprite(crop(1176, 112, 1512, 400), colors=8)
        self.gold = Sprite(crop(1264, 424, 1424, 552), colors=8)
        self.tie = Sprite(crop(1216, 576, 1472, 728), colors=10)


def bake(sprite, scale, colors=None):
    """Rasterize once at game scale; warping the result only shifts whole clusters, so
    highlights never boil from frame to frame. Returns (sprite, art_to_baked)."""
    image = rasterize(sprite, rigid((0, 0), (40, 40), scale), outline=False)
    box = image.getbbox()
    baked = Sprite(np.array(image.crop(box)), colors=colors or len(sprite.palette))

    def transform(u, v):
        return 40 + u * scale - box[0], 40 + v * scale - box[1]
    return baked, transform


_library = None


def library():
    global _library
    if _library is None:
        _library = Library()
    return _library
