"""Decode painted sheets back to true art pixels: grid-sampled, palette-locked, hard alpha."""
from __future__ import annotations

import numpy as np
from PIL import Image

from fatfish_doll import ROOT

PARTS = ROOT / "output/Fatfish_Doll_v03/parts"
EXPRESSIONS = ("smile", "shout", "fierce", "hurt", "happy", "dizzy")


def decode(image, cell, offset=(0, 0), alpha_cut=128):
    """Sample each art cell by its median opaque color."""
    pixels = np.array(image.convert("RGBA"))
    ox, oy = offset
    h, w = pixels.shape[:2]
    rows, cols = (h - oy) // cell, (w - ox) // cell
    out = np.zeros((rows, cols, 4), np.uint8)
    for r in range(rows):
        for c in range(cols):
            block = pixels[oy + r * cell:oy + (r + 1) * cell, ox + c * cell:ox + (c + 1) * cell].reshape(-1, 4)
            solid = block[block[:, 3] >= alpha_cut]
            if len(solid) * 2 >= len(block):
                out[r, c, :3] = np.median(solid[:, :3], axis=0)
                out[r, c, 3] = 255
    return Image.fromarray(out, "RGBA")


def best_offset(image, cell):
    """Grid phase that maximizes contrast across cell borders."""
    rgb = np.array(image.convert("RGB")).astype(int)
    dx = np.abs(np.diff(rgb, axis=1)).sum(2).sum(0)
    dy = np.abs(np.diff(rgb, axis=0)).sum(2).sum(1)
    phase_x = max(range(cell), key=lambda k: dx[(np.arange(len(dx)) + 1) % cell == k].mean())
    phase_y = max(range(cell), key=lambda k: dy[(np.arange(len(dy)) + 1) % cell == k].mean())
    return phase_x, phase_y


def lock_palette(images, colors):
    """One shared palette across a family of sprites, so expressions never shift hue."""
    opaque = [np.array(i)[np.array(i)[..., 3] > 0][:, :3] for i in images]
    stack = np.concatenate(opaque)
    probe = Image.fromarray(stack.reshape(-1, 1, 3), "RGB").quantize(colors, method=Image.Quantize.MEDIANCUT, kmeans=4)
    result = []
    for image in images:
        arr = np.array(image)
        mapped = np.array(image.convert("RGB").quantize(palette=probe, dither=Image.Dither.NONE).convert("RGB"))
        arr[..., :3] = mapped
        arr[arr[..., 3] == 0] = 0
        result.append(Image.fromarray(arr, "RGBA"))
    return result
