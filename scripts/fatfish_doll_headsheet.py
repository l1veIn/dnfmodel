"""Review sheet: native head crop vs tracked transform, for hand-checking orientation of all frames."""
from __future__ import annotations

from PIL import Image, ImageDraw

from fatfish_doll import ROOT, layer_world
from fatfish_doll_render import OUT, poses

LAYERS = ("mg_body0000", "mg_hair0000b", "mg_hair0000a", "mg_face0000b", "mg_cap0000c")


def native(index):
    world = Image.new("RGBA", (500, 500))
    for layer in LAYERS:
        world.alpha_composite(layer_world(layer, index))
    return world


def main():
    pose = poses()
    half, zoom, cols = 20, 3, 15
    size = half * 2 * zoom
    rows = 174 // cols + 1
    board = Image.new("RGB", (cols * size, rows * size), (70, 80, 95))
    draw = ImageDraw.Draw(board)
    for i in range(174):
        x0, y0 = pose[i]["head"]
        crop = native(i).crop((int(x0) - half, int(y0) - half, int(x0) + half, int(y0) + half)).resize((size, size), Image.NEAREST)
        px, py = (i % cols) * size, (i // cols) * size
        board.paste(crop, (px, py), crop)
        draw.text((px + 2, py + 1), f"{i} {pose[i]['angle']:.0f}{'F' if pose[i]['flip'] else ''}", fill="yellow")
    board.save(OUT / "dev/head_review.png")


if __name__ == "__main__":
    main()
