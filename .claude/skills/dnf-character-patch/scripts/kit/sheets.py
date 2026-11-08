"""The master and pose sheets, drawn through the 65535 image CLI. One recorded request per name; never resubmits. About $0.2 per call.

A sheet is one image of many source poses redrawn as the character. One call keeps her consistent across cells and, unlike video,
holds every hand and every fast pose. Sheets live in design/<id>/pose_sheets.json.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from .art import downscale, finish, grade, matte, placed_mask, placement, sharpen
from .config import ROOT, P
from .hands import sprite_hands
from .process import best_shift
from .source import figure_mask, native_world, weapon_layers

CLI = Path(r"C:\Users\A\Desktop\fatfish_game\.agents\skills\65535\scripts\s65535.py")
MODEL = "gpt-image-2.6-sunburst-native"
SHEETS = P.run / "pose_sheets.json"
JOURNAL = P.parts / "journal.json"
SIZES = {"16:9": (2048, 1152), "1:1": (2048, 2048), "3:2": (2048, 1365)}
BACKDROP = (128, 128, 128)

SHEET_PROMPT = """A clean animation pose sheet for a 2D action game.

Image 1 is the character and costume authority: {identity} Keep the same head size and proportions as Image 1.

Image 2 is a grid of {count} poses from a game sprite, {cols} across and {rows} down. It decides everything about the pose and nothing about the costume. Redraw every cell with the character from Image 1, in the same place in the same cell, at the same height, in exactly that pose:
- The same head position and tilt, the same torso lean, the same facing.
- Each arm in exactly the same position as in that cell, from shoulder to elbow to hand, and each hand exactly where the sprite's hand is. Every hand must be clearly visible and never hidden by hair or sleeves.
- Her feet exactly where the sprite's feet are.

{motion}

The sprite faces to the right of the image, so forward is to the right unless the motion says otherwise. Anything loose, such as long hair, ribbons and hems, trails behind the direction she moves and never leads it. Keep long hair off her arms, hands and the front of her body. Every cell must be the same character at the same scale with the same colors. {hands_rule}

Style: {style} No painterly texture, no pixel art. Background: completely flat uniform medium gray, RGB 128 128 128, with no grid lines, no borders, no shadow, no floor, no effects, no numbers and no text.
"""
DEFAULT_STYLE = "clean cel shading, bold dark outlines of even weight around every shape, flat saturated colors."
GRIP_DOT = (255, 0, 255)
GRIP_NOTE = " A solid magenta dot in a cell of Image 2 marks exactly where one of her closed fists goes: draw a bare fist right on that dot, joined to her arm, in front of her hair, wings and skirt. The dots are only guides, so no magenta appears anywhere in your drawing."


COST = {"16:9": 0.22, "3:2": 0.29, "1:1": 0.39}  # dollars per image at 2k, from account balance differences; an estimate, not a bill
COST_1K = 0.24  # a 1k square master: four measured at $0.19 to $0.24


def preflight():
    """Stop before paying if patch.json still has placeholders."""
    fields = [P.title, P.notes, *P.character.values()]
    missing = [text for text in fields if "TODO" in str(text)]
    if missing:
        raise SystemExit(f"patch.json still has TODO fields: {missing}")


def spent():
    journal = json.loads(JOURNAL.read_text("utf-8")) if JOURNAL.exists() else {}
    return sum(COST_1K if entry.get("resolution") == "1k" else COST.get(entry["size"], 0.39) for entry in journal.values())


def cost():
    journal = json.loads(JOURNAL.read_text("utf-8")) if JOURNAL.exists() else {}
    print(len(journal), "images, estimated $", round(spent(), 2), "| failed:", [name for name, entry in journal.items() if entry.get("exit")])


def submit(name, prompt, refs, size, resolution="1k", background="opaque"):
    preflight()
    P.parts.mkdir(parents=True, exist_ok=True)
    journal = json.loads(JOURNAL.read_text("utf-8")) if JOURNAL.exists() else {}
    if name in journal:
        raise RuntimeError(f"{name} already submitted; use a new name or version instead of resubmitting")
    (P.parts / "raw").mkdir(parents=True, exist_ok=True)
    journal[name] = dict(model=MODEL, size=size, resolution=resolution, refs=[str(r) for r in refs], prompt=prompt, started=time.time())
    JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), "utf-8")
    command = [sys.executable, str(CLI), "image", "--model", MODEL, "--prompt", prompt, "--n", "1", "--size", size, "--resolution", resolution,
               "--background", background, "--quality", "high", "--out", str(P.parts / "raw"), "--name", name, "--timeout", "900"]
    for ref in refs:
        command += ["--image", str(ref)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    journal = json.loads(JOURNAL.read_text("utf-8"))
    journal[name].update(exit=result.returncode, finished=time.time())
    JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), "utf-8")
    print(name, "exit", result.returncode, P.parts / "raw" / f"{name}_0.png")
    return result.returncode


# Master

def master_refs():
    (P.parts / "refs").mkdir(parents=True, exist_ok=True)
    source = Path(P.character["reference_image"])
    Image.open(source).convert("RGB").save(P.parts / "refs/character_source.png")
    world = native_world(P.standing[0])
    crop = world.crop(world.getbbox())
    scale = 860 // crop.height
    big = crop.resize((crop.width * scale, crop.height * scale), Image.NEAREST)
    board = Image.new("RGB", (1024, 1024), BACKDROP)
    board.paste(big, ((1024 - big.width) // 2, (1024 - big.height) // 2), big)
    board.save(P.parts / "refs/pose_standing.png")
    print(P.parts / "refs")


def master_draw(name):
    prompt = (P.run / "master_prompt.txt").read_text("utf-8")
    (P.parts / "prompts").mkdir(parents=True, exist_ok=True)
    (P.parts / "prompts" / f"{name}.txt").write_text(prompt, "utf-8")
    return submit(name, prompt, [P.parts / "refs/character_source.png", P.parts / "refs/pose_standing.png"], "1:1")


def _raw(name):
    """A drawing by the name given to master-draw or by its file name: master_a and master_a_0 both work."""
    path = P.parts / f"raw/{name}.png"
    return path if path.exists() else P.parts / f"raw/{name}_0.png"


def master_edit(name, source):
    """Change a finished master in place: it is the only reference, so what the prompt leaves alone stays almost untouched. Prompt in design/<id>/master_prompt_<name>.txt."""
    prompt = (P.run / f"master_prompt_{name}.txt").read_text("utf-8")
    (P.parts / "prompts").mkdir(parents=True, exist_ok=True)
    (P.parts / "prompts" / f"{name}.txt").write_text(prompt, "utf-8")
    return submit(name, prompt, [_raw(source)], "1:1")


def _grid(path, name):
    """The master with lines at each 0.05 of its height, to read the proportions it really got: a model often ignores the ones in the prompt."""
    image = Image.open(path).convert("RGB")
    rgb = np.asarray(image, float)
    rows = np.nonzero((np.abs(rgb - np.median(rgb[:8].reshape(-1, 3), axis=0)).max(2) > 14).any(1))[0]
    top, height = int(rows.min()), int(rows.max() - rows.min() + 1)
    pen = ImageDraw.Draw(image)
    for percent in range(5, 100, 5):
        y = top + round(percent / 100 * height)
        pen.line((0, y, image.width, y), fill=(255, 255, 0))
        pen.text((4, y + 2), f"{percent / 100:.2f}", fill=(255, 255, 0))
    target = P.out / f"dev/grid_{name}.png"
    image.save(target)
    print(target, "fractions from the top of the figure, so an ahoge or horn counts")


def _cut_figure(path):
    master = Image.open(path).convert("RGB")
    rgb = np.asarray(master, float)
    mask = np.abs(rgb - np.median(rgb[:8].reshape(-1, 3), axis=0)).max(2) > 14
    ys, xs = np.nonzero(mask)
    print(path.name, "wh", xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)
    rgba = np.dstack([np.asarray(master), (mask * 255).astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA").crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def small(names, zoom=5):
    """The master at game size next to the sprite: decide on this, because big art hides what cannot read at this size."""
    source = native_world(P.standing[0])
    target = int(round((source.getbbox()[3] - source.getbbox()[1]) * P.height_ratio))
    items = [("sprite", source.crop(source.getbbox()))]
    (P.out / "dev").mkdir(parents=True, exist_ok=True)
    for name in names:
        _grid(_raw(name), name)
        figure = _cut_figure(_raw(name))
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
    (P.out / "dev").mkdir(parents=True, exist_ok=True)
    board.save(P.out / "dev/small_test.png")
    print(P.out / "dev/small_test.png")


# Pose sheets

def load(name):
    sheet = json.loads(SHEETS.read_text("utf-8"))[name]
    width, height = SIZES[sheet["size"]]
    cols, frames = sheet["cols"], sheet["frames"]
    rows = (len(frames) + cols - 1) // cols
    boxes = [native_world(i).getbbox() for i in frames]
    # The whole figure must fit: a costume wider than the sprite needs generous room.
    world_w = max(b[2] - b[0] for b in boxes) + sheet.get("pad_x", 70)
    world_h = max(b[3] - b[1] for b in boxes) + sheet.get("pad_y", 24)
    cell = (width // cols, height // rows)
    # "zoom" pins a sheet already drawn: cutting has to use the layout it was drawn with, even if the source composites have since changed.
    zoom = sheet.get("zoom") or min(cell[0] / world_w, cell[1] / world_h)
    return dict(sheet, name=name, frames=frames, rows=rows, width=width, height=height, cell=cell, zoom=zoom, boxes=boxes)


def cell_origin(layout, k):
    """World point of the cell's top-left corner, keeping the sprite's soles level across cells."""
    cols, cell = layout["cols"], layout["cell"]
    box = layout["boxes"][k]
    world_w, world_h = cell[0] / layout["zoom"], cell[1] / layout["zoom"]
    center = (box[0] + box[2]) / 2
    bottom = max(b[3] for b in layout["boxes"]) if layout.get("level", True) else box[3]
    return center - world_w / 2, bottom + 10 - world_h, (k % cols) * cell[0], (k // cols) * cell[1]


def refs(name):
    layout = load(name)
    board = Image.new("RGB", (layout["width"], layout["height"]), BACKDROP)
    for k, i in enumerate(layout["frames"]):
        ox, oy, cx, cy = cell_origin(layout, k)
        crop = native_world(i).crop((round(ox), round(oy), round(ox + layout["cell"][0] / layout["zoom"]), round(oy + layout["cell"][1] / layout["zoom"])))
        big = crop.resize(layout["cell"], Image.Resampling.NEAREST)
        board.paste(big, (cx, cy), big)
        if layout.get("mark_grips"):
            pen = ImageDraw.Draw(board)
            for hand in sprite_hands(i):
                x, y = cx + (hand[0] - ox) * layout["zoom"], cy + (hand[1] - oy) * layout["zoom"]
                radius = 3 * layout["zoom"]
                pen.ellipse((x - radius, y - radius, x + radius, y + radius), fill=GRIP_DOT)
    (P.parts / "refs").mkdir(parents=True, exist_ok=True)
    path = P.parts / f"refs/poses_{name}.png"
    board.save(path)
    print(path)
    _marked(layout, board)
    return path


def _marked(layout, board):
    """The same board with cell numbers and each weapon grip ringed, to read while writing `motion`. Never sent to the model, because it would draw the rings."""
    marked = board.copy()
    pen = ImageDraw.Draw(marked)
    for k, i in enumerate(layout["frames"]):
        ox, oy, cx, cy = cell_origin(layout, k)
        pen.text((cx + 6, cy + 4), f"cell {k + 1} = frame {i}", fill=(255, 255, 0))
        if not weapon_layers():
            continue
        for hand in sprite_hands(i):
            x, y = cx + (hand[0] - ox) * layout["zoom"], cy + (hand[1] - oy) * layout["zoom"]
            pen.ellipse((x - 14, y - 14, x + 14, y + 14), outline=(255, 60, 60), width=3)
    marked.save(P.parts / f"refs/poses_{layout['name']}_marked.png")


def draw(name, version=1):
    layout = load(name)
    if "TODO" in layout.get("motion", "TODO"):
        raise SystemExit(f"{name} has no motion yet: read its marked poses and write it before paying")
    path = refs(name)
    motion = layout["motion"] + (GRIP_NOTE if layout.get("mark_grips") else "")
    prompt = SHEET_PROMPT.format(identity=P.character["identity"], count=len(layout["frames"]), cols=layout["cols"], rows=layout["rows"], motion=motion,
                                 hands_rule=P.character.get("hands_rule", "Her hands are empty: no weapon of any kind."), style=P.sheet_style or DEFAULT_STYLE)
    tag = f"poses_{name}_v{version}"
    (P.parts / "prompts").mkdir(parents=True, exist_ok=True)
    (P.parts / "prompts" / f"{tag}.txt").write_text(prompt, "utf-8")
    return submit(tag, prompt, [P.master, path], layout["size"], resolution="2k")


def standing_height():
    heights = []
    for i in range(P.standing[0], P.standing[1] + 1):
        box = native_world(i).getbbox()
        heights.append(box[3] - box[1])
    return float(np.median(heights)) * P.height_ratio


def sway(image, phase, amount=1.7):
    """A living idle from one drawing: the skirt swings from the waist, the chest rises, the feet stay planted."""
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
    """Cut the sheet's cells into clip folders that the normal render and grounding steps use."""
    layout = load(name)
    raw = Image.open(P.parts / f"raw/poses_{name}_v{version}_0.png").convert("RGB")
    ratio = raw.width / layout["width"]
    cell_w, cell_h = raw.width // layout["cols"], raw.height // layout["rows"]
    side = max(cell_w, cell_h)
    zoom = layout["zoom"] * ratio
    window = [0, 0, int(round(side / zoom))]
    cells = []
    for k in range(len(layout["frames"])):
        x, y = (k % layout["cols"]) * cell_w, (k // layout["cols"]) * cell_h
        figure = matte(raw.crop((x, y, x + cell_w, y + cell_h)))
        solid_alpha = np.asarray(figure.getchannel("A")) > 128
        edges = {"top": solid_alpha[:3], "bottom": solid_alpha[-3:], "left": solid_alpha[:, :3], "right": solid_alpha[:, -3:]}
        touching = [edge for edge, band in edges.items() if band.sum() > 6]
        if touching:
            print(f"WARNING {name} frame {layout['frames'][k]} touches the cell's {touching} edge: she was drawn too large and may be cut off. Look at it; redraw with more pad_x or pad_y", flush=True)
        square = Image.new("RGBA", (side, side))
        square.paste(figure, (0, 0))
        cells.append(square)
    if "head_ref" in layout:
        # Nothing here stands head over feet, so the size comes from her head width against a sheet that does.
        other = load(layout["head_ref"]["sheet"])
        head_world = layout["head_ref"]["ref_head_px"] / other["zoom"] * layout["head_ref"]["ref_scale"]
        scale = head_world / (layout["head_ref"]["head_px"] / layout["zoom"])
    else:
        # A lunge or a crouch lowers her and the sprite alike, so match her height against the sprite's in the same frame.
        fits = []
        for k in layout["ref_cells"]:
            box = cells[k].getchannel("A").getbbox()
            native = native_world(layout["frames"][k]).getbbox()
            fits.append(P.height_ratio * (native[3] - native[1]) / ((box[3] - box[1]) / zoom))
        scale = float(np.median(fits))
    size = int(round(window[2] * scale))

    def placed_at(alpha, slot, cell, frame_window=window, frame_scale=scale):
        """As drawn: same place in the cell, scaled about the soles."""
        box = alpha.getbbox()
        target = figure_mask(slot)
        target_rows = np.nonzero(target.any(1))[0]
        k = int(round(frame_window[2] * frame_scale)) / side
        native = native_world(layout["frames"][cell]).getbbox()
        left0, top0 = placement(frame_window, frame_scale)
        dx = int(round((native[0] + native[2]) / 2 - (left0 + (box[0] + box[2]) / 2 * k)))
        dy = int(target_rows.max()) + 1 - int(round(top0 + box[3] * k))
        value, sx, _ = best_shift(placed_mask(alpha, frame_window, frame_scale, dx, dy), target, 14, 1)
        return [dx + sx, dy], round(value, 3)

    micros = layout.get("micro", {})

    def drawn(slot, cell):
        spec = micros.get(str(slot))
        return micro(cells[cell], spec, zoom / scale) if spec else cells[cell]

    # A repair sheet: its cells replace single frames in clips that other sheets drew.
    for text, cell in layout.get("replace", {}).items():
        slot = int(text)
        owner = next(c for c in P.clips() if c["start"] <= slot <= c["end"])
        folder = P.out / "clips" / owner["id"]
        report = json.loads((folder / "selection.json").read_text("utf-8"))
        row = next(r for r in report["frames"] if r["slot"] == slot)
        # A frame renders through its clip's window, so restate this sheet's scale against that window: the same world size comes out.
        clip_scale = scale * window[2] / report["window"][2]
        image = drawn(slot, cell)
        image.save(folder / f"hd/{slot:04d}.png")
        offset, value = placed_at(image.getchannel("A"), slot, cell, report["window"], clip_scale)
        row.update(video_frame=f"{name}:{cell}", scale=round(float(clip_scale), 3), offset=offset, score=value)
        row.pop("offset_before_ground", None)
        (folder / "selection.json").write_text(json.dumps(report, indent=1), "utf-8")
        print("replaced", slot, "in", owner["id"], "score", value)
    held = None
    for clip, slots in layout.get("clips", {}).items():
        folder = P.out / "clips" / clip
        if folder.exists():
            shutil.rmtree(folder)
        (folder / "hd").mkdir(parents=True)
        rows = []
        for entry in slots:
            slot, cell = entry["slot"], entry["cell"]
            image = drawn(slot, cell)
            if "phase" in entry:
                image = sway(image, entry["phase"] * np.pi)
            image.save(folder / f"hd/{slot:04d}.png")
            offset, value = placed_at(image.getchannel("A"), slot, cell)
            rows.append(dict(slot=slot, video_frame=f"{name}:{cell}", scale=round(float(scale), 3), offset=offset, track=[0, 0], score=value))
        if "phase" in slots[0] or len({s["cell"] for s in slots}) == 1:
            # One drawing: the only motion should be the sway itself.
            for row in rows:
                row["offset"] = list(rows[0]["offset"])
        if layout.get("hold"):
            # "hold": every cell of this sheet is the same drawing with only a hand or the head changed, so all its clips share one place.
            held = held or list(rows[0]["offset"])
            for row in rows:
                row["offset"] = list(held)
        (folder / "selection.json").write_text(json.dumps(dict(clip=clip, sheet=f"{name}_v{version}", window=window, base_scale=scale, frames=rows), indent=1), "utf-8")
        print(clip, "scale", round(scale, 3), [(r["slot"], r["offset"], r["score"]) for r in rows])


def micro(image, spec, per_world):
    """Small motion measured on the source, on one drawing, instead of a sway that bends all of her. Whatever the spec leaves alone stays pixel for pixel, as the source's planted feet do.

    spec: {"shear": [[t, dx], ...], "lift": [[t, dy], ...], "moves": [{"poly": [[x, y], ...], "dx": 1, "dy": 0, "feather": 8}]}.
    t is a fraction of her height, poly is in the drawing's pixels, dx and dy are game pixels.
    """
    rgba = np.asarray(image, np.float32)
    h, w = rgba.shape[:2]
    box = image.getchannel("A").getbbox()
    rows = (np.arange(h, dtype=np.float32) - box[1]) / (box[3] - box[1])
    field_x, field_y = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
    for key, field in (("shear", field_x), ("lift", field_y)):
        if key in spec:
            points = np.array(spec[key], np.float32)
            field += np.interp(rows, points[:, 0], points[:, 1]).astype(np.float32)[:, None]
    for move in spec.get("moves", []):
        mask = Image.new("L", (w, h))
        ImageDraw.Draw(mask).polygon([tuple(p) for p in move["poly"]], fill=255)
        weight = ndimage.gaussian_filter(np.asarray(mask, np.float32) / 255, move.get("feather", 8) / 2)
        field_x += weight * move.get("dx", 0)
        field_y += weight * move.get("dy", 0)
    field_x, field_y = field_x * per_world, field_y * per_world
    moved = (np.abs(field_x) > 0.01) | (np.abs(field_y) > 0.01)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    premultiplied = rgba.copy()
    premultiplied[..., :3] *= rgba[..., 3:] / 255
    out = np.stack([ndimage.map_coordinates(premultiplied[..., c], [ys - field_y, xs - field_x], order=1) for c in range(4)], 2)
    out[..., :3] /= np.maximum(out[..., 3:] / 255, 1e-3)
    return Image.fromarray(np.clip(np.where(moved[..., None], out, rgba), 0, 255).astype(np.uint8), "RGBA")


def _latest(name):
    """The newest drawing of a sheet: 0 when it has none yet."""
    versions = [int(p.stem.split("_v")[-1].split("_")[0]) for p in (P.parts / "raw").glob(f"poses_{name}_v*_0.png")]
    return max(versions, default=0)


def draw_all(budget):
    """Every sheet not drawn yet, one at a time. Stops before an image would pass the budget, which counts everything in this patch's journal. Safe to run again."""
    data = json.loads(SHEETS.read_text("utf-8"))
    for name, sheet in data.items():
        if _latest(name):
            continue
        if budget is not None and spent() + COST[sheet["size"]] > budget:
            print("budget reached at estimated $", round(spent(), 2), "next was", name)
            break
        if draw(name):
            print("failed", name, "stopping")
            break
    cost()


def cut_all():
    """Cut each sheet's newest drawing: clip sheets first, because repair sheets write into their clips. Then the recorded per-clip sizes."""
    data = json.loads(SHEETS.read_text("utf-8"))
    for name in sorted(data, key=lambda n: "replace" in data[n]):
        version = _latest(name)
        if version:
            cut(name, version)
        else:
            print("not drawn yet", name)
    resize()


def resize():
    """design/<id>/clip_scales.json, {"clip_100_102": 1.02}: a target height against the sprite, for clips the model drew at their own size. One sheet has one scale, so a clip can pop against its neighbors. Upright frames only.

    design/<id>/frame_scales.json, {"155": 1.06}: one frame times this, for a cell the model drew smaller or larger than the rest of its sheet
    (measure by figure area against its neighbours). Safe to run again: the factor already applied is divided out first.
    """
    path, frame_path = P.run / "clip_scales.json", P.run / "frame_scales.json"
    goals = json.loads(path.read_text("utf-8")) if path.exists() else {}
    per_frame = json.loads(frame_path.read_text("utf-8")) if frame_path.exists() else {}
    owners = {c["id"] for c in P.clips() if any(c["start"] <= int(f) <= c["end"] for f in per_frame)}
    for ident in [c["id"] for c in P.clips() if c["id"] in goals or c["id"] in owners]:
        folder = P.out / "clips" / ident
        report = json.loads((folder / "selection.json").read_text("utf-8"))
        window = report["window"]
        for row in report["frames"]:
            row["scale"] = row["scale"] / row.pop("frame_scale", 1)
        factor = 1.0
        if ident in goals:
            ratios = []
            for row in report["frames"]:
                image = Image.open(folder / f"hd/{row['slot']:04d}.png")
                box = image.getchannel("A").getbbox()
                native = native_world(row["slot"]).getbbox()
                ratios.append((box[3] - box[1]) * window[2] * row["scale"] / image.width / (native[3] - native[1]))
            factor = goals[ident] / float(np.median(ratios))
        for row in report["frames"]:
            # By ratio, not one value: a frame replaced from a repair sheet can have its own.
            own = per_frame.get(str(row["slot"]), 1)
            scale = row["scale"] * factor * own
            image = Image.open(folder / f"hd/{row['slot']:04d}.png")
            alpha = image.getchannel("A")
            box = alpha.getbbox()
            size = int(round(window[2] * scale))
            k = size / image.width
            native = native_world(row["slot"]).getbbox()
            target = figure_mask(row["slot"])
            rows = np.nonzero(target.any(1))[0]
            left0, top0 = placement(window, scale)
            dx = int(round((native[0] + native[2]) / 2 - (left0 + (box[0] + box[2]) / 2 * k)))
            dy = int(rows.max()) + 1 - int(round(top0 + box[3] * k))
            _, sx, _ = best_shift(placed_mask(alpha, window, scale, dx, dy), target, 14, 1)
            row["scale"] = round(scale, 4)
            if own != 1:
                row["frame_scale"] = own
            row["offset"] = [dx + sx, dy]
            row.pop("offset_before_ground", None)
        # One drawing with micro motion: the only movement should be the sway, as in cut.
        if len({r["video_frame"] for r in report["frames"]}) == 1:
            for row in report["frames"]:
                row["offset"] = list(report["frames"][0]["offset"])
        (folder / "selection.json").write_text(json.dumps(report, indent=1), "utf-8")
        print(ident, "scale times", round(factor, 3), {s: v for s, v in per_frame.items() if any(r["slot"] == int(s) for r in report["frames"])})
