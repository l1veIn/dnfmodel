"""Whale Song Queen: the luxurious costume on the native paper-doll rig.

Motion still comes from the official hand-animated layers. Painted parts, a shaded gown,
physics-driven train, sashes and wings, and looping particles provide the spectacle.
"""
from __future__ import annotations

import sys

import numpy as np
from PIL import Image
from scipy import ndimage

from fatfish_doll import CANVAS, FRAMES, INK, ROOT, Sprite, along, bake, bake_head, decode_art, layer_world, rasterize, recolor, rigid
from fatfish_doll_render import (ORANGE, WIND, TRAIL, WAG, GROUND, chain_step, charm_info, clips, hair_anchor, poses, relax, rot, swings,
                                 tail_anchor, wrap)

OUT = ROOT / "output/Fatfish_Luxe_v04"
PARTS = OUT / "parts/raw"

HEAD_SCALE = 0.9
HAIR_SCALE = 0.8
TRAIN_SCALE = 0.68
WING_SCALE = 0.84
TAIL_SCALE = 0.76
CREST_WIDTH = 23

OUTLINE = "2b2a5a"
PEARL = ("ffffff", "f1f2fb", "d9dcf2", "b6bbe3", "8f92c9")
GOLD = ("fff0a0", "f4cd5c", "d9a23a", "a06f28", "63421f")
OCEAN = ("9be8f5", "52c4ee", "2f8fe0", "2460c8", "1d3f9e")
LACE = ("ffffff", "eef1fb", "cdd4ee", "98a2d2")

SKIN = {"f7dfb7": "fff1e4", "f7b77f": "ffdccb", "cf875f": "f0b6a4", "af6f47": "c9877f", "7f472f": "7c4a5c",
        "cf5f5f": "e0707a", "8f3737": "8f3f55", "fff7f7": "ffffff", "f7bfbf": "ffc7cc", "e78f8f": "f49aa2"}
STOCKING = {"f7dfb7": "ffffff", "f7b77f": "f2f4fc", "cf875f": "cfd4ee", "af6f47": "9aa0cf", "7f472f": "4d4a82"}
COAT = {"171717": OUTLINE, "1f171f": "c8cdea", "27272f": "eef0fb", "3f3f47": "ffffff", "67676f": GOLD[1], "675f67": GOLD[1],
        "877f8f": GOLD[1], "9f9fa7": GOLD[0],
        "df272f": PEARL[0], "b71f2f": PEARL[1], "871737": PEARL[2], "5f1f37": PEARL[3], "3f172f": PEARL[4],
        "fff787": GOLD[0], "ffc707": GOLD[1], "ffa717": GOLD[1], "cf770f": GOLD[2], "8f3717": GOLD[3],
        "ffffff": LACE[0], "e7dff7": LACE[1], "c7c7c7": LACE[1], "c7bfdf": LACE[2], "9f9fbf": GOLD[1], "777797": GOLD[2],
        "ce7308": GOLD[2], "8c3110": GOLD[3], "ffa510": GOLD[1], "9c9cbd": GOLD[1], "ffc600": GOLD[1],
        "737394": GOLD[2], "101010": OUTLINE, "c6bdde": LACE[2], "e7def7": LACE[1], "212129": "eef0fb"}
CORSET = {"df272f": "ffffff", "b71f2f": "f1f2fb", "871737": GOLD[1], "5f1f37": GOLD[2], "3f172f": GOLD[3]}
SHOES = {"171717": OUTLINE, "170f0f": OUTLINE, "271717": "a9aedc", "1f171f": OUTLINE, "27272f": "a9aedc", "3f2727": "d5d9f0",
         "572f2f": "f2f4fc", "7f4747": "ffffff", "3f3f47": GOLD[2], "675f67": GOLD[1],
         "df272f": LACE[0], "b71f2f": LACE[1], "871737": GOLD[1], "5f1f37": GOLD[2], "3f172f": GOLD[3]}
UNDER = {"1f1717": "1d3f9e", "171717": OUTLINE, "271f1f": "2460c8", "170f0f": OUTLINE, "27272f": OUTLINE}
VEST = {(0xdf, 0x27, 0x2f), (0xb7, 0x1f, 0x2f), (0x87, 0x17, 0x37), (0x5f, 0x1f, 0x37), (0x3f, 0x17, 0x2f)}
SHADE = {(0x47, 0x3f, 0x3f): 0, (0x37, 0x2f, 0x2f): 1, (0x27, 0x1f, 0x1f): 2, (0x1f, 0x17, 0x17): 3, (0x17, 0x0f, 0x0f): 4,
         (0x5f, 0x1f, 0x37): 3, (0x3f, 0x17, 0x2f): 4}
HEM = {(0xdf, 0x27, 0x2f): GOLD[1], (0xb7, 0x1f, 0x2f): GOLD[2], (0x87, 0x17, 0x37): GOLD[3]}
CREST_WHALE = ["..G.......", "...G...G.G", ".GGGGG..G.", "GGDGGGGGG.", "GGGGGGGGG.", ".LLLLGGG.."]
CREST_COLORS = {"G": (217, 162, 58), "D": (99, 66, 31), "L": (255, 240, 160)}

EXPRESSION = {"待机站立": "serene", "默认走路": "serene", "战斗待机": "fierce", "蹲伏": "serene", "跳跃": "smile", "加buff": "happy",
              "魔道学者修东西": "serene", "魔道学者修东西2": "serene", "驱散": "happy", "召唤骑士": "serene"}
# Long fabric streams further behind than hair during fast clips.
FABRIC_TRAIL = {"默认走路": 0.5, "战斗跑": 1.8, "前冲": 2.2, "前冲摔倒": 1.0, "魔道学者丢东西": 0.9, "碎霸": 0.8, "落花掌": 0.5, "三段平A": 0.5}


def rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def hex_recolor(native, mapping):
    return recolor(native, mapping)


def pick(art, x, y):
    """The connected art component nearest a raw-sheet point, cropped, plus its origin."""
    labels, count = ndimage.label(art[..., 3] > 0, structure=np.ones((3, 3)))
    ax, ay = x // 8, y // 8
    if labels[ay, ax] == 0:
        distance = ndimage.distance_transform_edt(labels == 0, return_indices=True)
        iy, ix = distance[1][:, ay, ax]
        target = labels[iy, ix]
    else:
        target = labels[ay, ax]
    ys, xs = np.nonzero(labels == target)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    out = art[y0:y1, x0:x1].copy()
    out[labels[y0:y1, x0:x1] != target] = 0
    return out, (int(x0), int(y0))


def plain_fabric(art):
    """Pearl fabric with lilac folds: the scrollwork is unreadable at game scale."""
    out = art.copy()
    solid = out[..., 3] > 0
    gold = solid & (out[..., 0].astype(int) - out[..., 2].astype(int) > 25)
    interior = ndimage.binary_erosion(solid, iterations=2)
    out[gold & interior, :3] = (244, 244, 252)
    return out


class Parts:
    def __init__(self):
        first = decode_art(Image.open(PARTS / "heads_1_0.png"))
        second = decode_art(Image.open(PARTS / "heads_2_0.png"))
        cell = lambda sheet, r, c: sheet[r * 64:(r + 1) * 64, c * 64:(c + 1) * 64]
        table = {"smile": (cell(first, 0, 0), (36, 54)), "shout": (cell(first, 0, 1), (36, 54)), "fierce": (cell(first, 0, 2), (36, 54)),
                 "hurt": (cell(first, 1, 0), (36, 54)), "happy": (cell(first, 1, 1), (36, 54)), "dizzy": (cell(first, 1, 2), (36, 54)),
                 "back": (cell(second, 0, 0), (34, 54)), "front": (cell(second, 0, 1), (32, 54)), "frontshout": (cell(second, 0, 2), (32, 54)),
                 "cry": (cell(second, 1, 0), (37, 54)), "serene": (cell(second, 1, 1), (37, 54)), "surprised": (cell(second, 1, 2), (37, 54))}
        family = Sprite(np.concatenate([art for art, _ in table.values()], axis=1), colors=40)
        self.heads = {}
        for k, (name, (_, pivot)) in enumerate(table.items()):
            part = Sprite.__new__(Sprite)
            part.palette = family.palette
            part.index = family.index[:, k * 64:(k + 1) * 64]
            part.height, part.width = part.index.shape
            self.heads[name] = bake_head(part, pivot, None, HEAD_SCALE)
        self.head_pivot = (30, 56)

        sheet = decode_art(Image.open(PARTS / "parts_1_0.png"))
        hair, _ = pick(sheet, 250, 500)
        train, _ = pick(sheet, 720, 500)
        wing, wing_origin = pick(sheet, 1200, 300)
        tail, tail_origin = pick(sheet, 1300, 800)
        self.hair, self.hair_t = bake(Sprite(hair, colors=20), HAIR_SCALE)
        self.hair_cx, self.hair_len = hair.shape[1] / 2, hair.shape[0]
        self.train, self.train_t = bake(Sprite(plain_fabric(train), colors=8), TRAIN_SCALE, colors=8)
        self.train_cx, self.train_len = train.shape[1] / 2, train.shape[0]
        self.wing, self.wing_t = bake(Sprite(wing, colors=18), WING_SCALE)
        # Wing root sits at the sheet's lower right of the part.
        self.wing_root = (wing.shape[1] - 2, wing.shape[0] - 2)
        # Tail: split at the fluke root so the fluke stays rigid.
        split = 1150 // 8 - tail_origin[0]
        self.tail_split = split
        body, fluke = tail.copy(), tail.copy()
        body[:, :split - 2] = 0
        fluke[:, split + 1:] = 0
        self.tail_body, self.tail_body_t = bake(Sprite(body, colors=20), TAIL_SCALE)
        self.tail_fluke, self.tail_fluke_t = bake(Sprite(fluke, colors=16), TAIL_SCALE)
        self.tail_center = 810 // 8 - tail_origin[1]
        self.tail_width = tail.shape[1]
        self.fluke_root = (split, 770 // 8 - tail_origin[1])

        sheet = decode_art(Image.open(PARTS / "parts_2_0.png"))
        crest, _ = pick(sheet, 300, 700)
        bow, _ = pick(sheet, 700, 300)
        collar, _ = pick(sheet, 700, 760)
        # Painted whale and wreath become mush at crest size: a clean shield gets a hand-placed whale.
        inside = ndimage.binary_erosion(crest[..., 3] > 0, iterations=4)
        crest[inside, :3] = (250, 251, 255)
        self.crest, _ = bake(Sprite(crest, colors=10), CREST_WIDTH / crest.shape[1])
        self.bow = Sprite(bow, colors=14)
        self.bow_pivot = (bow.shape[1] / 2, bow.shape[0] / 2)
        self.collar = Sprite(collar, colors=14)
        self.collar_pivot = (collar.shape[1] / 2, collar.shape[0] * 0.35)


_parts = None


def parts():
    global _parts
    if _parts is None:
        _parts = Parts()
    return _parts


def luxe_poses():
    pose = poses()
    for i in range(FRAMES):
        p = pose[i]
        if p["expression"] == "smile":
            p["expression"] = EXPRESSION.get(p["clip"], "smile")
        elif p["clip"] in ("战斗待机", "加buff", "驱散", "召唤骑士") and p["expression"] in ("fierce", "happy"):
            p["expression"] = EXPRESSION[p["clip"]]
    return pose


def simulate(pose, lib):
    """Hair, tail and train over each clip. Every chain closes on loop clips."""
    result = {}
    hair_len = lib.hair_len * HAIR_SCALE
    train_len = lib.train_len * TRAIN_SCALE
    tail_len = (lib.tail_width - lib.tail_split) * TAIL_SCALE
    N = 7
    for clip in clips():
        frames = list(range(clip["start"], clip["end"] + 1))
        loop = bool(clip.get("loop"))
        name = clip["name"]
        wind_base, wag, trail = WIND.get(name, 0.0), WAG.get(name, 1.2), TRAIL.get(name, 0.0)
        cloth = FABRIC_TRAIL.get(name, 0.12)
        n = len(frames)
        sub = 4
        steps = n * sub

        def state(position):
            k = int(position) % n
            t = position - int(position)
            a, b = pose[frames[k]], pose[frames[(k + 1) % n] if (loop or k + 1 < n) else frames[k]]
            mix = lambda f: np.array(f(a), float) * (1 - t) + np.array(f(b), float) * t
            return mix(hair_anchor), mix(tail_anchor), mix(lambda p: p["axis"]), mix(lambda p: p["back"]), mix(lambda p: p["waist"])

        ha, ta, axis, back, waist = state(0)
        sign = -1 if pose[frames[0]]["flip"] else 1
        line = lambda start, direction, length: np.array([start + direction * j * length / (N - 1) for j in range(N)])
        down = np.array([0.0, 1.0])
        hair = line(ha, down, hair_len)
        tail = line(ta, back, tail_len)
        train = line(waist + back * 4, down, train_len)
        chains = [hair, tail, train]
        previous = [c.copy() for c in chains]
        records = {}
        stiff = dict(hair=np.linspace(0.5, 0.1, N), tail=np.linspace(0.55, 0.14, N), train=np.linspace(0.6, 0.06, N))
        total = steps * (4 if loop else 1) + (0 if loop else 40)
        for step in range(total):
            position = (step % steps) / sub if loop else min(max(0, step - 40) / sub, n - 1)
            ha, ta, axis, back, waist = state(position)
            phase = 2 * np.pi * ((step % steps) / steps if loop else step / (steps + 8))
            lift = -axis
            hair_dir = back * 0.14 + np.array([-trail * sign, 1.0])
            hair_dir /= np.hypot(*hair_dir)
            rest_h = line(ha, hair_dir, hair_len) + np.array([[np.sin(phase + j * 0.5) * 0.9 * j / (N - 1), 0] for j in range(N)])
            rest_t = [ta.copy()]
            for j in range(1, N):
                sweep = back * 0.9 + lift * (-0.62 + 0.62 * j / (N - 1))
                rest_t.append(rest_t[-1] + sweep / np.hypot(*sweep) * tail_len / (N - 1))
            rest_t = np.array(rest_t) + np.array([lift * np.sin(phase * (2 if loop and n >= 8 else 1) - j * 0.7) * wag * (j / (N - 1)) ** 1.4 for j in range(N)])
            cloth_dir = back * 0.62 + np.array([-cloth * sign, 1.0])
            cloth_dir /= np.hypot(*cloth_dir)
            rest_c = line(waist + back * 4, cloth_dir, train_len) + np.array([[np.sin(phase - j * 0.6) * 1.1 * j / (N - 1), 0] for j in range(N)])
            wind = -wind_base * sign
            chain_step(hair, previous[0], ha, rest_h, hair_len / (N - 1), stiff["hair"], 0.12, wind, floor=GROUND - 16)
            chain_step(tail, previous[1], ta, rest_t, tail_len / (N - 1), stiff["tail"], 0.02, wind * 0.5, floor=GROUND - 8)
            chain_step(train, previous[2], waist + back * 4, rest_c, train_len / (N - 1), stiff["train"], 0.14, wind * 1.2, floor=GROUND - 8)
            if abs(position - round(position)) < 1e-6:
                records[int(round(position)) % n] = tuple(c.copy() for c in chains)
        for j, i in enumerate(frames):
            result[i] = dict(zip(("hair", "tail", "train"), records[j]))
            result[i]["clip_phase"] = j / n
            result[i]["clip_len"] = n
            result[i]["clip_loop"] = loop
    return result


def gown(index, p, tick):
    """Native skirt pixels keep their hand-drawn folds and take the gown's zones by radius."""
    native = layer_world("mg_pants0000a", index)
    raw = np.array(native)
    solid = raw[..., 3] > 0
    out = raw.copy()
    if not solid.any():
        return Image.fromarray(out, "RGBA"), None
    waist = np.array(p["waist"])
    ys, xs = np.nonzero(solid)
    dx, dy = xs - waist[0], ys - waist[1]
    rho, phi = np.hypot(dx, dy), np.arctan2(dy, dx)
    bins = ((phi + np.pi) / (2 * np.pi) * 90).astype(int) % 90
    colors = raw[ys, xs, :3]
    is_band = np.array([tuple(c) in HEM for c in colors])
    outer = np.zeros(90)
    np.maximum.at(outer, bins, rho)
    order = np.arange(90)
    valid = outer > 0
    outer = np.interp(order, order[valid], outer[valid], period=90)
    band = np.full(90, np.nan)
    for b in np.unique(bins[is_band]):
        band[b] = rho[is_band & (bins == b)].max()
    known = ~np.isnan(band)
    edge = np.interp(order, order[known], band[known], period=90) if known.sum() >= 3 else outer * 0.86
    t = rho / np.maximum(edge[bins], 1)
    reference = p["apron"] if p["apron"] is not None else float(np.arctan2(ys.mean() - waist[1], xs.mean() - waist[0]))
    arc = np.arctan2(np.sin(phi - reference), np.cos(phi - reference)) * np.median(edge)
    for k in range(len(xs)):
        c = tuple(colors[k])
        if c in HEM:
            out[ys[k], xs[k], :3] = rgb(HEM[c])
            continue
        level = SHADE.get(c)
        if level is None:
            out[ys[k], xs[k], :3] = rgb(OUTLINE)
            continue
        tk = t[k]
        if tk > 1.0:
            out[ys[k], xs[k], :3] = rgb(LACE[min(level, 3)])
        elif tk > 0.68:
            ramp = int(np.clip((1.0 - tk) / 0.32 * 3, 0, 3)) + (1 if level >= 3 else 0)
            color = OCEAN[min(ramp, 4)]
            cell = int(arc[k]) * 7 + int(rho[k]) * 13
            if cell % 19 == 0 and (cell + tick) % 3 != 0:
                color = "ffffff"
            out[ys[k], xs[k], :3] = rgb(color)
        elif tk > 0.63:
            out[ys[k], xs[k], :3] = rgb(GOLD[1 if level < 3 else 2])
        else:
            out[ys[k], xs[k], :3] = rgb(PEARL[min(level, 4)])
    return Image.fromarray(out, "RGBA"), (solid, outer, order)


def petticoat(index, p, tick):
    """Two tiers under the bell, offset along the skirt axis, for a grander silhouette."""
    solid = np.array(layer_world("mg_pants0000a", index))[..., 3] > 0
    if not solid.any():
        return None
    ys, xs = np.nonzero(solid)
    axis = np.array([xs.mean() - p["waist"][0], ys.mean() - p["waist"][1]])
    axis /= max(np.hypot(*axis), 1e-6)
    out = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    # Deep ocean tier first, then lace; each is the bell slid down and slightly widened.
    for shift, widen, kind in ((7, 2, "ocean"), (4, 1, "lace")):
        moved = ndimage.shift(solid.astype(float), (axis[1] * shift, axis[0] * shift), order=0) > 0.5
        moved = ndimage.binary_dilation(moved, iterations=widen)
        yy, xx = np.nonzero(moved)
        rim = moved & ~ndimage.binary_erosion(moved, structure=np.ones((3, 3)))
        if kind == "ocean":
            out[moved] = (*rgb(OCEAN[3]), 235)
            near = moved & ~ndimage.binary_erosion(moved, iterations=2)
            out[near] = (*rgb(OCEAN[1]), 245)
            twinkle = ((xx * 7 + yy * 13) % 17 == 0) & ((xx + yy + tick) % 3 != 0)
            out[yy[twinkle], xx[twinkle]] = (255, 255, 255, 255)
        else:
            out[moved] = (*rgb(LACE[1]), 255)
            band = ((xx // 3 + yy // 2) % 2 == 0)
            out[yy[band], xx[band]] = (*rgb(LACE[0]), 255)
        out[rim] = (*rgb(OUTLINE if kind == "lace" else "12205a"), 255)
    return Image.fromarray(out, "RGBA")


def crest_layer(p, fields, direction, lib):
    sprite = lib.crest
    solid, radius, order = fields
    waist = np.array(p["waist"])
    centers = -np.pi + (order + 0.5) * 2 * np.pi / 90
    R0 = float(np.interp(direction, centers, radius, period=2 * np.pi))
    half, v0, v1 = CREST_WIDTH / 2, 0.1, 0.9

    def mapping(u, v):
        su = u / sprite.width * 2 - 1
        sv = v / sprite.height
        angle = direction + np.arcsin(np.clip(su * half / max(R0, 1), -0.98, 0.98))
        R = np.interp(angle, centers, radius, period=2 * np.pi)
        r = (v0 + (v1 - v0) * sv) * R
        return waist[0] + np.cos(angle) * r, waist[1] + np.sin(angle) * r

    colors = np.array(rasterize(sprite, mapping, outline=False))
    colors[~ndimage.binary_dilation(solid), 3] = 0
    mask = colors[..., 3] > 0
    if not mask.any():
        return None
    ring = ndimage.binary_dilation(mask) & ~mask
    colors[ring] = (*rgb(GOLD[2]), 255)
    ex, ey = round(waist[0] + np.cos(direction) * R0 * 0.58), round(waist[1] + np.sin(direction) * R0 * 0.58)
    for row, line in enumerate(CREST_WHALE):
        for col, ch in enumerate(line):
            if ch != ".":
                px = int(round(ex + 5 - col if p["flip"] else ex - 5 + col))
                py = int(round(ey - 3 + row))
                if mask[py, px]:
                    colors[py, px, :3] = CREST_COLORS[ch]
    return Image.fromarray(colors, "RGBA")


def dressed_coat(native, p):
    raw = np.array(native)
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS]
    depth = (xx - p["waist"][0]) * p["axis"][0] + (yy - p["waist"][1]) * p["axis"][1]
    below = depth >= -7
    vest = np.zeros(raw.shape[:2], bool)
    for color in VEST:
        vest |= (raw[..., 0] == color[0]) & (raw[..., 1] == color[1]) & (raw[..., 2] == color[2]) & (raw[..., 3] > 0)
    corset = raw.copy()
    corset[~(vest & below & (depth < 2)), 3] = 0
    plain = raw.copy()
    # The vest's long tail would flood the skirt and hide the crest: drop it past the waist.
    plain[vest & below, 3] = 0
    image = recolor(Image.fromarray(plain, "RGBA"), COAT)
    image.alpha_composite(recolor(Image.fromarray(corset, "RGBA"), CORSET))
    return image


def legs_in_stockings(body, shoe_mask, skirt_mask):
    """Skin pixels connected to the shoes are legs; hands are not, so they stay skin."""
    visible = (body[..., 3] > 0)
    labels, count = ndimage.label(visible & ~skirt_mask, structure=np.ones((3, 3)))
    touching = np.unique(labels[ndimage.binary_dilation(shoe_mask, iterations=2) & (labels > 0)])
    return np.isin(labels, touching[touching > 0])


def wings(p, data, lib, tick):
    phase = data["clip_phase"]
    flap = np.sin(2 * np.pi * phase * (1 if data["clip_len"] < 6 else 2)) * 7
    lean = np.degrees(np.arctan2(p["axis"][1], p["axis"][0])) - 90
    sign = -1 if p["flip"] else 1
    root = np.array(p["chin"], float) + p["axis"] * 8 + p["back"] * 2
    low = p["chin"][1] > GROUND - 42
    if low:
        lean, root = 0.0, np.array(p["chin"], float) + np.array([-sign * 6, -8])
    layers = []
    pivot = lib.wing_t(*lib.wing_root)
    for offset, scale_shift, extra in (((5, -3), 0.82, 30), ((0, 0), 1.0, 0)):
        scale_shift *= 0.72 if low else 1.0
        world = root + np.array([offset[0] * sign, offset[1]])
        angle = (lean * 0.6 + (flap + extra) * -sign)
        angle = round(angle / 3) * 3
        image = np.array(rasterize(lib.wing, rigid(pivot, (round(world[0]), round(world[1])), scale_shift, angle, p["flip"]), outline=False))
        solid = image[..., 3] > 0
        blueish = solid & (image[..., 2].astype(int) > image[..., 0].astype(int) + 12)
        # Membrane glows through; the gold rim and veins stay solid.
        image[blueish, 3] = 168 if extra == 0 else 128
        layers.append(Image.fromarray(image, "RGBA"))
    return layers


def halo(p, tick):
    center = np.array(p["chin"], float) + np.array(rot(p["angle"], -1, -23))
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS]
    r = np.hypot(xx - center[0], yy - center[1])
    ring = np.abs(r - 23) < 0.62
    out = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    out[ring] = (*rgb(GOLD[1]), 120)
    ang = np.radians(p["angle"] - 90)
    star = (round(center[0] + np.cos(ang) * 23), round(center[1] + np.sin(ang) * 23))
    stamp(out, star, STAR_SMALL, rgb(GOLD[0]))
    return Image.fromarray(out, "RGBA")


STAR_BIG = ["..#..", "..#..", "##@##", "..#..", "..#.."]
STAR_SMALL = [".#.", "#@#", ".#."]
BUBBLE = [".###.", "#@..#", "#...#", "#...#", ".###."]


def stamp(out, center, pattern, color, alpha=255):
    h, w = len(pattern), len(pattern[0])
    for r in range(h):
        for c in range(w):
            ch = pattern[r][c]
            if ch == ".":
                continue
            x, y = center[0] - w // 2 + c, center[1] - h // 2 + r
            if 0 <= x < CANVAS and 0 <= y < CANVAS:
                out[y, x] = (255, 255, 255, 255) if ch == "@" else (*color, alpha)


def particles(p, data, front):
    """Orbiting glints and bubbles; whole-number cycles keep loop clips seamless."""
    out = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    waist = np.array(p["waist"], float)
    phase = data["clip_phase"]
    n = data["clip_len"]
    tick = round(phase * n)
    specs = [(0.0, 34, 0.55, STAR_BIG, GOLD[0]), (1.1, 44, 0.7, STAR_SMALL, "ffffff"), (2.3, 38, 0.8, STAR_SMALL, GOLD[1]),
             (3.4, 46, 0.6, BUBBLE, "9be8f5"), (4.2, 30, 0.75, STAR_BIG, "ffffff"), (5.2, 42, 0.5, BUBBLE, "cfefff"), (5.9, 36, 0.9, STAR_SMALL, "9be8f5")]
    for k, (a, radius, squash, pattern, color) in enumerate(specs):
        angle = a + 2 * np.pi * phase
        depth = np.sin(angle)
        if (depth > 0) != front:
            continue
        if (tick + k) % 4 == 3:
            continue
        x = waist[0] + np.cos(angle) * radius
        y = waist[1] - 8 + depth * radius * squash * 0.5 + np.sin(angle * 2 + k) * 3
        if y > GROUND - 4:
            continue
        stamp(out, (round(x), round(y)), pattern, rgb(color), 170 if pattern is BUBBLE else 255)
    return Image.fromarray(out, "RGBA")


def crescent(p, swing):
    """The antenna hair as a fat tapered crescent, as on the design sheet."""
    points = np.array([(-1, -33), (-2, -41), (-5, -46), (-10, -47), (-14, -44), (-15, -40)], float)
    weights = np.linspace(0, 1, len(points)) ** 1.3
    ca, sa = np.cos(np.radians(swing * weights)), np.sin(np.radians(swing * weights))
    rel = points - points[0]
    local = np.c_[rel[:, 0] * ca - rel[:, 1] * sa, rel[:, 0] * sa + rel[:, 1] * ca] + points[0]
    if p["flip"]:
        local[:, 0] *= -1
    wx, wy = rot(p["angle"], local[:, 0], local[:, 1])
    t = np.linspace(0, len(points) - 1, 120)
    fine = np.arange(len(points))
    cx, cy = np.interp(t, fine, wx + p["chin"][0]), np.interp(t, fine, wy + p["chin"][1])
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS]
    core = np.zeros((CANVAS, CANVAS), bool)
    light = np.zeros((CANVAS, CANVAS), bool)
    for x, y, u in zip(cx, cy, t / t[-1]):
        radius = 2.0 * (1 - u) + 0.55
        ix, iy = int(round(x)), int(round(y))
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                if dx * dx + dy * dy <= radius * radius:
                    core[iy + dy, ix + dx] = True
        if 0.15 < u < 0.6:
            light[iy, ix] = True
    rim = ndimage.binary_dilation(core, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~core
    out = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    out[rim] = (*INK, 255)
    out[core] = (40, 62, 160, 255)
    out[light] = (82, 120, 224, 255)
    return Image.fromarray(out, "RGBA")


def compose(index, p, data, lib):
    world = Image.new("RGBA", (CANVAS, CANVAS))
    tick = round(data["clip_phase"] * data["clip_len"])
    from_behind = p["expression"] == "back"
    # Effects behind everything.
    world.alpha_composite(halo(p, tick))
    world.alpha_composite(particles(p, data, front=False))
    wing_layers = wings(p, data, lib, tick)
    if not from_behind:
        for layer in wing_layers:
            world.alpha_composite(layer)
    # Long fabric.
    (tx0, ty0), (tx1, ty1) = lib.train_t(lib.train_cx, 0), lib.train_t(lib.train_cx, lib.train_len)
    train = np.array(rasterize(lib.train, along((ty0, ty1), ((ty0, ty1), (tx0, tx1), True), relax(data["train"]), 1.0)))
    # A double gold edge drawn on the final silhouette stays crisp whatever the cloth does.
    solid = train[..., 3] > 0
    cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    inner1 = ndimage.binary_erosion(solid, structure=cross)
    inner2 = ndimage.binary_erosion(inner1, structure=cross)
    inner3 = ndimage.binary_erosion(inner2, structure=cross)
    train[inner1 & ~inner2] = (*rgb(GOLD[1]), 255)
    train[inner2 & ~inner3] = (*rgb(GOLD[2]), 255)
    world.alpha_composite(Image.fromarray(train, "RGBA"))
    # Hair over the fabric, tail over the hair.
    (hx0, hy0), (hx1, hy1) = lib.hair_t(lib.hair_cx, 0), lib.hair_t(lib.hair_cx, lib.hair_len)
    hair_layer = rasterize(lib.hair, along((hy0, hy1), ((hy0, hy1), (hx0, hx1), True), relax(data["hair"]), 1.0))
    if not from_behind:
        world.alpha_composite(hair_layer)
    tr = lib.tail_body_t
    knots_u = [tr(x, 0)[0] for x in (lib.tail_split, lib.tail_split + 8, lib.tail_width)]
    knots_v = [tr(0, lib.tail_center - 4)[1], tr(0, lib.tail_center)[1], tr(0, lib.tail_center)[1]]
    tail_nodes = relax(data["tail"], 1)
    tail_map = along((tr(lib.tail_width, 0)[0], tr(lib.tail_split, 0)[0]), (knots_u, knots_v, False), tail_nodes, 1.0, mirror=p["flip"])
    world.alpha_composite(rasterize(lib.tail_body, tail_map))
    tip = tail_nodes[-1] - tail_nodes[-3]
    fluke_angle = np.degrees(np.arctan2(tip[1], tip[0])) - 180
    if p["flip"]:
        fluke_angle = np.degrees(np.arctan2(tip[1], tip[0]))
    root_x, root_y = tail_map(*[np.array([c]) for c in tr(*lib.fluke_root)])
    world.alpha_composite(rasterize(lib.tail_fluke, rigid(lib.tail_fluke_t(*lib.fluke_root), (root_x[0], root_y[0]), 1.0, fluke_angle, p["flip"])))
    # Native body, with head erased.
    world.alpha_composite(recolor(layer_world("mg_pants0000d", index), UNDER))
    skirt_mask = np.array(layer_world("mg_pants0000a", index))[..., 3] > 0
    shoes_a, shoes_b = layer_world("mg_shoes0000a", index), layer_world("mg_shoes0000b", index)
    shoe_mask = (np.array(shoes_a)[..., 3] > 0) | (np.array(shoes_b)[..., 3] > 0)
    native_body = np.array(layer_world("mg_body0000", index))
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS]
    distance = np.hypot(xx - p["head"][0], yy - p["head"][1])
    behind = (xx - p["head"][0]) * (-1 if p["flip"] else 1) < -5
    disc = (distance < 15) | ((distance < 21) & behind)
    native_body[disc, 3] = 0
    legs = legs_in_stockings(native_body, shoe_mask, skirt_mask)
    skin = np.array(recolor(Image.fromarray(native_body, "RGBA"), SKIN))
    stocking = np.array(recolor(Image.fromarray(native_body, "RGBA"), STOCKING))
    skin[legs] = stocking[legs]
    body_image = Image.fromarray(skin, "RGBA")
    world.alpha_composite(body_image)
    world.alpha_composite(recolor(shoes_b, SHOES))
    world.alpha_composite(recolor(shoes_a, SHOES))
    # Gown, crest, bow, near sash.
    tiers = petticoat(index, p, tick)
    if tiers is not None:
        world.alpha_composite(tiers)
    skirt, fields = gown(index, p, tick)
    world.alpha_composite(skirt)
    direction = p["apron"]
    if fields is not None and direction is not None:
        crest = crest_layer(p, fields, direction, lib)
        if crest is not None:
            world.alpha_composite(crest)
    bow_pos = np.round(np.array(p["waist"]) + p["back"] * (11 if direction is not None else 0) + p["axis"] * 1)
    tilt = round((np.degrees(np.arctan2(p["axis"][1], p["axis"][0])) - 90) / 15) * 15
    world.alpha_composite(rasterize(lib.bow, rigid(lib.bow_pivot, bow_pos, 0.38, tilt, p["flip"])))
    # Coat.
    _, charms = charm_info(index, p)
    coats = []
    for layer in ("mg_coat0000c", "mg_coat0000b", "mg_coat0000a"):
        raw = np.array(layer_world(layer, index))
        for color in ORANGE:
            hit = (raw[..., 0] == color[0]) & (raw[..., 1] == color[1]) & (raw[..., 2] == color[2])
            raw[hit, 3] = 0
        coats.append(dressed_coat(Image.fromarray(raw, "RGBA"), p))
    for coat in coats:
        world.alpha_composite(coat)
    if not from_behind:
        collar_pos = np.round(np.array(p["chin"], float) + p["axis"] * 5)
        world.alpha_composite(rasterize(lib.collar, rigid(lib.collar_pivot, collar_pos, 0.3, tilt, p["flip"])))
    else:
        world.alpha_composite(hair_layer)
        for layer in wing_layers:
            world.alpha_composite(layer)
    world.alpha_composite(crescent(p, p.get("swing", 0.0)))
    head_layer = rasterize(lib.heads[p["expression"]], rigid(lib.head_pivot, p["chin"], 1.0, p["angle"], p["flip"]))
    world.alpha_composite(head_layer)
    # Arms beside the head stay in front.
    start, end = np.array(p["chin"], float), np.array(p["waist"], float)
    span = end - start
    t = np.clip(((xx - start[0]) * span[0] + (yy - start[1]) * span[1]) / max((span ** 2).sum(), 1e-6), 0, 1)
    torso = np.hypot(xx - (start[0] + t * span[0]), yy - (start[1] + t * span[1])) < 10
    head_alpha = np.array(head_layer)[..., 3] > 0
    front = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    for piece in (body_image, *coats):
        arr = np.array(piece)
        hit = (arr[..., 3] > 0) & head_alpha & ~torso & ~disc
        front[hit] = arr[hit]
    world.alpha_composite(Image.fromarray(front, "RGBA"))
    world.alpha_composite(particles(p, data, front=True))
    # Nothing sinks through the floor.
    arr = np.array(world)
    arr[GROUND + 3:, :, 3] = 0
    edge = arr[GROUND + 2, :, 3] > 0
    arr[GROUND + 2, edge] = (*INK, 255)
    return Image.fromarray(arr, "RGBA")


def render(selection=None):
    lib = parts()
    pose = luxe_poses()
    chains = simulate(pose, lib)
    for i, value in swings(pose).items():
        pose[i]["swing"] = value
    (OUT / "native_frames").mkdir(parents=True, exist_ok=True)
    for index in (selection if selection is not None else range(FRAMES)):
        compose(index, pose[index], chains[index], lib).save(OUT / f"native_frames/{index:04d}.png")
        print(index, flush=True)


if __name__ == "__main__":
    render([int(a) for a in sys.argv[1:]] or None)
