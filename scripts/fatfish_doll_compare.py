"""Side-by-side native vs doll for chosen frames."""
from __future__ import annotations

import sys

from PIL import Image, ImageDraw

from fatfish_doll import ROOT
from fatfish_doll_render import OUT

NATIVE = ROOT / "materials/female_mage/reference_composite/frames"


def compare(indices, path, zoom=3, cols=6, half=70, height=150):
    width = half * 2
    rows = (len(indices) + cols - 1) // cols
    board = Image.new("RGB", (cols * width * zoom, rows * height * zoom * 2), (112, 124, 140))
    draw = ImageDraw.Draw(board)
    for k, i in enumerate(indices):
        doll = Image.open(OUT / f"native_frames/{i:04d}.png").convert("RGBA")
        world = Image.new("RGBA", (500, 500))
        world.alpha_composite(Image.open(NATIVE / f"{i:04d}.png").convert("RGBA"), (185, 0))
        box = doll.getbbox()
        cx = (box[0] + box[2]) // 2
        crop = (cx - half, 395 - height, cx + half, 395)
        x, y = (k % cols) * width * zoom, (k // cols) * height * zoom * 2
        for row, image in enumerate((world, doll)):
            big = image.crop(crop).resize((width * zoom, height * zoom), Image.NEAREST)
            board.paste(big, (x, y + row * height * zoom), big)
        draw.text((x + 4, y + 2), str(i), fill="yellow")
    board.save(path)


if __name__ == "__main__":
    compare([int(a) for a in sys.argv[1:]], OUT / "dev/compare.png")
