"""Dev previews: zoomed contact sheet and per-clip GIF loops over a game-like backdrop."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

from fatfish_doll import ROOT
from fatfish_doll_render import OUT, clips

BACK = (112, 124, 140, 255)


def load(index):
    return Image.open(OUT / f"native_frames/{index:04d}.png").convert("RGBA")


def sheet(indices, path, zoom=3, cols=8, size=(180, 140)):
    rows = (len(indices) + cols - 1) // cols
    board = Image.new("RGB", (cols * size[0] * zoom, rows * size[1] * zoom), BACK[:3])
    draw = ImageDraw.Draw(board)
    for k, i in enumerate(indices):
        crop = load(i).crop((250 - size[0] // 2, 392 - size[1], 250 + size[0] // 2, 392)).resize((size[0] * zoom, size[1] * zoom), Image.NEAREST)
        x, y = (k % cols) * size[0] * zoom, (k // cols) * size[1] * zoom
        board.paste(crop, (x, y), crop)
        draw.text((x + 3, y + 2), str(i), fill="yellow")
    board.save(path)


def gif(frames, path, zoom=3, size=(130, 140), ms=100):
    images = []
    for i in frames:
        base = Image.new("RGBA", (size[0], size[1]), BACK)
        base.alpha_composite(load(i).crop((250 - size[0] // 2, 392 - size[1], 250 + size[0] // 2, 392)))
        images.append(base.resize((size[0] * zoom, size[1] * zoom), Image.NEAREST).convert("P", palette=Image.ADAPTIVE, colors=128))
    images[0].save(path, save_all=True, append_images=images[1:], duration=ms, loop=0, disposal=2)


if __name__ == "__main__":
    picks = [int(a) for a in sys.argv[1:]]
    sheet(picks, OUT / "dev/sample.png")
