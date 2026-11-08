"""Frames 4-8 (user 5-9) on one drawing: the source moves only the raised hand, the head and the hair there, and its legs never move from frame 0.

Step `ref`: three copies of frame 0's drawing on gray, side by side, for one image edit that changes only the front arm and head (step `draw`, paid).
Step `compose`: each edited figure is aligned to the base by its legs, and only her upper body and the front arm come from the edit, so the legs,
gown and tail stay the base's pixels. Writes the raw sheet poses_idle_hold_v1_0.png that `sheet-cut idle_hold` reads.
"""
import json, os, sys
os.environ["PATCH_ID"] = "gpt_dragon_slayer_v03"
sys.path.insert(0, ".claude/skills/dnf-character-patch/scripts")
import numpy as np
from PIL import Image
from scipy import ndimage
from kit.config import P
from kit.art import matte
from kit import sheets

BASE = P.parts / "raw/idle_hold_base.png"  # frame 0 as the idle sheet drew it, frozen so re-cutting cannot change it
REF = P.parts / "refs/edit_idle_hand.png"
NAME = "edit_idle_hand_v1"
GRAY = (128, 128, 128)
K = 1.9  # base drawing pixels to edit pixels
SLOTS = 3

PROMPT = """Image 1 shows the same character three times, side by side, all identical. Redraw Image 1 exactly: the same three figures in the same places at the same size, the same colors, line weight and style, the same gown, wings, tail, hair, legs and shoes, on the same flat gray background, RGB 128 128 128.

Change only her front arm (the one at the right side of her body) and turn her head very slightly; everything else, especially the legs, gown, wings and tail, stays exactly as it is. Her other arm, hanging at the left of her hip with a closed fist, stays exactly as it is.
- Left figure: the front forearm comes forward, the relaxed open hand held in front of her at waist height. Her head turns very slightly towards the viewer.
- Middle figure: the front arm is bent and raised, the open hand held up in front of her chest at the right, fingers loose and slightly spread. Her head turns very slightly towards the viewer.
- Right figure: exactly the middle figure, but that raised hand is closed into a tight fist.

The front forearm and hand are bare peach skin, drawn in front of the sleeve drape, which hangs from her upper arm. No other changes, no text, no shadow."""


def figure_box():
    return Image.open(BASE).getchannel("A").getbbox()


def ref():
    base = Image.open(BASE).convert("RGBA")
    box = figure_box()
    fig = base.crop(box)
    fig = fig.resize((round(fig.width * K), round(fig.height * K)), Image.LANCZOS)
    board = Image.new("RGB", (2048, 1152), GRAY)
    for k in range(SLOTS):
        x = round(2048 * (k + 0.5) / SLOTS - fig.width / 2)
        board.paste(fig, (x, (1152 - fig.height) // 2), fig)
    REF.parent.mkdir(parents=True, exist_ok=True)
    board.save(REF)
    print(REF, fig.size)


def draw():
    return sheets.submit(NAME, PROMPT, [REF], "16:9", resolution="2k")


def aligned(k):
    """Edited figure k, back at base size, shifted so its legs sit on the base's legs."""
    base = Image.open(BASE).convert("RGBA")
    box = figure_box()
    w, h = round((box[2] - box[0]) * K), round((box[3] - box[1]) * K)
    raw = Image.open(P.parts / f"raw/{NAME}_0.png").convert("RGB").resize((2048, 1152), Image.LANCZOS)
    x = round(2048 * (k + 0.5) / SLOTS - w / 2)
    y = (1152 - h) // 2
    pad = 40
    crop = raw.crop((x - pad, y - pad, x + w + pad, y + h + pad))
    fig = matte(crop)
    small = fig.resize((round(fig.width / K), round(fig.height / K)), Image.LANCZOS)
    canvas = Image.new("RGBA", base.size)
    p = round(pad / K)
    canvas.paste(small, (box[0] - p, box[1] - p), small)
    a = np.asarray(base, float)
    b = np.asarray(canvas, float)
    legs = slice(box[1] + int((box[3] - box[1]) * 0.55), box[3])
    best = None
    for dy in range(-12, 13):
        for dx in range(-12, 13):
            s = np.roll(np.roll(b, dy, 0), dx, 1)
            d = np.abs(a[legs] - s[legs]).sum()
            if best is None or d < best[0]:
                best = (d, dx, dy)
    print("figure", k, "shift", best[1:])
    return np.roll(np.roll(b, best[2], 0), best[1], 1)


def compose():
    base = np.asarray(Image.open(BASE).convert("RGBA"), float)
    box = figure_box()
    h = box[3] - box[1]
    rows = (np.arange(base.shape[0]) - box[1]) / h
    # Upper body from the edit, blended over a band at the waist; below it the base, except where the front arm differs.
    upper = np.clip((0.5 - rows) / 0.06, 0, 1)[:, None] * np.ones(base.shape[1])[None]
    outs = []
    for k in range(SLOTS):
        edit = aligned(k)
        diff = (np.abs(edit - base)[..., :3].sum(2) > 90) & (rows[:, None] < 0.62)
        # The front arm is at the right of her body; legs differences elsewhere are only redraw noise.
        cx = (box[0] + box[2]) / 2
        arm = diff & (np.arange(base.shape[1])[None] > cx - 10)
        arm = ndimage.binary_opening(arm, iterations=1)
        arm = ndimage.binary_dilation(arm, iterations=4)
        weight = np.maximum(upper, ndimage.gaussian_filter(arm.astype(float), 2))
        under = base
        if k == 2:
            # Source frames 5 and 6 differ only in the fingers closing, so the fist frame is frame 5's picture with only the hand taken from the edit.
            under = np.asarray(outs[1], float)
            hand = (np.abs(edit - under)[..., :3].sum(2) > 90) & (rows[:, None] > 0.2) & (rows[:, None] < 0.5) & (np.arange(base.shape[1])[None] > cx + 10)
            hand = ndimage.binary_dilation(ndimage.binary_opening(hand, iterations=1), iterations=4)
            weight = ndimage.gaussian_filter(hand.astype(float), 2)
        out = under * (1 - weight[..., None]) + edit * weight[..., None]
        outs.append(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA"))
        outs[-1].save(P.out / f"dev/idle_hand_{k}.png")
    # The raw sheet: cell 0 is the base (frames 0-3), cells 1-3 are frames 4, 5 and 6. Same placement in every cell, so the legs line up.
    layout = sheets.load("idle_hold")
    raw = Image.new("RGB", (layout["width"], layout["height"]), GRAY)
    cw, ch = layout["width"] // layout["cols"], layout["height"]
    figs = [Image.open(BASE).convert("RGBA")] + outs
    s = min(cw * 0.9 / (box[2] - box[0]), ch * 0.85 / h)
    for k, im in enumerate(figs):
        f = im.crop(box)
        f = f.resize((round(f.width * s), round(f.height * s)), Image.LANCZOS)
        raw.paste(f, (k * cw + (cw - f.width) // 2, ch - f.height - 40), f)
    path = P.parts / "raw/poses_idle_hold_v1_0.png"
    raw.save(path)
    print(path)


if __name__ == "__main__":
    {"ref": ref, "draw": draw, "compose": compose}[sys.argv[1]]()
