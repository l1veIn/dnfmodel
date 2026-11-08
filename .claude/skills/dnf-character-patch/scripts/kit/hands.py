"""Make her hands meet the weapon.

Weapons are separate game layers drawn to fit the source sprite's hands, so a gap appears wherever her hand differs from the
sprite's. Three steps per armed frame:
  1. Find the sprite's hand: its visible skin touching the weapon.
  2. Find her hand in the drawing and bend the arm so it lands there. The bend fades along the figure from the hand, so the
     torso, head and feet stay put.
  3. Paint the sprite's own hand pixels over the result, so the grip touches the weapon exactly as in the source art.

Manual corrections go in design/<id>/hand_overrides.json: {"<frame>": [[world_x, world_y], ...]} gives her hand position
per sprite hand in order; null there means leave that hand alone. {"ignore": {"<frame>": [<hand index>, ...]}} drops a false
hand, such as a blade touching a bare leg. {"use_contact": [<frame>, ...]} takes the grip from the handle instead of the skin, when the skin
target lands on a forearm (needs "grip_fallback": true in patch.json). {"grip": {"<frame>": [world_x, world_y]}} sets the grip by hand.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from PIL import Image
from scipy import ndimage

from .art import placement
from .config import P
from .source import layer_world, weapon_layers, weapon_world

SEARCH = 22
SAME_HAND = 14
LARGEST_HAND = 60  # world px; a face or a bare leg is larger
ARM_HALF_WIDTH = 4
GRIP_END = 0.3
HILT_DARK = 110  # the wrapped handle is much darker than the blade
GRIP_GAP_WIDEST = 20  # about a fist; wider means the weapon passes behind a leg or her body, and the middle of that is not a grip
CONTACT_SEARCH = 12  # with grip_gap: a grip this far from any hand is left as drawn, because the nearest skin may be the other hand
OVERRIDES = P.run / "hand_overrides.json"


def _overrides():
    return json.loads(OVERRIDES.read_text("utf-8")) if OVERRIDES.exists() else {}


def _visible_skin(i):
    skin = np.asarray(layer_world(P.body, i))[..., 3] > 0
    for layer in P.cover:
        skin &= np.asarray(layer_world(layer, i))[..., 3] == 0
    return skin


def _arms(i):
    """The skin layer's thin parts, costume ignored: gloves hide a hand from the visible skin, and a bare thigh is thick where an arm is thin."""
    skin = np.asarray(layer_world(P.body, i))[..., 3] > 0
    thick = ndimage.binary_opening(skin, iterations=ARM_HALF_WIDTH)
    arms = skin & ~ndimage.binary_dilation(thick, iterations=2)
    # A shin is as thin as an arm, but it ends in a boot.
    for layer in P.figure:
        if layer.startswith("shoes/"):
            arms &= ~ndimage.binary_dilation(np.asarray(layer_world(layer, i))[..., 3] > 0, iterations=6)
    return arms


def _hilt_first(i, found):
    """A one-handed long weapon has one grip. Among the contacts, the grip is beside the weapon's dark handle, not its bright blade."""
    world = np.zeros((P.canvas, P.canvas, 4), np.float32)
    for layer in weapon_layers():
        pixels = np.asarray(weapon_world(i, layer), np.float32)
        solid = pixels[..., 3] > 0
        world[solid] = pixels[solid]
    ys, xs = np.mgrid[0:P.canvas, 0:P.canvas]

    def brightness(hand):
        nearby = ((xs - hand[0]) ** 2 + (ys - hand[1]) ** 2 <= 64) & (world[..., 3] > 0)
        return world[nearby][:, :3].mean() if nearby.any() else 255.0

    return [min(found, key=brightness)]


def _grip_ends(piece):
    """Where a long weapon can be held: the two ends along its length. Its middle may cross her body without being held there."""
    ys, xs = np.nonzero(piece)
    center = np.array([xs.mean(), ys.mean()])
    points = np.stack([xs, ys], 1) - center
    axis = np.linalg.svd(points, full_matrices=False)[2][0]
    along = points @ axis
    low, high = along.min(), along.max()
    margin = (high - low) * GRIP_END
    keep = (along <= low + margin) | (along >= high - margin)
    mask = np.zeros_like(piece)
    mask[ys[keep], xs[keep]] = True
    return ndimage.binary_dilation(mask, iterations=4)


@lru_cache(maxsize=None)
def sprite_hands(i):
    """One entry per hand holding a weapon piece in this frame: (x, y, mask of the sprite's visible hand)."""
    given = _overrides().get("grip", {}).get(str(i))
    if given:
        return [(float(given[0]), float(given[1]), np.zeros((P.canvas, P.canvas), bool), "contact")]
    long_weapon = P.hand_detect == "arm_end"
    skin = _arms(i) if long_weapon else _visible_skin(i)
    found = []
    for layer in weapon_layers():
        gun = np.asarray(weapon_world(i, layer))[..., 3] > 0
        labels, count = ndimage.label(gun, structure=np.ones((3, 3)))
        for part in range(1, count + 1):
            piece = labels == part
            if piece.sum() < 20:
                continue
            allowed = _grip_ends(piece) if long_weapon else True
            near = ndimage.binary_dilation(piece, iterations=2) & skin & allowed
            if near.sum() < 6:
                continue
            ys, xs = np.nonzero(near)
            found.append((float(xs.mean()), float(ys.mean()), ndimage.binary_dilation(piece, iterations=3) & skin & allowed))
    # One hand can touch two weapon pieces (layers b and c are two halves of one grip).
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
    if long_weapon and len(merged) > 1 and P.grips_per_frame == 1:
        merged = _hilt_first(i, merged)
    if long_weapon and P.grip_fallback and (not merged or i in _overrides().get("use_contact", [])):
        merged = _hilt_contact(i)
    ignored = _overrides().get("ignore", {}).get(str(i), [])
    return [tuple(m) for n, m in enumerate(merged) if n not in ignored]


def _hilt_gap(solid):
    """Weapon art often leaves out the handle where the sprite's glove covers it. That gap, between the handle and the guard, is the grip."""
    labels, count = ndimage.label(solid, structure=np.ones((3, 3)))
    if count < 2:
        return None
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    first, second = np.argsort(sizes)[-2:]
    if sizes[first] < 12:
        return None
    distance, (nearest_y, nearest_x) = ndimage.distance_transform_edt(labels != second, return_indices=True)
    ys, xs = np.nonzero(labels == first)
    best = int(np.argmin(distance[ys, xs]))
    y, x = ys[best], xs[best]
    if not 2 <= distance[y, x] <= GRIP_GAP_WIDEST:
        return None
    return (float(x + nearest_x[y, x]) / 2, float(y + nearest_y[y, x]) / 2)


def _hilt_contact(i):
    """Gloved or covered hands leave no skin to find. The grip is where the weapon's dark handle meets the sprite's figure (or its sleeve at the end of the handle)."""
    world = np.zeros((P.canvas, P.canvas, 4), np.uint8)
    for layer in weapon_layers():
        pixels = np.asarray(weapon_world(i, layer))
        solid = pixels[..., 3] > 0
        world[solid] = pixels[solid]
    solid = world[..., 3] > 0
    if solid.sum() < 20:
        return []
    if P.grip_gap:
        gap = _hilt_gap(solid)
        if gap:
            return [[gap[0], gap[1], np.zeros((P.canvas, P.canvas), bool), "contact"]]
    hilt = solid & (world[..., :3].astype(np.int32).mean(2) < HILT_DARK)
    labels, count = ndimage.label(hilt, structure=np.ones((3, 3)))
    if not count:
        return []
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    hilt = labels == sizes.argmax()
    if hilt.sum() < 6:
        return []
    figure = np.zeros((P.canvas, P.canvas), bool)
    for layer in P.cover + (P.body,):
        if layer.startswith("hair/"):
            continue
        figure |= np.asarray(layer_world(layer, i))[..., 3] > 0
    near = ndimage.binary_dilation(hilt, iterations=2) & figure
    if near.sum() < 4:
        return []
    ys, xs = np.nonzero(near)
    # An empty mask: nothing to paint over, the hand only has to arrive.
    return [[float(xs.mean()), float(ys.mean()), np.zeros((P.canvas, P.canvas), bool), "contact"]]


def skin_blobs(rgba, k):
    """Bare-skin blobs in her drawing, in hd pixels: (x, y, world_area). Peach is redder than a cream costume; tune skin_rule per character."""
    rule = P.skin_rule
    r, g, b, a = [rgba[..., c].astype(np.int32) for c in range(4)]
    low, high = rule["red_minus_green"]
    mask = (r - g >= low) & (r - g <= high) & (r > rule["red_min"]) & (b > rule["blue_min"]) & (a > 128)
    if rule.get("blue_below_green"):
        # Pale skin beside lilac shadows: red-green alone cannot part them, but only skin has less blue than green.
        mask &= b < g
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
    weight = np.clip(1 - reach / radius, 0, 1)
    weight = weight * weight * (3 - 2 * weight)
    weight[~np.isfinite(reach)] = 0
    indices = ndimage.distance_transform_edt(~seen, return_distances=False, return_indices=True)
    weight = weight[indices[0], indices[1]]
    weight = ndimage.gaussian_filter(weight, 1.0)
    return np.asarray(Image.fromarray(weight.astype(np.float32), "F").resize((alpha.shape[1], alpha.shape[0]), Image.Resampling.BILINEAR))


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


def fit_clip(ident):
    """Writes hdfit/<slot>.png for armed frames and records what moved. Offsets must already be grounded."""
    folder = P.out / "clips" / ident
    path = folder / "selection.json"
    report = json.loads(path.read_text("utf-8"))
    window = report["window"]
    manual = {int(k): v for k, v in _overrides().items() if k not in ("ignore", "use_contact", "grip")}
    (folder / "hdfit").mkdir(exist_ok=True)
    log = []
    for row in report["frames"]:
        slot = row["slot"]
        targets = sprite_hands(slot) if weapon_layers() else []
        row["hands"] = []
        if not targets:
            continue
        image = Image.open(folder / f"hd/{slot:04d}.png").convert("RGBA")
        size = int(round(window[2] * row["scale"]))
        k = image.width / size
        left, top = placement(window, row["scale"], row["offset"][0] + row["track"][0], row["offset"][1] + row["track"][1])
        blobs = skin_blobs(np.asarray(image), k)
        used, moves = set(), []
        for number, target in enumerate(targets):
            tx, ty = target[0], target[1]
            contact = len(target) > 3
            given = manual.get(slot)
            if given is not None and number < len(given):
                if given[number] is None:
                    row["hands"].append(dict(target=[round(tx), round(ty)], state="left alone"))
                    continue
                wx, wy = given[number]
                source = "manual"
            else:
                options = [(((left + b[0] / k - tx) ** 2 + (top + b[1] / k - ty) ** 2) ** 0.5, n) for n, b in enumerate(blobs) if n not in used]
                options = [o for o in options if o[0] <= (CONTACT_SEARCH if contact and P.grip_gap else SEARCH)]
                if options:
                    _, n = min(options)
                    used.add(n)
                    wx, wy = left + blobs[n][0] / k, top + blobs[n][1] / k
                    source = "contact" if contact else "auto"
                elif contact:
                    # A contact is only a guess at the grip, so never drag a body part to it when no hand is near.
                    row["hands"].append(dict(target=[round(tx), round(ty)], state="no hand near"))
                    continue
                else:
                    # Some drawings have pale hands that read as costume. Reach with the nearest part of her instead.
                    alpha = np.asarray(image.getchannel("A")) > 128
                    nx, ny = nearest_figure(alpha, ((tx - left) * k, (ty - top) * k))
                    wx, wy = left + nx / k, top + ny / k
                    source = "nearest"
            dx, dy = tx - wx, ty - wy
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > P.most_move:
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
    hands = sprite_hands(slot) if P.graft and weapon_layers() else []
    if not hands:
        return world
    rgba = np.array(world)
    source = np.asarray(layer_world(P.body, slot))
    for hand in hands:
        mask = hand[2]
        pixels = source[mask][:, :3]
        if palette is not None and len(pixels):
            patch = Image.fromarray(pixels.reshape(-1, 1, 3), "RGB").quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB")
            pixels = np.asarray(patch).reshape(-1, 3)
        rgba[mask, :3] = pixels
        rgba[mask, 3] = 255
    return Image.fromarray(rgba, "RGBA")
