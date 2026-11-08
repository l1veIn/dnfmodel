"""HD video frame -> crisp native sprite.

Plain resizing is why the old H3 frames read grey and soft: thin dark lines average away.
This keeps line art by mixing in a dark-preserving sample, grades the frame towards the
master's contrast, and finishes with hard alpha, a shared palette and a clean outline.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

from .config import P

PAD = 200

INK = np.array(P.ink if P and P.ink else (16, 18, 46), np.float32)


def premultiplied(image):
    arr = np.asarray(image.convert("RGBA"), np.float32) / 255
    arr[..., :3] *= arr[..., 3:]
    return arr


def resize_channels(arr, size, resample=Image.Resampling.BOX):
    return np.stack([np.asarray(Image.fromarray(arr[..., c], "F").resize(size, resample)) for c in range(arr.shape[2])], axis=2)


def grade(rgb, contrast=None, saturation=None, pivot=0.42):
    """Deepen darks and restore color; video models lift blacks and desaturate. A pale costume can turn this down with `grade` in patch.json."""
    settings = P.grade if P else {}
    contrast = settings.get("contrast", 1.22) if contrast is None else contrast
    saturation = settings.get("saturation", 1.32) if saturation is None else saturation
    gray = rgb.mean(2, keepdims=True)
    out = gray + (rgb - gray) * saturation
    out = np.clip(pivot + (out - pivot) * contrast, 0, 1)
    shift = settings.get("cool_hue_shift")
    out = _shift_cool_hue(out, shift) if shift else out
    clean = settings.get("clean_whites")
    return _clean_whites(out, **(clean if isinstance(clean, dict) else {})) if clean else out


def _clean_whites(rgb, max_s=0.16, min_v=0.55, lift=0.8, keep_s=0.5, tint=0.025):
    """Whites a model shades with grey-mauve read dusty next to a dark costume. Lift them and give the shade a faint cool blue instead (hue 225), so aprons and frills look clean."""
    top = rgb.max(2)
    s = (top - rgb.min(2)) / np.maximum(top, 1e-6)
    # Pale skin is just as unsaturated; it is the one that is warm (red well above blue), so leave it.
    white = (s < max_s) & (top > min_v) & (rgb[..., 0] - rgb[..., 2] < 0.06)
    v = top ** lift
    c = v * (s * keep_s + tint * (1 - v))
    cool = np.stack([v - c, v - 0.75 * c, v], axis=2)
    return np.where(white[..., None], np.clip(cool, 0, 1), rgb)


def _shift_cool_hue(rgb, degrees):
    """Turn only the violet shades (hue 240-300), so a model's drift in the shadows can be corrected while skin and gold stay as drawn."""
    out = rgb.copy()
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cool = (b > g) & (b >= r) & (r >= g)
    span = np.maximum(b - g, 1e-4)
    out[..., 0] = np.where(cool, g + span * np.clip((r - g) / span + degrees / 60, 0, 1), r)
    return out


def downscale(image, size, line_keep=0.45):
    """Box-down colors, then darken each cell towards its darkest quartile so lines survive."""
    arr = premultiplied(image)
    alpha = np.maximum(arr[..., 3], 1e-4)
    rgb = np.clip(arr[..., :3] / alpha[..., None], 0, 1)
    small = resize_channels(arr, size)
    a = small[..., 3]
    color = np.clip(small[..., :3] / np.maximum(a, 1e-4)[..., None], 0, 1)
    # Darkest-sample map: luminance minimum over about one output pixel, ignoring empty background.
    h, w = arr.shape[:2]
    cell = max(1, int(round(w / size[0])))
    luminance = np.where(arr[..., 3] > 0.5, rgb.mean(2), 1.0)
    dark = ndimage.minimum_filter(luminance, size=cell)
    small_dark = np.asarray(Image.fromarray(dark.astype(np.float32), "F").resize(size, Image.Resampling.BOX))
    current = color.mean(2)
    # Only pull down where a real line is present, in proportion to how much darker it is.
    pull = np.clip(current - small_dark, 0, 1) * line_keep
    color = np.clip(color * (1 - pull / np.maximum(current, 1e-3))[..., None], 0, 1)
    return color, a


def sharpen(color, amount=0.55):
    image = Image.fromarray((color * 255).astype(np.uint8), "RGB")
    blur = np.asarray(image.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255
    return np.clip(color + (color - blur) * amount, 0, 1)


def finish(color, a, palette=None, outline=True, alpha_cut=0.42):
    """Hard alpha, optional shared palette, one-pixel selective outline; drop specks."""
    solid = a > alpha_cut
    labels, count = ndimage.label(solid, structure=np.ones((3, 3)))
    if count > 1:
        sizes = np.bincount(labels.ravel())
        solid &= sizes[labels] >= 10
    out = (color * 255).astype(np.uint8)
    if palette is not None:
        out = np.asarray(Image.fromarray(out, "RGB").quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB")).copy()
    rgba = np.zeros((*solid.shape, 4), np.uint8)
    rgba[..., :3] = out
    rgba[..., 3] = solid * 255
    if outline:
        edge = solid & ~ndimage.binary_erosion(solid, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
        mix = 0.72
        rgba[edge, :3] = (rgba[edge, :3] * (1 - mix) + INK * mix).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def build_palette(colors_alpha, count=64):
    """One palette per costume, so colors never crawl between frames."""
    pixels = np.concatenate([(c[a > 0.42] * 255).astype(np.uint8) for c, a in colors_alpha])
    return Image.fromarray(pixels.reshape(-1, 1, 3), "RGB").quantize(count, method=Image.Quantize.MEDIANCUT, kmeans=4)


def process(image, size, palette=None, **grade_args):
    color, a = downscale(image, size)
    return finish(sharpen(grade(color, **grade_args)), a, palette)


def matte(frame):
    """Cut the flat gray background; keep the main figure and things close to it."""
    rgb = np.asarray(frame.convert("RGB"), np.float32)
    border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3), rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
    background = np.median(border, axis=0)
    distance = np.abs(rgb - background).max(2)
    chroma = rgb.max(2) - rgb.min(2)
    luma = rgb.mean(2)
    solid = (distance > 12) & ((chroma > 10) | (luma > 185) | (luma < 62))
    solid = ndimage.binary_opening(solid, iterations=1)
    labels, count = ndimage.label(solid, structure=np.ones((3, 3)))
    if not count:
        raise RuntimeError("no subject")
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    main = sizes.argmax()
    near = ndimage.binary_dilation(labels == main, iterations=10)
    keep = np.isin(labels, np.unique(labels[near & (labels > 0)]))
    keep &= sizes[labels] >= 60
    # Small holes are shaded fabric the keying missed; real gaps between limbs are much larger.
    holes = ndimage.binary_fill_holes(keep) & ~keep
    hole_labels, hole_count = ndimage.label(holes)
    if hole_count:
        hole_sizes = np.bincount(hole_labels.ravel())
        keep |= (hole_sizes[hole_labels] < 260) & (hole_labels > 0)
    alpha = np.clip(ndimage.gaussian_filter(keep.astype(np.float32), 0.7) * 1.15, 0, 1) * ndimage.binary_dilation(keep)
    out = np.zeros((*keep.shape, 4), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = (alpha * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def placed_mask(alpha, window, scale, dx=0, dy=0):
    """Generated alpha at native scale in world coordinates, scaled about the window's bottom center."""
    x, y, side = window
    size = int(round(side * scale))
    small = np.asarray(alpha.resize((size, size), Image.Resampling.BOX)) > 110
    left, top = placement(window, scale, dx, dy)
    world = np.zeros((500 + PAD * 2, 500 + PAD * 2), bool)
    world[top + PAD:top + PAD + size, left + PAD:left + PAD + size] = small
    return world[PAD:PAD + 500, PAD:PAD + 500]


def placement(window, scale, dx=0, dy=0):
    x, y, side = window
    size = int(round(side * scale))
    return int(round(x + side / 2 - size / 2)) + dx, y + side - size + dy


def monotonic(scores):
    slots, frames = scores.shape
    best = scores[0].copy()
    back = np.zeros((slots, frames), int)
    for k in range(1, slots):
        top = np.maximum.accumulate(best)
        where = np.zeros(frames, int)
        pick = 0
        for f in range(frames):
            if best[f] >= best[pick]:
                pick = f
            where[f] = pick
        best = top + scores[k]
        back[k] = where
    path = [int(best.argmax())]
    for k in range(slots - 1, 0, -1):
        path.append(int(back[k, path[-1]]))
    return path[::-1]


def looping(scores):
    slots, frames = scores.shape
    best = None
    for period in range(max(12, slots * 2), 66):
        for start in range(6, frames - period):
            picks = [start + round(k * period / slots) for k in range(slots)]
            value = sum(scores[k, picks[k]] for k in range(slots))
            if best is None or value > best[0]:
                best = (value, picks)
    return best[1]
