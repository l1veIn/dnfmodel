"""Appearance master for the Claude patch, and a game-size readability check.

Usage: python claude_gunner_master.py measure | refs | draw <name> | small <name> [<name> ...]
Each draw is submitted once, about $0.2.
"""
from __future__ import annotations

import sys

import numpy as np
from PIL import Image, ImageDraw

import fatfish_doll_parts as P
from claude_gunner import OUT, ROOT, layer_world, native_world
from fatfish_final_post import downscale, finish, grade, sharpen

RUN = OUT / "parts"
P.RUN = RUN
P.JOURNAL = RUN / "journal.json"
SOURCE = ROOT.parent / "fatfish_game/refs/ai_girl/claude.jpg"
SLOT = 0

PROMPT = """Full-body character art for a 2D action game, used as the appearance master for animation at very small size, so every shape must be large and readable.

Image 1 is the identity and costume authority: the same elegant young noble lady with long straight orange hair, amber eyes, calm composed expression, orange flower hair ornament with a black ribbon, high ruffled collar with an orange flower brooch and black cravat, cream-white blouse with a short capelet and full sleeves with frilled cuffs, black corset with gold buttons, and a long layered cream, black and orange gown with gold trim, orange flower bows and tassels, and a frilled hem. Keep her character and her color scheme, and simplify small ornaments into a few large clear shapes.
Image 2 is the pose and body proportions to copy: a tall slim woman in three-quarter view facing RIGHT, with both hands held together low in front of her. Copy only her pose, head size and body proportions, none of her colors, clothes or hair.

Do not draw the book. Her hands are empty.

Proportions, as fractions of total height from the top of her hair to the soles of her boots:
- Chin at 0.13: a small head, about eight heads tall with long legs. Tall adult proportions, NOT chibi.
- Waist at 0.32.
- Gown: floor-length, ending at 0.95 so both white lace-up boots stay visible below the hem. A full bell shape, 0.45 of her height wide at the hem, narrower than Image 1, with bold panels: cream center, orange front panel, black side panels.

Hair: very long straight orange hair falling behind her back, reaching the back of her knees, held together as one large smooth mass with a few clean strands. It extends behind her no more than 0.15 of her height and never covers the front of her body. No thin flying strands.

Colors: saturated warm orange hair, clean cream-white dress areas, true black panels, a little gold. Large flat areas of each.

Style: clean cel shading, bold dark outlines of even weight around every shape, flat saturated colors. No painterly texture, no pixel art.
Fill most of the image height, head and feet fully visible with a small margin. Background: completely flat uniform medium gray, RGB 128 128 128. No shadow, no floor, no effects, no text.
"""


def measure():
    body = np.asarray(layer_world("skin/gg_body0000", SLOT))[..., 3] > 0
    rows = np.nonzero(body.any(1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    height = bottom - top + 1
    print("body", top, bottom, "height", height)
    for y in range(top, bottom + 1, 5):
        print(f"  {(y - top) / height:.2f} width {int(body[y].sum())}")
    composite = native_world(SLOT).getbbox()
    print("composite bbox", composite)


def refs():
    (RUN / "refs").mkdir(parents=True, exist_ok=True)
    Image.open(SOURCE).convert("RGB").save(RUN / "refs/claude_source.png")
    world = native_world(SLOT)
    box = world.getbbox()
    crop = world.crop(box)
    scale = 860 // crop.height
    big = crop.resize((crop.width * scale, crop.height * scale), Image.NEAREST)
    board = Image.new("RGB", (1024, 1024), (128, 128, 128))
    board.paste(big, ((1024 - big.width) // 2, (1024 - big.height) // 2), big)
    board.save(RUN / "refs/pose_0.png")


def draw(name):
    (RUN / "prompts").mkdir(parents=True, exist_ok=True)
    (RUN / "prompts" / f"{name}.txt").write_text(PROMPT, "utf-8")
    raise SystemExit(P.submit(name, PROMPT, [RUN / "refs/claude_source.png", RUN / "refs/pose_0.png"], "1:1", resolution="1k", background="opaque"))


def cut(path):
    master = Image.open(path).convert("RGB")
    rgb = np.asarray(master, float)
    mask = np.abs(rgb - np.median(rgb[:8].reshape(-1, 3), axis=0)).max(2) > 14
    ys, xs = np.nonzero(mask)
    print(path.name, "bbox", xs.min(), ys.min(), xs.max(), ys.max(), "wh", xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)
    rgba = np.dstack([np.asarray(master), (mask * 255).astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA").crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def small(names, target=130, zoom=5):
    items = [("native 0", native_world(SLOT).crop(native_world(SLOT).getbbox()))]
    for name in names:
        figure = cut(RUN / f"raw/{name}.png")
        side = max(figure.size)
        square = Image.new("RGBA", (side, side))
        square.paste(figure, ((side - figure.width) // 2, side - figure.height))
        size = round(side * target / figure.height)
        color, a = downscale(square, (size, size))
        sprite = finish(sharpen(grade(color)), a)
        items.append((name, sprite.crop(sprite.getbbox())))
    width = sum(i.width + 14 for _, i in items) * zoom
    height = (max(i.height for _, i in items) + 8) * zoom
    board = Image.new("RGB", (width, height), (86, 97, 122))
    pen = ImageDraw.Draw(board)
    x = 0
    for label, image in items:
        big = image.resize((image.width * zoom, image.height * zoom), Image.NEAREST)
        board.paste(big, (x + 7 * zoom, height - big.height - 2 * zoom), big)
        pen.text((x + 6, 4), f"{label} {image.size}", fill="yellow")
        x += (image.width + 14) * zoom
    (OUT / "dev").mkdir(parents=True, exist_ok=True)
    board.save(OUT / "dev/small_test.png")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    action = sys.argv[1]
    if action == "measure":
        measure()
    elif action == "refs":
        refs()
    elif action == "draw":
        draw(sys.argv[2])
    else:
        small(sys.argv[2:])
