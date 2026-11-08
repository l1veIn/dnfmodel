"""Claude gunner `reload` sheet through gpt-image-2 with the original prompt and references, compared with the 2.6 sheet: whole figure and each hand against the official grip. Writes only to output/gunner_props/model_test3."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

os.environ["PATCH_ID"] = "claude_gunner"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
from kit.config import P  # noqa: E402
from kit.hands import sprite_hands  # noqa: E402
from kit.sheets import CLI, cell_origin, load  # noqa: E402
from kit.source import armed, native_world  # noqa: E402

OUT = ROOT / "output/gunner_props/model_test3"
NAME = sys.argv[1] if len(sys.argv) > 1 else "reload"
TAG = f"poses_{NAME}_v1"
MODEL = "gpt-image-2"
BACK = (128, 128, 128)


def on_gray(path, size):
    image = Image.open(path).convert("RGBA")
    page = Image.new("RGB", image.size, BACK)
    page.paste(image, (0, 0), image)
    return page.resize(size, Image.LANCZOS) if page.size != size else page


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    prompt = (P.parts / "prompts" / f"{TAG}.txt").read_text("utf-8")
    ref = P.parts / f"refs/poses_{NAME}.png"
    layout = load(NAME)
    name = f"{NAME}_gpt2"
    if not list(OUT.glob(f"{name}_0.*")):
        started = time.time()
        command = [sys.executable, str(CLI), "image", "--model", MODEL, "--prompt", prompt, "--n", "1", "--size", layout["size"], "--resolution", "2k", "--quality", "high", "--out", str(OUT), "--name", name, "--timeout", "600", "--image", str(P.master), "--image", str(ref)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        print("exit", result.returncode, round(time.time() - started), result.stderr[-240:] if result.returncode else "")
        if result.returncode:
            return
    new_path = next(OUT.glob(f"{name}_0.*"))
    print(new_path.name, Image.open(new_path).size, Image.open(new_path).mode)
    size = (layout["width"], layout["height"])
    old = on_gray(P.parts / f"raw/{TAG}_0.png", size)
    new = on_gray(new_path, size)
    source = Image.open(ref).convert("RGB")
    wide = Image.new("RGB", (size[0], size[1] * 3 + 12), (30, 30, 36))
    for row, page in enumerate((source, old, new)):
        wide.paste(page, (0, row * (size[1] + 6)))
    wide = wide.resize((wide.width * 5 // 8, wide.height * 5 // 8), Image.LANCZOS)
    wide.save(OUT / f"{NAME}_whole.png")
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
    span = 62
    crops = []
    for k, frame in enumerate(layout["frames"]):
        ox, oy, cx, cy = cell_origin(layout, k)
        for hand in sprite_hands(frame):
            x, y = cx + (hand[0] - ox) * layout["zoom"], cy + (hand[1] - oy) * layout["zoom"]
            half = span * layout["zoom"] / 2
            box = tuple(int(v) for v in (x - half, y - half, x + half, y + half))
            sprite = armed(native_world(frame), frame).crop((int(hand[0] - span / 2), int(hand[1] - span / 2), int(hand[0] + span / 2), int(hand[1] + span / 2)))
            crops.append((k, frame, sprite, old.crop(box), new.crop(box)))
    side = 170
    board = Image.new("RGB", (side * len(crops) + 8, side * 3 + 60), (40, 44, 56))
    pen = ImageDraw.Draw(board)
    for row, label in enumerate(("官方（带枪）", "2.6 native", "gpt-image-2")):
        pen.text((4, 4 + row * (side + 20)), label, fill=(255, 225, 120), font=font)
    for c, (k, frame, sprite, a, b) in enumerate(crops):
        for row, pic in enumerate((sprite, a, b)):
            shown = Image.new("RGB", pic.size, BACK)
            if pic.mode == "RGBA":
                shown.paste(pic, (0, 0), pic)
            else:
                shown = pic
            shown = shown.resize((side - 4, side - 4), Image.NEAREST if row == 0 else Image.LANCZOS)
            y = 24 + row * (side + 20)
            board.paste(shown, (c * side + 2, y))
            if row:
                pen.ellipse((c * side + side // 2 - 9, y + side // 2 - 9, c * side + side // 2 + 7, y + side // 2 + 7), outline=(255, 60, 60), width=2)
        pen.text((c * side + 4, 24), f"cell {k + 1}", fill=(255, 255, 0))
    board.save(OUT / f"{NAME}_hands.png")
    print(OUT / f"{NAME}_whole.png", OUT / f"{NAME}_hands.png", board.size, len(crops), "hands")


if __name__ == "__main__":
    main()
