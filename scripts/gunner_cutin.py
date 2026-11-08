"""Claude version of a gunner cut-in: a few redrawn key frames, the official camera motion carried over by optical flow.

    python scripts/gunner_cutin.py key 12          draw one key frame
    python scripts/gunner_cutin.py keys            draw the remaining key frames, using key 12 as the design
    python scripts/gunner_cutin.py render          build all frames and a comparison
"""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gunner_props import CLI, cut_key, load_img  # noqa: E402

PACK = "sprite_character_gunner_effect_cutin"
STEM = "atgunner_launcher_neo"
WORK = ROOT / "output/gunner_cutin/launcher_neo"
MODEL = "gpt-image-2.6-sunburst-native"
MASTER = ROOT / "output/claude_gunner_v02/parts/raw/claude_a_0.png"
IDENTITY = json.loads((ROOT / "design/claude_gunner/patch.json").read_text("utf-8"))["character"]["identity"]
W, H = 1067, 600
SEGMENTS = {0: (0, 4), 6: (5, 8), 10: (9, 11), 12: (12, 15), 18: (16, 25), 28: (26, 32), 35: (33, 39), 41: (40, 47)}

PROMPT = """Image 1 is the character authority: {identity} Keep her face, her very long straight orange hair, her orange flower hair ornament with the black ribbon, and her dress with its colors. Do not give her the sprite's clothes, hairstyle, goggles or skin exposure.

Image 2 is one frame from the dramatic camera shot of a 2D fantasy action game, on flat magenta. It decides the camera, framing and scale, where her head and arms are, and where the big machine is, and nothing about color or costume. Redraw the whole frame with the same composition, so it could be laid over Image 2: she is in the same place, in the same pose, wearing a fictional science-fiction exo-rig made of the same machine parts in the same places. Parts cut off by the frame edge stay cut off.

The camera position, zoom and crop must match Image 2 exactly: when Image 2 is a close-up of her face, draw that close-up; when she is tiny in Image 2, she is equally tiny here. The cream ceramic gun barrels have a dark inner core and thin gold rings; the rocket pods behind her are near-black boxes with rows of clay orange lights. She wears near-black harness straps and shoulder armor over her dress.

Design language for the machine: premium future hardware from a calm, thoughtful AI lab. Smooth glazed ceramic plates in warm cream white, matte near-black machinery, thin gold trim, and glowing seams in clay orange, RGB 217 119 87 to 232 112 48. Small red lights in the sprite become clay orange. No olive, no rust, no grime.
{extra}
Polished anime key-visual rendering: clean cel shading with soft gradients and even dark outlines. Keep it readable at a glance. No text, no logo. Background: completely flat uniform magenta, RGB 255 0 255, wherever Image 2 shows magenta, with no glow or shadow spilling onto it.
"""
EXPLOSION = "Do not draw the muzzle flashes, sparks and fireballs in Image 2; leave those places showing whatever machine is behind them."


def official():
    img, _ = load_img(PACK, STEM)
    pages = []
    for frame in img.frames:
        page = Image.new("RGBA", (W, H))
        picture = img.image(frame["index"]) if "link" not in frame else None
        if picture is not None:
            page.paste(picture.convert("RGBA"), (frame["x"], frame["y"]))
        pages.append(page)
    return img, pages


def key_ref(index, pages):
    path = WORK / "refs" / f"key{index:02d}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    board = Image.new("RGB", (W, H), (255, 0, 255))
    board.paste(pages[index], (0, 0), pages[index])
    board.resize((2048, 1152), Image.LANCZOS).save(path)
    return path


def draw_key(index, pages, design=None, version=1):
    name = f"key{index:02d}_v{version}"
    raw = WORK / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    if (raw / f"{name}_0.png").exists():
        return name, "exists"
    extra = "Image 3 is a finished key frame of this same shot: keep exactly her look and the machine's look.\n" if design else ""
    if index >= 40:
        extra += EXPLOSION + "\n"
    refs = [MASTER, key_ref(index, pages)] + ([design] if design else [])
    command = [sys.executable, str(CLI), "image", "--model", MODEL, "--prompt", PROMPT.format(identity=IDENTITY, extra=extra), "--n", "1", "--size", "16:9", "--resolution", "2k", "--background", "opaque", "--quality", "high", "--out", str(raw), "--name", name, "--timeout", "900"]
    for ref in refs:
        command += ["--image", str(ref)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    return name, result.returncode, result.stderr[-200:] if result.returncode else ""


def flow_warp(new_rgba, from_rgba, to_rgba):
    """Moves the new key frame by the motion between two official frames. Works on small images, so it follows the camera and the big shapes and not pixel noise."""
    def gray(page):
        a = np.asarray(page, np.float32)
        alpha = a[..., 3:4] / 255
        return (np.clip((a[..., :3] * alpha + 40 * (1 - alpha)).mean(2), 0, 255)).astype(np.uint8)

    scale = 0.5
    size = (int(W * scale), int(H * scale))
    a, b = cv2.resize(gray(to_rgba), size), cv2.resize(gray(from_rgba), size)
    flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 5, 41, 5, 7, 1.5, 0)
    flow = cv2.GaussianBlur(flow, (0, 0), 6)
    flow = cv2.resize(flow, (W, H)) / scale
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    source = np.asarray(new_rgba, np.float32)
    premultiplied = source.copy()
    premultiplied[..., :3] *= source[..., 3:4] / 255
    out = cv2.remap(premultiplied, xs + flow[..., 0], ys + flow[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    alpha = np.maximum(out[..., 3:4], 1e-3)
    out[..., :3] = np.clip(out[..., :3] * 255 / alpha, 0, 255)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def machine_box(page):
    """Extent of the solid figure, leaving out sparks and fireballs, which would stretch the box."""
    a = np.asarray(page, np.float32)
    solid = a[..., 3] > 128
    hot = (a[..., 0] > 170) & (a[..., 0] > a[..., 2] + 50)
    mask = ndimage.binary_opening(solid & ~hot, iterations=2)
    labels, count = ndimage.label(ndimage.binary_dilation(mask, iterations=4))
    if not count:
        return page.getbbox()
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    mask &= labels == (int(np.argmax(sizes)) + 1)
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def box_warp(new_rgba, from_box, to_box):
    """Scale and move the whole picture so one box lands on another: follows a camera pull-back that flow cannot."""
    sx, sy = (to_box[2] - to_box[0]) / max(1, from_box[2] - from_box[0]), (to_box[3] - to_box[1]) / max(1, from_box[3] - from_box[1])
    scale = (sx * sy) ** 0.5
    cx0, cy0 = (from_box[0] + from_box[2]) / 2, (from_box[1] + from_box[3]) / 2
    cx1, cy1 = (to_box[0] + to_box[2]) / 2, (to_box[1] + to_box[3]) / 2
    matrix = np.float32([[scale, 0, cx1 - cx0 * scale], [0, scale, cy1 - cy0 * scale]])
    source = np.asarray(new_rgba, np.float32).copy()
    source[..., :3] *= source[..., 3:4] / 255
    out = cv2.warpAffine(source, matrix, (W, H), flags=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    alpha = np.maximum(out[..., 3:4], 1e-3)
    out[..., :3] = np.clip(out[..., :3] * 255 / alpha, 0, 255)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def latest(index):
    return sorted((WORK / "raw").glob(f"key{index:02d}_v*_0.png"), key=lambda p: int(p.stem.split("_v")[1].split("_")[0]))[-1]


def load_key(index):
    picture = cut_key(latest(index))
    return picture.resize((W, H), Image.LANCZOS)


def render():
    img, pages = official()
    frames = {}
    keys = {i: load_key(i) for i in SEGMENTS if list((WORK / "raw").glob(f"key{i:02d}_v*_0.png"))}
    print("keys", sorted(keys))
    for key, (start, end) in SEGMENTS.items():
        if key not in keys:
            continue
        frames[key] = keys[key]
        if key >= 28:
            # The figure is whole in view here, so its official extent says where the camera went.
            art_box = machine_box(keys[key])
            for i in range(start, end + 1):
                # Fire covers the machine in the last segment, so its place comes from the frame before the fire.
                frames[i] = box_warp(keys[key], art_box, machine_box(pages[40] if key == 41 else pages[i]))
            continue
        # Chain outward from the key, so each step only has to explain a small motion.
        for direction, stop in ((1, end), (-1, start)):
            current = keys[key]
            for i in range(key + direction, stop + direction, direction):
                current = flow_warp(current, pages[i - direction], pages[i])
                frames[i] = current
    (WORK / "frames").mkdir(exist_ok=True)
    for i, page in frames.items():
        page.save(WORK / "frames" / f"{i:02d}.png")
    # Official muzzle flashes and fireballs go back on top in the last segment.
    for i in range(40, 48):
        if i in frames:
            a = np.asarray(pages[i], np.float32)
            value = a[..., :3].max(2)
            warm = (a[..., 0] > 150) & (value > 170) & (a[..., 0] > a[..., 2] + 40)
            # Fireballs have dark centers in places; fill them so the machine does not show through a hole.
            warm = ndimage.binary_fill_holes(ndimage.binary_closing(warm, iterations=4))
            labels, count = ndimage.label(warm)
            if count:
                sizes = ndimage.sum(warm, labels, range(1, count + 1))
                warm = np.isin(labels, [k + 1 for k, v in enumerate(sizes) if v >= 60])
            # Her official blonde hair and dark armor sit inside the filled area and must not come back.
            r, g, b = a[..., 0], a[..., 1], a[..., 2]
            # Only where her head is before the fire arrives; the same pale yellow is also the fireball's core.
            first = np.asarray(pages[40], np.float32)
            head = (first[..., 0] - first[..., 2] > 35) & (first[..., 0] - first[..., 2] < 100) & (first[..., 1] > 150) & (first[..., 0] > 190) & (first[..., 3] > 200)
            head = ndimage.binary_dilation(ndimage.binary_opening(head, iterations=1), iterations=5)
            hair = head & (r - b > 35) & (r - b < 100) & (g > 150) & (value < 250)
            armor = (value < 95) & (a[..., 3] > 200)
            warm &= ~(hair | armor)
            mask = cv2.GaussianBlur((warm * 255).astype(np.uint8), (0, 0), 2).astype(np.float32) / 255
            mask = np.clip(mask * 1.6, 0, 1)[..., None]
            base = np.asarray(frames[i], np.float32).copy()
            base[..., :3] = base[..., :3] * (1 - mask) + a[..., :3] * mask
            base[..., 3] = np.maximum(base[..., 3], a[..., 3] * mask[..., 0])
            frames[i] = Image.fromarray(base.astype(np.uint8), "RGBA")
            frames[i].save(WORK / "frames" / f"{i:02d}.png")
    cols, cell = 8, (200, 113)
    rows = 6
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1] * 2), (58, 66, 84))
    for i in range(48):
        x, y = (i % cols) * cell[0], (i // cols) * cell[1] * 2
        for r, page in enumerate((pages[i], frames.get(i))):
            if page is None:
                continue
            small = page.resize(cell, Image.LANCZOS)
            sheet.paste(small, (x, y + r * cell[1]), small)
    sheet.save(WORK / "compare.jpg", quality=88)
    print(WORK / "compare.jpg", len(frames))


def main():
    command = sys.argv[1]
    if command == "render":
        return render()
    _, pages = official()
    if command == "key":
        print(draw_key(int(sys.argv[2]), pages))
    elif command == "keys":
        with ThreadPoolExecutor(4) as pool:
            for result in pool.map(lambda i: draw_key(i, pages, None, 2), [i for i in SEGMENTS if i != 12]):
                print(result, flush=True)


if __name__ == "__main__":
    main()
