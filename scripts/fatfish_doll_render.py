"""Assemble all 174 frames: native recolored costume + painted head, hair, tail, apron.

Hair and tail are driven by a verlet chain simulated over each annotated clip, so loops
close and secondary motion follows the real hand-animated poses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from fatfish_doll import (CANVAS, COAT, FRAMES, HEAD_SCALE, INK, NAVY, ROOT, SHOES, SKIN, SKIRT, TRACK, WHITE, along,
                          bake, layer_world, library, rasterize, recolor, rigid)

OUT = ROOT / "output/Fatfish_Doll_v03"
MOTION = ROOT / "design/fatfish/action_catalog/manual_motion.json"
CHIN_WORLD = (1, 10)
GROUND = 389
HAIR_SCALE = 0.56
TAIL_SCALE = 0.68
APRON_WIDTH = 30
# Knobs other costume variants override; these values are the big-head version.
STYLE = dict(disc=(15, 21), bow=0.42, bow_back=9, tie=0.42, gold=0.52, ahoge=1.0, body_hook=None, under_skirt=None, floor_lift=0, clip_floor=False)
ORANGE = {(0xcf, 0x77, 0x0f), (0x8f, 0x37, 0x17), (0xff, 0xa7, 0x17), (0xff, 0xc7, 0x07), (0xff, 0xf7, 0x87),
          (0xce, 0x73, 0x08), (0x8c, 0x31, 0x10), (0xff, 0xa5, 0x10), (0xff, 0xc6, 0x00)}
BAND = {(0xdf, 0x27, 0x2f), (0xb7, 0x1f, 0x2f), (0x87, 0x17, 0x37)}

# Hand-placed emblem: survives at apron scale where the painted one would turn to mush.
WHALE = ["..B.......", "...B...B.B", ".BBBBB..B.", "BBWBBBBBB.", "BBBBBBBBB.", ".LLLLBBB.."]
WHALE_COLORS = {"B": (47, 111, 216), "L": (170, 200, 250), "W": (255, 255, 255)}
VEST = {(0xdf, 0x27, 0x2f), (0xb7, 0x1f, 0x2f), (0x87, 0x17, 0x37), (0x5f, 0x1f, 0x37), (0x3f, 0x17, 0x2f)}
CORSET = {"df272f": NAVY[0], "b71f2f": NAVY[1], "871737": NAVY[2], "5f1f37": NAVY[3], "3f172f": NAVY[4]}

# Expression by annotated clip name; (default, {frame: override}).
EXPRESSION = {
    "默认走路": "smile", "待机站立": "smile", "战斗待机": "fierce", "战斗跑": "fierce", "前冲": "shout",
    "前冲摔倒": "hurt", "碎霸": "shout", "召唤": "shout", "蹲伏": "smile", "杰克爆弹": "shout", "落花掌": "shout",
    "跳跃": "smile", "跳跃平A": "shout", "啦啦啦": "happy", "三段平A": "shout", "受击": "hurt", "受击倒地": "dizzy",
    "魔法星弹": "fierce", "加buff": "happy", "鞭挞": "shout", "魔道学者修东西": "smile", "魔道学者丢东西": "shout",
    "魔道学者修东西2": "smile", "召唤骑士": "fierce", "驱散": "happy",
}
EXPRESSION_FRAME = {30: "dizzy", 31: "dizzy", 32: "dizzy", 33: "dizzy", 34: "dizzy", 130: "hurt",
                    36: "back", 43: "back", 149: "back", 48: "frontshout", 172: "frontshout",
                    167: "front", 168: "front", 169: "front",
                    39: "cry", 40: "cry", 72: "cry", 73: "cry", 112: "cry", 113: "cry", 116: "cry", 117: "cry", 118: "cry",
                    124: "cry", 125: "cry", 126: "cry", 104: "cry", 105: "cry", 106: "cry", 107: "cry", 108: "cry",
                    156: "cry", 157: "cry", 160: "cry", 161: "cry", 162: "cry"}
# Apron center relative to the skirt axis in px; negative is towards the belly.
APRON_OFFSET_CLIP = {"待机站立": -4.0, "战斗待机": -4.0, "战斗跑": -3.0, "蹲伏": -3.0, "驱散": -3.0}
APRON_OFFSET = {48: -2.0, 49: -3.0, 50: -3.0, 51: -3.0, 52: -3.0, 172: -1.0, 167: -3.0, 168: -3.0, 169: -3.0}
# Hand-reviewed head orientation where the tracker was wrong: frame -> (angle, flip).
HEAD_OVERRIDE = {36: (-12, False), 43: (12, False), 149: (-12, False), 48: (-6, False), 49: (-30, False), 50: (-30, False),
                 51: (-30, False), 52: (-30, False), 134: (-90, False), 172: (0, False), 32: (12, False), 33: (12, False),
                 34: (6, False)}
# Implied forward speed the sprite itself does not show (root motion happens in the engine).
WIND = {"默认走路": 0.22, "战斗跑": 0.62, "前冲": 0.9, "前冲摔倒": 0.35}
TRAIL = {"默认走路": 0.25, "战斗跑": 1.2, "前冲": 1.6, "前冲摔倒": 0.6, "魔道学者丢东西": 0.5, "碎霸": 0.5, "落花掌": 0.3}
WAG = {"默认走路": 2.6, "待机站立": 1.5, "战斗待机": 2.0, "战斗跑": 3.2, "加buff": 3.0, "啦啦啦": 3.4}


def clips():
    data = json.loads(MOTION.read_text("utf-8"))
    return sorted(data["clips"], key=lambda c: c["start"])


def tracks():
    return json.loads(TRACK.read_text("utf-8"))["frames"]


def rot(angle, x, y):
    ca, sa = np.cos(np.radians(angle)), np.sin(np.radians(angle))
    return ca * x - sa * y, sa * x + ca * y


def centroid(world):
    alpha = np.array(world)[..., 3] > 0
    if not alpha.any():
        return None
    ys, xs = np.nonzero(alpha)
    return float(xs.mean()), float(ys.mean())


def skirt_top(index, head):
    """Waist = the skirt pixels nearest the head; the belt layer is a chain hanging lower."""
    alpha = np.array(layer_world("mg_pants0000a", index))[..., 3] > 0
    if not alpha.any():
        return head[0], head[1] + 30.0
    ys, xs = np.nonzero(alpha)
    direction = np.array([xs.mean() - head[0], ys.mean() - head[1]])
    direction /= max(np.hypot(*direction), 1e-6)
    along_axis = (xs - head[0]) * direction[0] + (ys - head[1]) * direction[1]
    top = along_axis <= np.percentile(along_axis, 8)
    return float(xs[top].mean()), float(ys[top].mean())


def wrap(angle):
    return float(np.arctan2(np.sin(angle), np.cos(angle)))


def apron_directions(out):
    """Place the apron at a fixed offset from the skirt's own axis.

    The native pumpkin charms are swinging pendants (IMG 5 throws them to the far side), so
    they say nothing about which way the dress faces. The body stays three-quarter almost
    throughout, so a constant offset towards the belly side is both correct and stable.
    Back-view frames show no apron.
    """
    for i in range(FRAMES):
        p = out[i]
        p["apron"] = None
        alpha = np.array(layer_world("mg_pants0000a", i))[..., 3] > 0
        if not alpha.any() or p["expression"] == "back":
            continue
        ys, xs = np.nonzero(alpha)
        waist = p["waist"]
        mid = np.array([xs.mean() - waist[0], ys.mean() - waist[1]])
        offset = APRON_OFFSET.get(i, APRON_OFFSET_CLIP.get(p["clip"], -5.5))
        if p["flip"]:
            offset = -offset
        reach = max(np.hypot(*mid) * 1.35, 1)
        p["apron"] = wrap(float(np.arctan2(mid[1], mid[0])) + float(np.arcsin(np.clip(offset / reach, -0.9, 0.9))))


def poses():
    """Per-frame head transform and body anchors; clip-level smoothing removes tracker jitter."""
    rows = tracks()
    out = {}
    for clip in clips():
        frames = list(range(clip["start"], clip["end"] + 1))
        angles = np.array([rows[i]["angle"] for i in frames], float)
        center = np.median(angles)
        for k, i in enumerate(frames):
            row = rows[i]
            delta = angles[k] - center
            # Small nods are mostly tracker noise and rotating re-samples every head pixel:
            # hold the clip angle so the head stays pixel-identical, only large turns rotate.
            angle = center if abs(delta) <= 15 else angles[k]
            angle = round(angle / 6) * 6
            flip = bool(row["flip"])
            if i in HEAD_OVERRIDE:
                angle, flip = HEAD_OVERRIDE[i]
            cx, cy = rot(angle, -CHIN_WORLD[0] if flip else CHIN_WORLD[0], CHIN_WORLD[1])
            # Whole-pixel chin: the same expression then reproduces identical head pixels.
            chin = (round(row["x"] + cx), round(row["y"] + cy))
            head = (float(row["x"]), float(row["y"]))
            waist = skirt_top(i, head)
            axis = np.array([waist[0] - head[0], waist[1] - head[1]], float)
            axis /= max(np.hypot(*axis), 1e-6)
            back = np.array([-axis[1], axis[0]]) * (-1 if flip else 1)
            expression = EXPRESSION_FRAME.get(i, EXPRESSION.get(clip["name"], "smile"))
            out[i] = dict(angle=float(angle), flip=flip, chin=chin, head=head, waist=waist, axis=axis, back=back,
                          expression=expression, clip=clip["name"])
    apron_directions(out)
    return out


def chain_step(nodes, previous, anchor, rest, segment, stiff, gravity, wind, damping=0.9, floor=None):
    velocity = (nodes - previous) * damping
    previous[:] = nodes
    nodes[1:] += velocity[1:]
    nodes[1:, 1] += gravity
    nodes[1:, 0] += wind
    nodes[1:] += (rest[1:] - nodes[1:]) * stiff[1:, None]
    nodes[0] = anchor
    for _ in range(6):
        delta = nodes[1:] - nodes[:-1]
        length = np.maximum(np.hypot(delta[:, 0], delta[:, 1]), 1e-6)
        correction = (delta.T * (1 - segment / length)).T
        nodes[1:] -= correction * 0.5
        nodes[:-1] += correction * 0.5
        nodes[0] = anchor
        if floor is not None:
            nodes[:, 1] = np.minimum(nodes[:, 1], floor)
    return nodes


def simulate(pose):
    """Run hair and tail chains over each clip. Returns {frame: (hair_nodes, tail_nodes)}."""
    result = {}
    H_N, T_N = 7, 7
    hair_len = 100 * HAIR_SCALE
    tail_len = 54 * TAIL_SCALE
    for clip in clips():
        frames = list(range(clip["start"], clip["end"] + 1))
        loop = bool(clip.get("loop"))
        wind_base = WIND.get(clip["name"], 0.0)
        wag = WAG.get(clip["name"], 1.2)
        trail = TRAIL.get(clip["name"], 0.0)
        n = len(frames)
        sub = 4
        steps = n * sub

        def anchors(position):
            k = int(position) % n
            t = position - int(position)
            a, b = pose[frames[k]], pose[frames[(k + 1) % n] if (loop or k + 1 < n) else frames[k]]
            lerp = lambda f: np.array(f(a), float) * (1 - t) + np.array(f(b), float) * t
            return lerp(hair_anchor), lerp(tail_anchor), lerp(lambda p: p["axis"]), lerp(lambda p: p["back"])

        def init(position):
            ha, ta, _, back = anchors(position)
            hair = np.array([ha + np.array([back[0] * 0.14, 1.0]) * j * hair_len / (H_N - 1) for j in range(H_N)])
            tail = np.array([ta + back * j * tail_len / (T_N - 1) for j in range(T_N)])
            return hair, tail

        hair, tail = init(0)
        phair, ptail = hair.copy(), tail.copy()
        records = {}
        stiff_h = np.linspace(0.5, 0.1, H_N)
        stiff_t = np.linspace(0.55, 0.14, T_N)
        total = steps * (4 if loop else 1) + (0 if loop else 40)
        for step in range(total):
            if loop:
                position = (step % steps) / sub
            else:
                position = max(0, step - 40) / sub
                position = min(position, n - 1)
            ha, ta, axis, back = anchors(position)
            phase = 2 * np.pi * ((step % steps) / steps if loop else step / (steps + 8))
            sign = -1 if pose[frames[0]]["flip"] else 1
            hair_dir = back * 0.14 + np.array([-trail * sign, 1.0])
            hair_dir = hair_dir / np.hypot(*hair_dir)
            rest_h = np.array([ha + hair_dir * j * hair_len / (H_N - 1)
                               + np.array([np.sin(phase + j * 0.5), 0]) * 0.9 * j / (H_N - 1) for j in range(H_N)])
            lift = np.array([-axis[0], -axis[1]])
            rest_t = [ta.copy()]
            for j in range(1, T_N):
                f = j / (T_N - 1)
                # Nearly straight out of the skirt: the painted fluke already rises on its own.
                sweep = back * 0.9 + lift * (-0.55 + 0.75 * f)
                sweep = sweep / np.hypot(*sweep)
                rest_t.append(rest_t[-1] + sweep * tail_len / (T_N - 1))
            rest_t = np.array(rest_t) + np.array([lift * np.sin(phase * (2 if loop and n >= 8 else 1) - j * 0.7) * wag * (j / (T_N - 1)) ** 1.4
                                                  for j in range(T_N)])
            wind = -wind_base * sign
            chain_step(hair, phair, ha, rest_h, hair_len / (H_N - 1), stiff_h, 0.12, wind, floor=GROUND - STYLE["floor_lift"])
            chain_step(tail, ptail, ta, rest_t, tail_len / (T_N - 1), stiff_t, 0.02, wind * 0.5, floor=GROUND)
            k = position
            if abs(k - round(k)) < 1e-6:
                records[int(round(k)) % n] = (hair.copy(), tail.copy())
        for j, i in enumerate(frames):
            result[i] = records[j]
    return result


def hair_anchor(p):
    ax, ay = rot(p["angle"], 4 if p["flip"] else -4, -8)
    return p["head"][0] + ax, p["head"][1] + ay


def tail_anchor(p):
    return np.array(p["waist"]) + p["back"] * 5 + p["axis"] * 9


def skirt_decoration(index, p):
    """Native skirt pixels -> navy skirt, gold band, white frill past the band, plus apron and bows."""
    native = layer_world("mg_pants0000a", index)
    raw = np.array(native)
    solid = raw[..., 3] > 0
    world = recolor(native, SKIRT)
    _, charms = charm_info(index, p)
    if not solid.any():
        return world, None, charms
    waist = np.array(p["waist"])
    ys, xs = np.nonzero(solid)
    dx, dy = xs - waist[0], ys - waist[1]
    rho, phi = np.hypot(dx, dy), np.arctan2(dy, dx)
    bins = ((phi + np.pi) / (2 * np.pi) * 90).astype(int) % 90
    rgb = raw[ys, xs, :3]
    is_band = np.array([tuple(c) in BAND for c in rgb])
    band = np.full(90, np.nan)
    for b in np.unique(bins[is_band]):
        band[b] = rho[is_band & (bins == b)].max()
    known = ~np.isnan(band)
    frill_pixels = np.zeros(len(xs), bool)
    if known.sum() >= 3:
        order = np.arange(90)
        filled = np.interp(order, order[known], band[known], period=90)
        frill_pixels = (rho > filled[bins] + 0.6) & ~is_band & np.isin(bins, np.nonzero(ndimage.binary_dilation(known, iterations=2))[0])
    out = np.array(world)
    shade = {(0x47, 0x3f, 0x3f): 0, (0x37, 0x2f, 0x2f): 0, (0x27, 0x1f, 0x1f): 1, (0x1f, 0x17, 0x17): 2, (0x17, 0x0f, 0x0f): 3}
    for k in np.nonzero(frill_pixels)[0]:
        level = shade.get(tuple(rgb[k]))
        if level is not None:
            out[ys[k], xs[k], :3] = tuple(int(WHITE[level][j:j + 2], 16) for j in (0, 2, 4))
    return Image.fromarray(out, "RGBA"), (solid, rho, phi, xs, ys), charms


def charm_info(index, p):
    """Orange ornaments in the native coat: skirt charms mark the front of the dress."""
    raw = np.array(layer_world("mg_coat0000a", index))
    orange = np.zeros(raw.shape[:2], bool)
    for color in ORANGE:
        orange |= (raw[..., 0] == color[0]) & (raw[..., 1] == color[1]) & (raw[..., 2] == color[2]) & (raw[..., 3] > 0)
    labels, count = ndimage.label(orange, structure=np.ones((3, 3)))
    charms = []
    for k in range(1, count + 1):
        ys, xs = np.nonzero(labels == k)
        charms.append(dict(x=float(xs.mean()), y=float(ys.mean()), size=len(xs), mask=(ys, xs)))
    waist = np.array(p["waist"])
    below = [c for c in charms if np.dot(np.array([c["x"], c["y"]]) - waist, p["axis"]) > 3 and c["size"] >= 10]
    direction = None
    if below:
        vec = np.mean([np.array([c["x"], c["y"]]) - waist for c in below], axis=0)
        direction = float(np.arctan2(vec[1], vec[0]))
    return direction, charms


def apron_layer(index, p, fields, direction):
    sprite = baked_parts()["apron"]
    solid = fields[0]
    waist = np.array(p["waist"])
    ys, xs = np.nonzero(solid)
    rho_all = np.hypot(xs - waist[0], ys - waist[1])
    phi_all = np.arctan2(ys - waist[1], xs - waist[0])
    bins = ((phi_all + np.pi) / (2 * np.pi) * 90).astype(int) % 90
    outer = np.zeros(90)
    np.maximum.at(outer, bins, rho_all)
    order = np.arange(90)
    valid = outer > 0
    radius = ndimage.grey_dilation(np.interp(order, order[valid], outer[valid], period=90), size=3, mode="wrap")
    centers = -np.pi + (order + 0.5) * 2 * np.pi / 90
    R0 = float(np.interp(direction, centers, radius, period=2 * np.pi))
    half, v0, v1 = APRON_WIDTH / 2, 0.06, 0.95

    def mapping(u, v):
        su = u / sprite.width * 2 - 1
        sv = v / sprite.height
        angle = direction + np.arcsin(np.clip(su * half / max(R0, 1), -0.98, 0.98))
        R = np.interp(angle, centers, radius, period=2 * np.pi)
        r = (v0 + (v1 - v0) * sv) * R
        return waist[0] + np.cos(angle) * r, waist[1] + np.sin(angle) * r

    colors = np.array(rasterize(sprite, mapping, outline=False))
    colors[~ndimage.binary_dilation(solid, iterations=1), 3] = 0
    mask = colors[..., 3] > 0
    if not mask.any():
        return None
    # Soft ring lets the apron read against the navy skirt.
    ring = ndimage.binary_dilation(mask) & ~mask
    colors[ring, :3] = tuple(int(NAVY[4][j:j + 2], 16) for j in (0, 2, 4))
    colors[ring, 3] = 255
    ex, ey = round(waist[0] + np.cos(direction) * R0 * 0.6), round(waist[1] + np.sin(direction) * R0 * 0.6)
    for row, line in enumerate(WHALE):
        for col, ch in enumerate(line):
            if ch != ".":
                px = int(round(ex + 5 - col if p["flip"] else ex - 5 + col))
                py = int(round(ey - 3 + row))
                if mask[py, px]:
                    colors[py, px, :3] = WHALE_COLORS[ch]
    # Gold bows sit on the skirt just outside the apron edges.
    bows = []
    for sign in (-1, 1):
        offset = np.arcsin(min(0.96, (half + 4) / max(R0, 1))) * sign
        angle = direction + offset
        r = 0.74 * np.interp(angle, centers, radius, period=2 * np.pi)
        spot = (round(waist[0] + np.cos(angle) * r), round(waist[1] + np.sin(angle) * r))
        if solid[spot[1], spot[0]]:
            bows.append(spot)
    return Image.fromarray(colors, "RGBA"), bows


def dress_coat(native, p):
    """Vest above the ribs stays white blouse; from the ribs down it becomes the navy corset."""
    raw = np.array(native)
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS]
    below = ((xx - p["waist"][0]) * p["axis"][0] + (yy - p["waist"][1]) * p["axis"][1]) >= -4
    vest = np.zeros(raw.shape[:2], bool)
    for color in VEST:
        vest |= (raw[..., 0] == color[0]) & (raw[..., 1] == color[1]) & (raw[..., 2] == color[2]) & (raw[..., 3] > 0)
    corset = raw.copy()
    corset[~(vest & below), 3] = 0
    plain = raw.copy()
    plain[vest & below, 3] = 0
    image = recolor(Image.fromarray(plain, "RGBA"), COAT)
    image.alpha_composite(recolor(Image.fromarray(corset, "RGBA"), CORSET))
    return image


def ahoge(p, swing, scale=1.0):
    """A springy antenna curl, drawn by hand so it can bounce with the head."""
    points = np.array([(-2, -39), (-3, -44), (-2, -48), (-5, -51), (-9, -51), (-12, -48)], float) * scale
    root = points[0]
    weights = np.linspace(0, 1, len(points)) ** 1.3
    ca, sa = np.cos(np.radians(swing * weights)), np.sin(np.radians(swing * weights))
    rel = points - root
    local = np.c_[rel[:, 0] * ca - rel[:, 1] * sa, rel[:, 0] * sa + rel[:, 1] * ca] + root
    if p["flip"]:
        local[:, 0] *= -1
    wx, wy = rot(p["angle"], local[:, 0], local[:, 1])
    wx, wy = wx + p["chin"][0], wy + p["chin"][1]
    t = np.linspace(0, len(points) - 1, 80)
    fine = np.arange(len(points))
    cx, cy = np.interp(t, fine, wx), np.interp(t, fine, wy)
    core = np.zeros((CANVAS, CANVAS), bool)
    light = np.zeros((CANVAS, CANVAS), bool)
    core[np.round(cy).astype(int), np.round(cx).astype(int)] = True
    thick = t < 4.2
    core[np.round(cy[thick]).astype(int), np.round(cx[thick] + 1).astype(int)] = True
    core[np.round(cy[t < 2.6] + 1).astype(int), np.round(cx[t < 2.6]).astype(int)] = True
    shine = (t > 0.5) & (t < 2.4)
    light[np.round(cy[shine]).astype(int), np.round(cx[shine]).astype(int)] = True
    rim = ndimage.binary_dilation(core, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~core
    out = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    out[rim] = (*INK, 255)
    out[core] = (44, 70, 170, 255)
    out[light] = (74, 110, 214, 255)
    return Image.fromarray(out, "RGBA")


def swings(pose):
    """Antenna swing per frame: follows head velocity within each clip, with a soft spring."""
    result = {}
    for clip in clips():
        frames = list(range(clip["start"], clip["end"] + 1))
        loop = bool(clip.get("loop"))
        angle, velocity = 0.0, 0.0
        for cycle in range(4 if loop else 1):
            for k, i in enumerate(frames):
                prev = pose[frames[k - 1]] if (k or loop) else pose[i]
                dx, dy = pose[i]["head"][0] - prev["head"][0], pose[i]["head"][1] - prev["head"][1]
                velocity += (dx * 3.2 + dy * 2.0) - angle * 0.34
                velocity *= 0.62
                angle += velocity
                result[i] = float(np.clip(angle, -32, 32))
    return result


_baked = {}


def baked_parts():
    if not _baked:
        lib = library()
        hair, h = bake(lib.hair, HAIR_SCALE)
        body, t = bake(lib.tail_body, TAIL_SCALE)
        fluke, f = bake(lib.tail_fluke, TAIL_SCALE)
        apron, _ = bake(lib.apron, APRON_WIDTH / lib.apron.width)
        _baked.update(hair=hair, hair_t=h, body=body, body_t=t, fluke=fluke, fluke_t=f, apron=apron)
    return _baked


def relax(nodes, passes=3):
    """Limit curvature: a 44px-wide lock folds onto itself around tight bends."""
    smooth = np.array(nodes, float)
    for _ in range(passes):
        smooth[1:-1] = smooth[1:-1] * 0.5 + (smooth[:-2] + smooth[2:]) * 0.25
    return smooth


def compose(index, p, nodes):
    lib = library()
    world = Image.new("RGBA", (CANVAS, CANVAS))
    hair_nodes, tail_nodes = relax(nodes[0]), relax(nodes[1], 1)
    # Back hair, then tail.
    baked = baked_parts()
    (hx0, hy0), (hx1, hy1) = baked["hair_t"](41, 2), baked["hair_t"](41, 104)
    hair_layer = rasterize(baked["hair"], along((hy0, hy1), ((hy0, hy1), (hx0, hx1), True), hair_nodes, 1.0))
    from_behind = p["expression"] == "back"
    if not from_behind:
        world.alpha_composite(hair_layer)
    # Tail: along art x from the base at the right to the fluke; the fluke rises from the centerline.
    tr = baked["body_t"]
    knots = [tr(14, 22), tr(22, 29), tr(34, 35), tr(68, 35)]
    us, vs = [k[0] for k in knots], [k[1] for k in knots]
    tail_map = along((tr(68, 0)[0], tr(14, 0)[0]), (us, vs, False), tail_nodes, 1.0, mirror=p["flip"])
    world.alpha_composite(rasterize(baked["body"], tail_map))
    tip = tail_nodes[-1] - tail_nodes[-3]
    # Art fluke points up from a tail heading left: rotate it with the tail tip direction.
    fluke_angle = np.degrees(np.arctan2(tip[1], tip[0])) - 180
    if p["flip"]:
        fluke_angle = np.degrees(np.arctan2(tip[1], tip[0]))
    root_x, root_y = tail_map(*[np.array([c]) for c in tr(17, 25)])
    world.alpha_composite(rasterize(baked["fluke"], rigid(baked["fluke_t"](17, 24), (root_x[0], root_y[0]), 1.0, fluke_angle, p["flip"])))
    # Native lower body. Body head is erased so it never peeks around the painted head.
    world.alpha_composite(recolor(layer_world("mg_pants0000d", index), SKIRT))
    body = np.array(recolor(layer_world("mg_body0000", index), SKIN))
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS]
    distance = np.hypot(xx - p["head"][0], yy - p["head"][1])
    # The native pointed ear sticks out on the back of the head, past the main disc.
    behind = (xx - p["head"][0]) * (-1 if p["flip"] else 1) < -5
    disc = (distance < STYLE["disc"][0]) | ((distance < STYLE["disc"][1]) & behind)
    body[disc, 3] = 0
    if STYLE["body_hook"]:
        body = STYLE["body_hook"](body, index)
    body_image = Image.fromarray(body, "RGBA")
    world.alpha_composite(body_image)
    world.alpha_composite(recolor(layer_world("mg_shoes0000b", index), SHOES))
    world.alpha_composite(recolor(layer_world("mg_shoes0000a", index), SHOES))
    skirt, fields, charms = skirt_decoration(index, p)
    if STYLE["under_skirt"]:
        world.alpha_composite(STYLE["under_skirt"](index, p))
    world.alpha_composite(skirt)
    direction = p["apron"]
    if fields is not None and direction is not None:
        apron = apron_layer(index, p, fields, direction)
        if apron is not None:
            apron, bows = apron
            world.alpha_composite(apron)
            for spot in bows:
                world.alpha_composite(rasterize(lib.gold, rigid((10, 8), spot, STYLE["gold"])))
    elif fields is not None:
        # Back view: no charms visible, the waist bow takes over.
        pass
    # Back bow behind the coat.
    bow_pos = np.round(np.array(p["waist"]) + p["back"] * (STYLE["bow_back"] if direction is not None else 0) + p["axis"] * 2)
    tilt = round((np.degrees(np.arctan2(p["axis"][1], p["axis"][0])) - 90) / 15) * 15
    world.alpha_composite(rasterize(lib.bow, rigid((21, 16), bow_pos, STYLE["bow"], tilt, p["flip"])))
    # Coat with skirt charms lifted out.
    coats = []
    for layer in ("mg_coat0000c", "mg_coat0000b", "mg_coat0000a"):
        native = layer_world(layer, index)
        raw = np.array(native)
        if layer == "mg_coat0000a":
            for c in charms:
                raw[c["mask"][0], c["mask"][1], 3] = 0
        else:
            # Back coat layers repeat the charm pixels wherever the front layer shows them on the skirt.
            for color in ORANGE:
                hit = (raw[..., 0] == color[0]) & (raw[..., 1] == color[1]) & (raw[..., 2] == color[2])
                raw[hit, 3] = 0
        native = Image.fromarray(raw, "RGBA")
        coats.append(dress_coat(native, p))
    for coat in coats:
        world.alpha_composite(coat)
    # Gold bows flanking the apron, tie at the chest where the native ornament sat.
    waist = np.array(p["waist"])
    chest = [c for c in charms if np.dot(np.array([c["x"], c["y"]]) - waist, p["axis"]) <= 3 and c["size"] >= 6]
    if chest:
        target = max(chest, key=lambda c: c["size"])
        world.alpha_composite(rasterize(lib.tie, rigid((15, 9), (round(target["x"]), round(target["y"])), STYLE["tie"], 0, p["flip"])))
    if from_behind:
        # Seen from behind, the long hair falls over the back of the dress.
        world.alpha_composite(hair_layer)
    world.alpha_composite(ahoge(p, p.get("swing", 0.0), STYLE["ahoge"]))
    # Painted head.
    head = lib.heads[p["expression"]]
    layer = rasterize(head, rigid(lib.pivots[p["expression"]], p["chin"], 1.0, p["angle"], p["flip"]))
    world.alpha_composite(layer)
    # Arms raised beside the oversized head stay in front of it.
    # Torso capsule from chin to waist stays under the head; anything outside it is an arm.
    start, end = np.array(p["chin"], float), np.array(p["waist"], float)
    span = end - start
    t = np.clip(((xx - start[0]) * span[0] + (yy - start[1]) * span[1]) / max((span ** 2).sum(), 1e-6), 0, 1)
    torso = np.hypot(xx - (start[0] + t * span[0]), yy - (start[1] + t * span[1])) < 10
    head_alpha = np.array(layer)[..., 3] > 0
    front = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    for piece in (body_image, *coats):
        arr = np.array(piece)
        hit = (arr[..., 3] > 0) & head_alpha & ~torso & ~disc
        front[hit] = arr[hit]
    world.alpha_composite(Image.fromarray(front, "RGBA"))
    # Native under-layers leave tiny isolated slivers once their neighbours are recolored.
    arr = np.array(world)
    labels, count = ndimage.label(arr[..., 3] > 0, structure=np.ones((3, 3)))
    if count > 1:
        sizes = np.bincount(labels.ravel())
        arr[(sizes < 24)[labels] & (labels > 0)] = 0
    if STYLE["clip_floor"]:
        arr[GROUND + 3:, :, 3] = 0
        arr[GROUND + 2, arr[GROUND + 2, :, 3] > 0] = (*INK, 255)
    return Image.fromarray(arr, "RGBA")


def render(selection=None):
    pose = poses()
    chains = simulate(pose)
    for i, value in swings(pose).items():
        pose[i]["swing"] = value
    (OUT / "native_frames").mkdir(parents=True, exist_ok=True)
    frames = {}
    for index in (selection if selection is not None else range(FRAMES)):
        frame = compose(index, pose[index], chains[index])
        frame.save(OUT / f"native_frames/{index:04d}.png")
        frames[index] = frame
        print(index, flush=True)
    return frames


if __name__ == "__main__":
    picks = [int(a) for a in sys.argv[1:]] or None
    render(picks)
