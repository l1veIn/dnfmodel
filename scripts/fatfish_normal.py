"""Normal-proportion whale maid: native-size head on the native body, costume per the character sheet."""
from __future__ import annotations

import sys

import numpy as np
from PIL import Image
from scipy import ndimage

import fatfish_doll_render as R
from fatfish_doll import COAT, NAVY, ROOT, SHOES, WHITE, Sprite, bake, bake_head, decode_art, layer_world, library, recolor
from fatfish_luxe import STOCKING, pick

OUT = ROOT / "output/Fatfish_Normal_v05"
HEAD_SCALE = 0.85
HEAD_PIVOT = (30, 56)
HAIR_LENGTH = 60
HAIR_SCALE = 0.6
TAIL_SCALE = 0.52
APRON_WIDTH = 30
# Solid navy sleeves as on the character sheet: the native stripes merge into highlights.
PLAIN_COAT = {**COAT, "27272f": NAVY[2], "3f3f47": NAVY[2], "67676f": NAVY[1], "675f67": NAVY[1], "877f8f": NAVY[1], "9f9fa7": NAVY[0]}
# Mary Janes: laces go quiet and the boot cuff becomes stocking.
PLAIN_SHOES = {**SHOES, "675f67": NAVY[1], "3f3f47": NAVY[2]}


def legs_hook(body, index):
    """Skin connected to the shoes becomes white stocking; hands stay skin."""
    skirt = np.array(layer_world("mg_pants0000a", index))[..., 3] > 0
    shoes = (np.array(layer_world("mg_shoes0000a", index))[..., 3] > 0) | (np.array(layer_world("mg_shoes0000b", index))[..., 3] > 0)
    labels, _ = ndimage.label((body[..., 3] > 0) & ~skirt, structure=np.ones((3, 3)))
    touching = np.unique(labels[ndimage.binary_dilation(shoes, iterations=2) & (labels > 0)])
    legs = np.isin(labels, touching[touching > 0])
    native = np.array(recolor(layer_world("mg_body0000", index), STOCKING))
    body[legs] = native[legs]
    return body


def ruffle(index, p):
    """A white ruffle below the hem, the bell slid down its own axis, for the sheet's frilled skirt."""
    solid = np.array(layer_world("mg_pants0000a", index))[..., 3] > 0
    out = np.zeros((*solid.shape, 4), np.uint8)
    if not solid.any():
        return Image.fromarray(out, "RGBA")
    ys, xs = np.nonzero(solid)
    axis = np.array([xs.mean() - p["waist"][0], ys.mean() - p["waist"][1]])
    axis /= max(np.hypot(*axis), 1e-6)
    moved = ndimage.shift(solid.astype(float), (axis[1] * 4, axis[0] * 4), order=0) > 0.5
    moved = ndimage.binary_dilation(moved)
    hex_rgb = lambda value: tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    yy, xx = np.nonzero(moved)
    out[moved] = (*hex_rgb(WHITE[1]), 255)
    scallop = (xx // 3 + yy // 2) % 2 == 0
    out[yy[scallop], xx[scallop]] = (*hex_rgb(WHITE[0]), 255)
    out[moved & ~ndimage.binary_erosion(moved, structure=np.ones((3, 3)))] = (*hex_rgb(NAVY[4]), 255)
    return Image.fromarray(out, "RGBA")


def setup():
    """Point the shared compositor at the normal-proportion parts."""
    R.OUT = OUT
    R.HAIR_SCALE = HAIR_LENGTH / 100
    R.TAIL_SCALE = TAIL_SCALE
    R.APRON_WIDTH = APRON_WIDTH
    R.COAT, R.SHOES = PLAIN_COAT, PLAIN_SHOES
    R.STYLE.update(disc=(12, 17), bow=0.34, bow_back=7, tie=0.34, gold=0.42, ahoge=0.7, body_hook=legs_hook, under_skirt=ruffle, floor_lift=14, clip_floor=True)
    lib = library()
    sheet = decode_art(Image.open(OUT / "parts/raw/heads_n1_0.png"))
    cell = lambda r, c: sheet[r * 64:(r + 1) * 64, c * 64:(c + 1) * 64]
    table = {"smile": (cell(0, 0), (37, 51)), "shout": (cell(0, 1), (37, 51)), "fierce": (cell(0, 2), (37, 51)),
             "hurt": (cell(1, 0), (37, 51)), "back": (cell(1, 1), (32, 51)), "front": (cell(1, 2), (33, 50))}
    family = Sprite(np.concatenate([art for art, _ in table.values()], axis=1), colors=32)
    baked = {}
    for k, (name, (_, pivot)) in enumerate(table.items()):
        part = Sprite.__new__(Sprite)
        part.palette = family.palette
        part.index = family.index[:, k * 64:(k + 1) * 64]
        part.height, part.width = part.index.shape
        baked[name] = bake_head(part, pivot, None, HEAD_SCALE)
    baked.update(happy=baked["smile"], dizzy=baked["hurt"], cry=baked["shout"], frontshout=baked["front"])
    lib.heads = baked
    lib.pivots = {name: HEAD_PIVOT for name in baked}
    # The later, cleaner hair painting; the compositor addresses hair in the older art's coordinates.
    hair_art, _ = pick(decode_art(Image.open(ROOT / "output/Fatfish_Luxe_v04/parts/raw/parts_1_0.png")), 250, 500)
    hair, transform = bake(Sprite(hair_art, colors=20), HAIR_SCALE)
    tail_body, tail_body_t = bake(lib.tail_body, TAIL_SCALE)
    tail_fluke, tail_fluke_t = bake(lib.tail_fluke, TAIL_SCALE)
    apron, _ = bake(lib.apron, APRON_WIDTH / lib.apron.width)
    h, w = hair_art.shape[:2]
    R._baked.clear()
    R._baked.update(hair=hair, hair_t=lambda u, v: transform(u * w / 78, v * h / 106), body=tail_body, body_t=tail_body_t,
                    fluke=tail_fluke, fluke_t=tail_fluke_t, apron=apron)


if __name__ == "__main__":
    setup()
    R.render([int(a) for a in sys.argv[1:]] or None)
