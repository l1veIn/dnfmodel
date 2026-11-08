"""HD video frame -> crisp native sprite.

Plain resizing is why the old H3 frames read grey and soft: thin dark lines average away.
This keeps line art by mixing in a dark-preserving sample, grades the frame towards the
master's contrast, and finishes with hard alpha, a shared palette and a clean outline.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

INK = np.array((16, 18, 46), np.float32)


def premultiplied(image):
    arr = np.asarray(image.convert("RGBA"), np.float32) / 255
    arr[..., :3] *= arr[..., 3:]
    return arr


def resize_channels(arr, size, resample=Image.Resampling.BOX):
    return np.stack([np.asarray(Image.fromarray(arr[..., c], "F").resize(size, resample)) for c in range(arr.shape[2])], axis=2)


def grade(rgb, contrast=1.22, saturation=1.32, pivot=0.42):
    """Deepen darks and restore color; video models lift blacks and desaturate."""
    gray = rgb.mean(2, keepdims=True)
    out = gray + (rgb - gray) * saturation
    return np.clip(pivot + (out - pivot) * contrast, 0, 1)


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
