"""Exact poses the video model cannot follow: draw a sheet of source poses in one image call, then cut the cells.

Fast actions (reload, clap, the walk) lose their hands in video because every frame differs. One call per sheet keeps the
character consistent across its cells and costs about $0.2.

Usage: claude_gunner_poses.py refs <sheet> | draw <sheet> [--version=N] | cut <sheet> [--version=N]
Sheets are defined in design/claude_gunner/pose_sheets.json; `clips` maps slots to cells, `ref_cells` are standing cells that set the size.
"""
from __future__ import annotations

import json
import shutil
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

import fatfish_doll_parts as P
from claude_gunner import OUT, RUN, figure_mask, native_world
from claude_gunner_process import best_shift
from fatfish_final_process import matte, placed_mask, placement

PARTS = OUT / "parts"
P.RUN = PARTS
P.JOURNAL = PARTS / "journal.json"
MASTER = PARTS / "raw/claude_a_0.png"
SHEETS = RUN / "pose_sheets.json"
SIZES = {"16:9": (2048, 1152), "1:1": (2048, 2048), "3:2": (2048, 1365)}
BACKDROP = (128, 128, 128)

PROMPT = """A clean animation pose sheet for a 2D action game.

Image 1 is the character and costume authority: the same tall slim elegant lady, with the same head size and proportions, very long straight orange hair, orange flower hair ornament with a black ribbon, high ruffled collar with an orange flower brooch and black cravat, cream capelet, full cream sleeves with frilled cuffs, black corset with gold buttons, floor-length bell gown with a cream center, orange front panel, black side panels, gold trim, orange flower bows and a frilled hem, white lace-up boots. Pale skin. Bare hands.

Image 2 is a grid of {count} poses from a game sprite, {cols} across and {rows} down. It decides everything about the pose and nothing about the costume. Redraw every cell with the character from Image 1, in the same place in the same cell, at the same height, in exactly that pose:
- The same head position and tilt, the same torso lean, the same facing.
- Each arm in exactly the same position as in that cell, from shoulder to elbow to hand, and her bare hand exactly where the sprite's hand is. Every hand must be clearly visible and never hidden by her hair or sleeves.
- Her feet exactly where the sprite's feet are.

{motion}

Keep her hair behind her back so it never covers her arms, hands or the front of her body. Every cell must be the same character at the same scale with the same colors. All her hands are empty: no gun, no weapon, no book.

Style: clean cel shading, bold dark outlines of even weight around every shape, flat saturated colors. No painterly texture, no pixel art. Background: completely flat uniform medium gray, RGB 128 128 128, with no grid lines, no borders, no shadow, no floor, no effects, no numbers and no text.
"""


def load(name):
    sheet = json.loads(SHEETS.read_text("utf-8"))[name]
    width, height = SIZES[sheet["size"]]
    cols, frames = sheet["cols"], sheet["frames"]
    rows = (len(frames) + cols - 1) // cols
    boxes = [native_world(i).getbbox() for i in frames]
    # The whole figure must fit: her gown and hair are wider than the sprite, so keep generous room.
    world_w = max(b[2] - b[0] for b in boxes) + sheet.get("pad_x", 70)
    world_h = max(b[3] - b[1] for b in boxes) + sheet.get("pad_y", 24)
    cell = (width // cols, height // rows)
    zoom = min(cell[0] / world_w, cell[1] / world_h)
    return dict(sheet, name=name, frames=frames, rows=rows, width=width, height=height, cell=cell, zoom=zoom, boxes=boxes)


def cell_origin(layout, k):
    """World point of the cell's top-left corner, keeping the sprite's soles level across cells."""
    cols = layout["cols"]
    cell = layout["cell"]
    box = layout["boxes"][k]
    world_w = cell[0] / layout["zoom"]
    world_h = cell[1] / layout["zoom"]
    center = (box[0] + box[2]) / 2
    bottom = max(b[3] for b in layout["boxes"]) if layout.get("level", True) else box[3]
    return center - world_w / 2, bottom + 10 - world_h, (k % cols) * cell[0], (k // cols) * cell[1]


def refs(name):
    layout = load(name)
    board = Image.new("RGB", (layout["width"], layout["height"]), BACKDROP)
    for k, i in enumerate(layout["frames"]):
        ox, oy, cx, cy = cell_origin(layout, k)
        world = native_world(i)
        crop = world.crop((round(ox), round(oy), round(ox + layout["cell"][0] / layout["zoom"]), round(oy + layout["cell"][1] / layout["zoom"])))
        big = crop.resize(layout["cell"], Image.Resampling.NEAREST)
        board.paste(big, (cx, cy), big)
    (PARTS / "refs").mkdir(parents=True, exist_ok=True)
    path = PARTS / f"refs/poses_{name}.png"
    board.save(path)
    return path


def draw(name, version=1):
    layout = load(name)
    path = refs(name)
    prompt = PROMPT.format(count=len(layout["frames"]), cols=layout["cols"], rows=layout["rows"], motion=layout["motion"])
    tag = f"poses_{name}_v{version}"
    (PARTS / "prompts").mkdir(parents=True, exist_ok=True)
    (PARTS / "prompts" / f"{tag}.txt").write_text(prompt, "utf-8")
    return P.submit(tag, prompt, [MASTER, path], layout["size"], resolution="2k", background="opaque")


def standing_height():
    """Hair top to sole of the kept video frames, so sheet frames match the size of the clips around them."""
    heights = []
    for i in range(14, 21):
        box = Image.open(OUT / f"native_frames/{i:04d}.png").getchannel("A").getbbox()
        heights.append(box[3] - box[1])
    return float(np.median(heights))


def sway(image, phase, amount=1.7):
    """A living idle from one drawing: the gown swings from the waist, the chest rises, the boots stay planted."""
    rgba = np.asarray(image, np.float32)
    box = image.getchannel("A").getbbox()
    height = box[3] - box[1]
    world = height / standing_height()
    ys, xs = np.mgrid[0:rgba.shape[0], 0:rgba.shape[1]].astype(np.float32)
    t = (ys - box[1]) / height
    below = np.clip((t - 0.3) / 0.62, 0, 1) ** 1.4
    planted = 1 - np.clip((t - 0.9) / 0.06, 0, 1)
    dx = amount * world * below * planted * np.sin(phase)
    chest = np.exp(-((t - 0.2) / 0.14) ** 2)
    dy = 0.8 * world * chest * np.sin(phase + np.pi / 2)
    out = np.stack([ndimage.map_coordinates(rgba[..., c] * (rgba[..., 3] / 255 if c < 3 else 1), [ys - dy, xs - dx], order=1) for c in range(4)], 2)
    a = np.maximum(out[..., 3:] / 255, 1e-3)
    out[..., :3] = out[..., :3] / a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def cut(name, version=1):
    """Cut the sheet's cells into clip folders that the normal render and grounding steps can use."""
    layout = load(name)
    raw = Image.open(PARTS / f"raw/poses_{name}_v{version}_0.png").convert("RGB")
    ratio = raw.width / layout["width"]
    cell_w, cell_h = raw.width // layout["cols"], raw.height // layout["rows"]
    side = max(cell_w, cell_h)
    zoom = layout["zoom"] * ratio
    window = [0, 0, int(round(side / zoom))]
    cells = []
    for k in range(len(layout["frames"])):
        x, y = (k % layout["cols"]) * cell_w, (k // layout["cols"]) * cell_h
        figure = matte(raw.crop((x, y, x + cell_w, y + cell_h)))
        square = Image.new("RGBA", (side, side))
        square.paste(figure, (0, 0))
        cells.append(square)
    if "head_ref" in layout:
        # Nothing here stands head over feet, so the size comes from her head width against a sheet that does.
        other = load(layout["head_ref"]["sheet"])
        head_world = layout["head_ref"]["ref_head_px"] / other["zoom"] * layout["head_ref"]["ref_scale"]
        scale = head_world / (layout["head_ref"]["head_px"] / layout["zoom"])
    else:
        # She stands about this much taller than the sprite in the kept frames; a lunge or a crouch lowers both alike.
        ratio = standing_height() / float(np.median([native_world(i).getbbox()[3] - native_world(i).getbbox()[1] for i in range(14, 21)]))
        fits = []
        for k in layout["ref_cells"]:
            box = cells[k].getchannel("A").getbbox()
            native = native_world(layout["frames"][k]).getbbox()
            fits.append(ratio * (native[3] - native[1]) / ((box[3] - box[1]) / zoom))
        scale = float(np.median(fits))
    size = int(round(window[2] * scale))
    grouped = {}
    for clip, slots in layout["clips"].items():
        folder = OUT / "clips" / clip
        if folder.exists():
            shutil.rmtree(folder)
        (folder / "hd").mkdir(parents=True)
        rows = []
        for entry in slots:
            slot, cell = entry["slot"], entry["cell"]
            image = cells[cell]
            if "phase" in entry:
                image = sway(image, entry["phase"] * np.pi)
            image.save(folder / f"hd/{slot:04d}.png")
            alpha = image.getchannel("A")
            box = alpha.getbbox()
            target = figure_mask(slot)
            target_rows = np.nonzero(target.any(1))[0]
            k = size / side
            native = native_world(layout["frames"][cell]).getbbox()
            # As drawn: same place in the cell, scaled about the soles.
            left0, top0 = placement(window, scale)
            dx = int(round((native[0] + native[2]) / 2 - (left0 + (box[0] + box[2]) / 2 * k)))
            dy = int(target_rows.max()) + 1 - int(round(top0 + box[3] * k))
            placed = placed_mask(alpha, window, scale, dx, dy)
            value, sx, sy = best_shift(placed, target, 14, 1)
            rows.append(dict(slot=slot, video_frame=f"{name}:{cell}", scale=round(float(scale), 3), offset=[dx + sx, dy], track=[0, 0], score=round(value, 3)))
        if "phase" in slots[0]:
            # One drawing: the only motion should be the sway itself.
            first = rows[0]["offset"]
            for row in rows:
                row["offset"] = list(first)
        grouped[clip] = rows
        (folder / "selection.json").write_text(json.dumps(dict(clip=clip, sheet=f"{name}_v{version}", window=window, base_scale=scale, frames=rows), indent=1), "utf-8")
        print(clip, "scale", round(scale, 3), [(r["slot"], r["offset"], r["score"]) for r in rows])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    action, target = sys.argv[1], sys.argv[2]
    version = next((int(a.split("=")[1]) for a in sys.argv[3:] if a.startswith("--version=")), 1)
    if action == "refs":
        print(refs(target))
    elif action == "cut":
        cut(target, version)
    else:
        raise SystemExit(draw(target, version))
