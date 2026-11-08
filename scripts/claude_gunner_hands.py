"""Make her hands meet the guns.

Guns are separate game layers drawn to fit the source sprite's hands, so a gap appears wherever her hand differs from the
sprite's. Three steps per armed frame:
  1. Find the sprite's hand: its visible skin touching the gun.
  2. Find her hand in the drawing and bend the arm so it lands there. The bend fades along the figure from the hand, so the
     torso, head and feet stay put.
  3. Paint the sprite's own hand pixels over the result, so the grip touches the gun exactly as in the source art.

Manual corrections go in design/claude_gunner/hand_overrides.json: {"<frame>": [[world_x, world_y], ...]} gives her hand position
per sprite hand in order, and null there means leave that hand alone.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from PIL import Image
from scipy import ndimage

from claude_gunner import OUT, RUN, layer_world, weapon_world
from fatfish_final_process import placement

GUNS = ("gg_rev0000b", "gg_rev0000c")
COVER = ("coat/gg_coat0000a", "coat/gg_coat0000b", "coat/gg_coat0000c", "coat/gg_coat0000d", "pants/gg_pants0000a", "hair/gg_hair0000a")
SEARCH = 22
SAME_HAND = 14
LARGEST_HAND = 60  # world px; a face or a bare leg is larger
MOST_MOVE = 26
OVERRIDES = RUN / "hand_overrides.json"


def _visible_skin(i):
    skin = np.asarray(layer_world("skin/gg_body0000", i))[..., 3] > 0
    for layer in COVER:
        skin &= np.asarray(layer_world(layer, i))[..., 3] == 0
    return skin


@lru_cache(maxsize=None)
def sprite_hands(i):
    """One entry per gun in this frame: the sprite's visible hand next to it, as (x, y, mask)."""
    skin = _visible_skin(i)
    found = []
    for layer in GUNS:
        gun = np.asarray(weapon_world(i, layer=layer))[..., 3] > 0
        labels, count = ndimage.label(gun, structure=np.ones((3, 3)))
        for part in range(1, count + 1):
            piece = labels == part
            if piece.sum() < 20:
                continue
            near = ndimage.binary_dilation(piece, iterations=2) & skin
            if near.sum() < 6:
                continue
            ys, xs = np.nonzero(near)
            found.append((float(xs.mean()), float(ys.mean()), ndimage.binary_dilation(piece, iterations=3) & skin))
    # One hand can touch two gun pieces (layers b and c are two halves of one grip).
    merged = []
    for x, y, mask in found:
        for m in merged:
            if (x - m[0]) ** 2 + (y - m[1]) ** 2 < SAME_HAND ** 2:
                m[2] = m[2] | mask
                ys, xs = np.nonzero(m[2])
                m[0], m[1] = float(xs.mean()), float(ys.mean())
                break
        else:
            merged.append([x, y, mask])
    return [tuple(m) for m in merged]


def skin_blobs(rgba, k):
    """Bare-skin blobs in her drawing, in hd pixels: (x, y, world_area). Peach is redder than the gown's cream."""
    r, g, b, a = [rgba[..., c].astype(np.int32) for c in range(4)]
    mask = (r - g >= 36) & (r - g <= 95) & (r > 195) & (b > 115) & (a > 128)
    mask = ndimage.binary_opening(mask, iterations=max(1, int(k / 2)))
    labels, count = ndimage.label(mask, structure=np.ones((3, 3)))
    blobs = []
    for part in range(1, count + 1):
        ys, xs = np.nonzero(labels == part)
        area = len(xs) / (k * k)
        if 1.5 <= area <= LARGEST_HAND:
            blobs.append((float(xs.mean()), float(ys.mean()), float(area)))
    return blobs


def geodesic_weight(alpha, seed, radius):
    """1 at the hand, fading to 0 at `radius` hd pixels measured along the figure; filled outward over the background."""
    step = 4
    small = ndimage.maximum_filter(alpha, size=step)[::step, ::step]
    h, w = small.shape
    sx, sy = int(np.clip(seed[0] / step, 0, w - 1)), int(np.clip(seed[1] / step, 0, h - 1))
    reach = np.full(small.shape, np.inf, np.float32)
    front = np.zeros(small.shape, bool)
    front[sy, sx] = True
    seen = front.copy()
    reach[front] = 0
    cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
    for distance in range(1, int(radius / step) + 2):
        front = ndimage.binary_dilation(front, structure=cross) & small & ~seen
        if not front.any():
            break
        reach[front] = distance * step
        seen |= front
    # The seed may sit just off the mask; the search above then stops at once, so start from the nearest figure pixel.
    weight = np.clip(1 - reach / radius, 0, 1)
    weight = weight * weight * (3 - 2 * weight)
    weight[~np.isfinite(reach)] = 0
    indices = ndimage.distance_transform_edt(~seen, return_distances=False, return_indices=True)
    weight = weight[indices[0], indices[1]]
    weight = ndimage.gaussian_filter(weight, 1.0)
    big = np.asarray(Image.fromarray(weight.astype(np.float32), "F").resize((alpha.shape[1], alpha.shape[0]), Image.Resampling.BILINEAR))
    return big


def nearest_figure(alpha, point):
    ys, xs = np.nonzero(alpha)
    best = np.argmin((xs - point[0]) ** 2 + (ys - point[1]) ** 2)
    return float(xs[best]), float(ys[best])


def bend(image, moves, k):
    """moves: [(hd_x, hd_y, hd_dx, hd_dy)]. Returns the image with each hand moved, the rest following smoothly."""
    rgba = np.asarray(image, np.float32)
    alpha = rgba[..., 3] > 128
    h, w = alpha.shape
    field_x, field_y = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
    for x, y, dx, dy in moves:
        length = (dx * dx + dy * dy) ** 0.5
        radius = float(np.clip(2.6 * length, 20 * k, 62 * k))
        weight = geodesic_weight(alpha, nearest_figure(alpha, (x, y)), radius)
        field_x += weight * dx
        field_y += weight * dy
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    sx, sy = xs.copy(), ys.copy()
    for _ in range(6):
        fx = ndimage.map_coordinates(field_x, [sy, sx], order=1, mode="nearest")
        fy = ndimage.map_coordinates(field_y, [sy, sx], order=1, mode="nearest")
        sx, sy = xs - fx, ys - fy
    premultiplied = rgba.copy()
    premultiplied[..., :3] *= rgba[..., 3:] / 255
    out = np.stack([ndimage.map_coordinates(premultiplied[..., c], [sy, sx], order=1) for c in range(4)], 2)
    a = np.maximum(out[..., 3:] / 255, 1e-3)
    out[..., :3] /= a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def overrides():
    return {int(k): v for k, v in json.loads(OVERRIDES.read_text("utf-8")).items()} if OVERRIDES.exists() else {}


def fit_clip(ident, report=None):
    """Writes hdfit/<slot>.png for armed frames and records what moved. Offsets must already be grounded."""
    folder = OUT / "clips" / ident
    path = folder / "selection.json"
    report = json.loads(path.read_text("utf-8"))
    window = report["window"]
    manual = overrides()
    (folder / "hdfit").mkdir(exist_ok=True)
    log = []
    for row in report["frames"]:
        slot = row["slot"]
        targets = sprite_hands(slot)
        row["hands"] = []
        if not targets:
            continue
        image = Image.open(folder / f"hd/{slot:04d}.png").convert("RGBA")
        size = int(round(window[2] * row["scale"]))
        k = image.width / size
        left, top = placement(window, row["scale"], row["offset"][0] + row["track"][0], row["offset"][1] + row["track"][1])
        blobs = skin_blobs(np.asarray(image), k)
        used, moves = set(), []
        for number, (tx, ty, _) in enumerate(targets):
            given = manual.get(slot)
            if given is not None and number < len(given):
                if given[number] is None:
                    row["hands"].append(dict(target=[round(tx), round(ty)], state="left alone"))
                    continue
                wx, wy = given[number]
                source = "manual"
            else:
                options = [(((left + b[0] / k - tx) ** 2 + (top + b[1] / k - ty) ** 2) ** 0.5, n) for n, b in enumerate(blobs) if n not in used]
                options = [o for o in options if o[0] <= SEARCH]
                if options:
                    _, n = min(options)
                    used.add(n)
                    wx, wy = left + blobs[n][0] / k, top + blobs[n][1] / k
                    source = "auto"
                else:
                    # Some drawings have pale hands that read as cream. Reach with the nearest part of her instead.
                    alpha = np.asarray(image.getchannel("A")) > 128
                    nx, ny = nearest_figure(alpha, ((tx - left) * k, (ty - top) * k))
                    wx, wy = left + nx / k, top + ny / k
                    source = "nearest"
            dx, dy = tx - wx, ty - wy
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > MOST_MOVE:
                row["hands"].append(dict(target=[round(tx), round(ty)], found=[round(wx), round(wy)], gap=round(distance, 1), state="too far"))
                continue
            moves.append(((wx - left) * k, (wy - top) * k, dx * k, dy * k))
            row["hands"].append(dict(target=[round(tx), round(ty)], found=[round(wx), round(wy)], gap=round(distance, 1), state=source))
        if moves:
            bend(image, moves, k).save(folder / f"hdfit/{slot:04d}.png")
        log.append((slot, row["hands"]))
    path.write_text(json.dumps(report, indent=1), "utf-8")
    return log


def graft(world, slot, palette=None):
    """Paint the sprite's own hand over her at the same pixels. Returns a new image."""
    hands = sprite_hands(slot)
    if not hands:
        return world
    rgba = np.array(world)
    source = np.asarray(layer_world("skin/gg_body0000", slot))
    for _, _, mask in hands:
        pixels = source[mask][:, :3]
        if palette is not None and len(pixels):
            patch = Image.fromarray(pixels.reshape(-1, 1, 3), "RGB").quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB")
            pixels = np.asarray(patch).reshape(-1, 3)
        rgba[mask, :3] = pixels
        rgba[mask, 3] = 255
    return Image.fromarray(rgba, "RGBA")
