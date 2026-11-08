"""Cuts each sample from magenta, reduces it to game size in the sprite's own coordinates, measures the fit and builds the comparison board."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit import art  # noqa: E402

art.INK = np.array((24, 18, 16), np.float32)
OUT = ROOT / "output" / "gunner_props_sample"
FACTS = json.loads((OUT / "facts.json").read_text("utf-8"))
MARGIN = 16
BACK = (70, 78, 98)


def cut(path):
    """Alpha from distance to magenta, then remove the pink spill on edge pixels."""
    rgb = np.asarray(Image.open(path).convert("RGB"), np.float32)
    key = np.array((255, 0, 255), np.float32)
    distance = np.sqrt(((rgb - key) ** 2).sum(2))
    alpha = np.clip((distance - 70) / 90, 0, 1)
    alpha = np.where(ndimage.binary_opening(alpha > 0.5, iterations=1) | (alpha > 0.95), alpha, 0)
    spill = np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1]
    edge = (alpha < 1) | ndimage.binary_dilation(alpha < 0.5, iterations=2)
    clean = rgb.copy()
    fix = edge & (spill > 12)
    clean[..., 0][fix] -= spill[fix] * 0.9
    clean[..., 2][fix] -= spill[fix] * 0.9
    return Image.fromarray(np.dstack([np.clip(clean, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")


def to_game(cutout, name):
    """The reference pasted the sprite centered at a whole zoom, so the same mapping brings the drawing back."""
    fact = FACTS[name]
    w, h = fact["size"]
    zoom = fact["zoom"]
    left, top = (1024 - w * zoom) // 2 - MARGIN * zoom, (1024 - h * zoom) // 2 - MARGIN * zoom
    box = (left, top, left + (w + MARGIN * 2) * zoom, top + (h + MARGIN * 2) * zoom)
    size = (w + MARGIN * 2, h + MARGIN * 2)
    color, a = art.downscale(cutout.crop(box), size, line_keep=0.5 if zoom < 20 else 0.15)
    return art.finish(art.sharpen(color, 0.35), a, outline=True, alpha_cut=0.45)


def on_back(image, zoom=1):
    page = Image.new("RGB", image.size, BACK)
    page.paste(image, (0, 0), image)
    return page.resize((page.width * zoom, page.height * zoom), Image.NEAREST)


def main():
    versions = dict(a.split("=") for a in sys.argv[1:]) or {"bomb": "bomb_v1", "mech": "mech_v1", "g2": "g2_v1"}
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
    body = Image.open(ROOT / "output/claude_gunner_v02/native_frames/0000.png").convert("RGBA")
    body = body.crop(body.getbbox())
    rows = []
    for name, raw in versions.items():
        new = to_game(cut(OUT / "raw" / f"{raw}_0.png"), name)
        new.save(OUT / f"{name}_game.png")
        old = Image.open(OUT / f"{name}_original.png").convert("RGBA")
        canvas = Image.new("RGBA", new.size, (0, 0, 0, 0))
        canvas.paste(old, (MARGIN, MARGIN))
        mo, mn = np.asarray(canvas)[..., 3] > 128, np.asarray(new)[..., 3] > 128
        iou = (mo & mn).sum() / (mo | mn).sum()
        outside = (mn & ~ndimage.binary_dilation(mo, iterations=2)).sum() / mn.sum()
        missing = (mo & ~ndimage.binary_dilation(mn, iterations=2)).sum() / mo.sum()
        print(name, raw, "game size", new.size, "IoU", round(float(iou), 3), "new outside old", round(float(outside), 3), "old not covered", round(float(missing), 3))
        rows.append((name, canvas, new))
    zoom = {"bomb": 2, "mech": 2, "g2": 6}
    labels = {"bomb": "原子弹", "mech": "白色机甲", "g2": "小型 G2"}
    W = 1180
    height = sum(max(r[2].height * zoom[r[0]], body.height) + 44 for r in rows)
    sheet = Image.new("RGB", (W, height), (40, 44, 56))
    pen = ImageDraw.Draw(sheet)
    y = 6
    for name, old, new in rows:
        pen.text((8, y), f"{labels[name]}：原版 x{zoom[name]} | 新画 x{zoom[name]} | 游戏尺寸（和大小姐同比例）原版、新画", fill=(255, 225, 120), font=font)
        y += 28
        x = 8
        for image in (old, new):
            big = on_back(image, zoom[name])
            sheet.paste(big, (x, y))
            x += big.width + 10
        panel = Image.new("RGB", (W - x - 8, max(new.height * zoom[name], body.height)), BACK)
        panel.paste(body, (6, panel.height - body.height), body)
        px = body.width + 16
        for image in (old, new):
            box = image.getbbox()
            part = image.crop(box)
            panel.paste(part, (px, panel.height - part.height - 6), part)
            px += part.width + 12
        sheet.paste(panel, (x, y))
        y += panel.height + 16
    sheet.save(OUT / "sample_compare.png")
    print(OUT / "sample_compare.png")


if __name__ == "__main__":
    main()
