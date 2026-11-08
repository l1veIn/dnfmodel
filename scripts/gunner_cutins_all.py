"""The other female gunner cut-ins: redrawn key frames, official motion carried over. One entry per cut-in in CUTS.

    python scripts/gunner_cutins_all.py draw [name ...]
    python scripts/gunner_cutins_all.py render [name ...]

Segment kinds: draw (from a key frame), official (keep the frames, only effects in them), orange (keep them, recolored).
`mask` uses the official alpha, for banners that open and close around a finished picture.
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
BASE = ROOT / "output/gunner_cutin"
MODEL = "gpt-image-2.6-sunburst-native"
MASTER = ROOT / "output/claude_gunner_v02/parts/raw/claude_a_0.png"
IDENTITY = json.loads((ROOT / "design/claude_gunner/patch.json").read_text("utf-8"))["character"]["identity"]
STOPS = np.array([[0, 0, 0], [92, 28, 10], [222, 98, 44], [248, 158, 84], [255, 236, 208]], np.float32)
POS = np.array([0, 0.2, 0.52, 0.8, 1.0], np.float32)

CUTS = {
    "stormtrooper": dict(stem="atgunner_stormtrooper", note="A wide cinematic strip: she is small at the right with a huge gun rig, and the left shows smoke and a huge flying shell casing. Keep the smoke as pale warm gray and the shell casing as polished gold. Fill the whole strip as Image 2 does.",
                         segments=[dict(kind="official", start=0, end=2), dict(key=5, start=3, end=7, mask=True, left=0.56, feather=170, note="In this frame only the huge rotary gun barrels are in view at the right, firing; she is not in view yet. The barrels are near-black with thin gold rings and cream ceramic housings."), dict(key=11, start=8, end=23, mask=True, left=0.47)]),
    "spitfire_neo": dict(stem="atgunner_spitfire_neo", note="She is flying fast and diving through the air with small fictional thruster boots and sharp cream and near-black fin blades on her back. Her long orange hair streams behind her along the same line as the sprite's long braid. Her dress flows but keeps covering her legs, modest and elegant.",
                         segments=[dict(key=3, start=0, end=3), dict(key=4, start=4, end=7), dict(key=9, start=8, end=11), dict(key=13, start=12, end=15), dict(key=17, start=16, end=19), dict(key=22, start=20, end=23), dict(key=26, start=24, end=27), dict(key=32, start=28, end=39)]),
    "freyja": dict(stem="atgunner_freyja", note="A diagonal cinematic banner with gold bars at its edges. Inside the banner is a dramatic close-up of her face with her orange hair, against warm fire. Keep the banner shape and its gold bars. Fill the whole banner.",
                   segments=[dict(kind="official", start=0, end=1), dict(key=6, start=2, end=8, mask=True), dict(key=11, start=9, end=19, mask=True)]),
    "mechanic_neo": dict(stem="atgunner_mechanic_neo", note="A calm portrait of her from the chest up, facing us with one hand raised near her mouth in thought. Her long orange hair falls on both sides, and the high ruffled collar and orange flower brooch are clearly visible.",
                         segments=[dict(key=3, start=0, end=7), dict(key=15, start=8, end=22)]),
    "optimus": dict(stem="atgunner_optimus", note="A diagonal cinematic banner with a mechanical frame at its edges. Inside it is a dramatic close-up of her face with flowing orange hair. Make the frame cream ceramic and near-black. Fill the whole banner.",
                    segments=[dict(kind="official", start=0, end=0), dict(key=9, start=1, end=18, mask=True)]),
    "ranger_neo": dict(stem="atgunner_ranger_neo", note="She moves fast and low, seen close up, with her long orange hair falling across her face. Her dress and capelet stay on, in dark shadow with gold trim.",
                       segments=[dict(key=3, start=0, end=6), dict(key=10, start=7, end=13), dict(key=17, start=14, end=20), dict(key=21, start=21, end=21), dict(key=23, start=22, end=24, note="In this frame she has almost passed: only the hem of her dress, her white boots and flying gold-trimmed ribbons sweep through the picture. No face.")]),
    "crimsonrose": dict(stem="atgunner_crimsonrose", note="A wide cinematic strip: she is small at the right, with broken glass and sparks across the strip. Keep the debris as warm gray and gold. Fill the whole strip as Image 2 does.",
                        segments=[dict(kind="official", start=0, end=3), dict(key=12, start=4, end=23, mask=True, left=0.55, flow_from=8)]),
    "paramedic_neo": dict(stem="atgunner_paramedic_neo", note="An extreme close-up of her face and shoulders, with long orange hair spreading wide on both sides. Her whole face is visible, with no mask. Any glow is clay orange and any smoke is pale warm gray.",
                          segments=[dict(key=2, start=0, end=3), dict(key=9, start=4, end=11), dict(key=14, start=12, end=16), dict(key=18, start=17, end=19)]),
    "paramedic": dict(stem="atgunner_paramedic", note="She sits gracefully in her long dress with a large angular cream and clay orange shape behind her.",
                      segments=[dict(key=0, start=0, end=0)]),
    "coronis": dict(stem="atgunner_coronis", note="She stands in the center in her dress with several small hovering cream ceramic drones around her, firing thin clay orange beams. Where the sprite has blue light, draw clay orange light.",
                    segments=[dict(kind="orange", start=0, end=5), dict(key=18, start=6, end=32), dict(kind="orange", start=33, end=39)]),
}
PROMPT = """Image 1 is the character authority: {identity} Keep her face, her very long straight orange hair, her orange flower hair ornament with the black ribbon, and her dress with its colors. Do not give her the sprite's clothes, hairstyle, goggles, face mask or skin exposure.

Image 2 is one frame from a dramatic cut-in of a 2D fantasy action game, on flat magenta. It decides the camera, framing and scale, where her head and limbs are, and the shape of the picture, and nothing about color or costume. Redraw the frame with the same composition so it could be laid over Image 2. The camera position, zoom and crop must match exactly: a close-up stays that close-up, and parts cut off by the edge stay cut off.

{note}

Any machine is premium future hardware from a calm, thoughtful AI lab: smooth glazed ceramic plates in warm cream white, matte near-black machinery, thin gold trim and glowing clay orange seams, RGB 217 119 87 to 232 112 48. No blue, no green, no purple, no rust, no grime.

Polished anime key-visual rendering: clean cel shading with soft gradients and even dark outlines. No text, no logo. Background: completely flat uniform magenta, RGB 255 0 255, wherever Image 2 shows magenta, with no glow or shadow spilling onto it.
"""


def official(stem):
    img, _ = load_img(PACK, stem)
    real = [f for f in img.frames if "link" not in f]
    canvas = next(((f.get("cw"), f.get("ch")) for f in real if f.get("cw")), None) or next((f.get("canvas_width"), f.get("canvas_height")) for f in real)
    pages = []
    for frame in img.frames:
        page = Image.new("RGBA", canvas)
        source = img.resolve(frame["index"]) if "link" in frame else frame
        picture = img.image(frame["index"]) if source["w"] * source["h"] > 1 else None
        if picture is not None:
            page.paste(picture.convert("RGBA"), (source["x"], source["y"]))
        pages.append(page)
    return pages, canvas


def window(pages):
    """Union of everything drawn, with a margin; the model gets the most pixels this way."""
    boxes = [p.getbbox() for p in pages if p.getbbox()]
    x0, y0, x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)
    pad = max(8, int(max(x1 - x0, y1 - y0) * 0.02))
    return max(0, x0 - pad), max(0, y0 - pad), min(pages[0].width, x1 + pad), min(pages[0].height, y1 + pad)


def layout(pages):
    box = window(pages)
    w, h = box[2] - box[0], box[3] - box[1]
    size, board = ("16:9", (2048, 1152)) if w / h > 1.6 else ("3:2", (2048, 1365)) if w / h > 1.15 else ("1:1", (2048, 2048))
    zoom = min(board[0] / w, board[1] / h)
    return dict(box=box, size=size, board=board, zoom=zoom, ox=(board[0] - w * zoom) / 2, oy=(board[1] - h * zoom) / 2)


def draw_key(name, index):
    spec = CUTS[name]
    work = BASE / name
    note = spec["note"] + " " + next((s.get("note", "") for s in spec["segments"] if s.get("key") == index), "")
    (work / "raw").mkdir(parents=True, exist_ok=True)
    (work / "refs").mkdir(exist_ok=True)
    tag = f"key{index:02d}_v1"
    if (work / "raw" / f"{tag}_0.png").exists():
        return name, tag, "exists"
    pages, _ = official(spec["stem"])
    plan = layout(pages)
    box = plan["box"]
    crop = pages[index].crop(box)
    big = crop.resize((int(crop.width * plan["zoom"]), int(crop.height * plan["zoom"])), Image.LANCZOS)
    board = Image.new("RGB", plan["board"], (255, 0, 255))
    board.paste(big, (int(plan["ox"]), int(plan["oy"])), big)
    ref = work / "refs" / f"key{index:02d}.png"
    board.save(ref)
    command = [sys.executable, str(CLI), "image", "--model", MODEL, "--prompt", PROMPT.format(identity=IDENTITY, note=note), "--n", "1", "--size", plan["size"], "--resolution", "2k", "--background", "opaque", "--quality", "high", "--out", str(work / "raw"), "--name", tag, "--timeout", "900", "--image", str(MASTER), "--image", str(ref)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    return name, tag, result.returncode, result.stderr[-160:] if result.returncode else ""


def key_page(name, index, pages):
    """The drawn key back in canvas coordinates."""
    plan = layout(pages)
    box = plan["box"]
    art = cut_key(BASE / name / "raw" / f"key{index:02d}_v1_0.png")
    ratio = art.width / plan["board"][0]
    w, h = box[2] - box[0], box[3] - box[1]
    area = tuple(int(v * ratio) for v in (plan["ox"], plan["oy"], plan["ox"] + w * plan["zoom"], plan["oy"] + h * plan["zoom"]))
    picture = art.crop(area).resize((w, h), Image.LANCZOS)
    page = Image.new("RGBA", pages[0].size)
    page.paste(picture, (box[0], box[1]))
    return page


def figure_box(page):
    a = np.asarray(page, np.float32)
    mask = ndimage.binary_opening(a[..., 3] > 128, iterations=2)
    labels, count = ndimage.label(ndimage.binary_dilation(mask, iterations=4))
    if not count:
        return page.getbbox()
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    mask &= labels == (int(np.argmax(sizes)) + 1)
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return page.getbbox()
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def premultiplied(page):
    source = np.asarray(page, np.float32).copy()
    source[..., :3] *= source[..., 3:4] / 255
    return source


def straight(out):
    alpha = np.maximum(out[..., 3:4], 1e-3)
    out[..., :3] = np.clip(out[..., :3] * 255 / alpha, 0, 255)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def box_warp(page, source_box, target_box):
    sx, sy = (target_box[2] - target_box[0]) / max(1, source_box[2] - source_box[0]), (target_box[3] - target_box[1]) / max(1, source_box[3] - source_box[1])
    w, h = page.size
    source_edges = (source_box[0] <= 2, source_box[1] <= 2, source_box[2] >= w - 2, source_box[3] >= h - 2)
    target_edges = (target_box[0] <= 2, target_box[1] <= 2, target_box[2] >= w - 2, target_box[3] >= h - 2)
    # A figure cut off by the screen must stay cut off there, or the cut shows as a straight edge in mid-air.
    scale = max(sx, sy) if any(source_edges) else (sx * sy) ** 0.5
    cx0, cy0 = (source_box[0] + source_box[2]) / 2, (source_box[1] + source_box[3]) / 2
    cx1, cy1 = (target_box[0] + target_box[2]) / 2, (target_box[1] + target_box[3]) / 2
    tx, ty = cx1 - cx0 * scale, cy1 - cy0 * scale
    if source_edges[0] and target_edges[0]:
        tx = target_box[0] - source_box[0] * scale
    elif source_edges[2] and target_edges[2]:
        tx = target_box[2] - source_box[2] * scale
    if source_edges[1] and target_edges[1]:
        ty = target_box[1] - source_box[1] * scale
    elif source_edges[3] and target_edges[3]:
        ty = target_box[3] - source_box[3] * scale
    matrix = np.float32([[scale, 0, tx], [0, scale, ty]])
    return straight(cv2.warpAffine(premultiplied(page), matrix, page.size, flags=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0))


def flow_warp(page, from_page, to_page):
    def gray(item):
        a = np.asarray(item, np.float32)
        alpha = a[..., 3:4] / 255
        return np.clip((a[..., :3] * alpha + 40 * (1 - alpha)).mean(2), 0, 255).astype(np.uint8)

    w, h = page.size
    size = (max(16, w // 2), max(16, h // 2))
    flow = cv2.calcOpticalFlowFarneback(cv2.resize(gray(to_page), size), cv2.resize(gray(from_page), size), None, 0.5, 5, 41, 5, 7, 1.5, 0)
    flow = cv2.resize(cv2.GaussianBlur(flow, (0, 0), 6), (w, h)) * 2
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    return straight(cv2.remap(premultiplied(page), xs + flow[..., 0], ys + flow[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0))


def to_orange(page):
    a = np.asarray(page.convert("RGBA"), np.float32)
    rgb = a[..., :3] / 255
    level = 0.65 * (0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2]) + 0.35 * rgb.max(2)
    out = np.stack([np.interp(level, POS, STOPS[:, c]) for c in range(3)], 2)
    return Image.fromarray(np.dstack([out, a[..., 3]]).astype(np.uint8), "RGBA")


def with_official_alpha(page, target, left=None, feather=48):
    """Banner wipes: colors from the new picture, shape from the official frame. Empty spots take the nearest new color. Left of `left`, smoke, debris and shells stay official."""
    color = np.asarray(page, np.float32)
    official_pixels = np.asarray(target, np.float32)
    alpha = color[..., 3:4] / 255
    solid = alpha[..., 0] > 0.5
    out_alpha = official_pixels[..., 3].copy()
    if solid.any():
        ys, xs = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        rgb = color[..., :3] * alpha + color[ys, xs, :3] * (1 - alpha)
    else:
        rgb = official_pixels[..., :3].copy()
    if left is not None:
        w = target.width
        ramp = np.clip((np.arange(w, dtype=np.float32) - left * w) / feather, 0, 1)[None, :, None]
        rgb = official_pixels[..., :3] * (1 - ramp) + rgb * ramp
        box = target.getbbox()
        if box:
            # Right of the seam the figure is new and may be wider than the official one, inside the strip that this frame shows.
            inside = np.zeros(out_alpha.shape, np.float32)
            inside[box[1]:box[3], box[0]:box[2]] = 1
            out_alpha = np.maximum(out_alpha, color[..., 3] * inside * ramp[..., 0])
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), out_alpha]).astype(np.uint8), "RGBA")


def render(name):
    spec = CUTS[name]
    pages, _ = official(spec["stem"])
    work = BASE / name
    (work / "frames").mkdir(parents=True, exist_ok=True)
    frames = {}
    for segment in spec["segments"]:
        kind = segment.get("kind", "draw")
        start, end = segment["start"], segment["end"]
        if kind == "official":
            for i in range(start, end + 1):
                frames[i] = pages[i]
            continue
        if kind == "orange":
            for i in range(start, end + 1):
                frames[i] = to_orange(pages[i])
            continue
        key = segment["key"]
        art = key_page(name, key, pages)
        boxes = {i: figure_box(pages[i]) for i in range(start, end + 1)}
        reference = boxes[key]

        def far(box):
            if not box or not reference:
                return False
            return abs((box[2] - box[0]) / max(1, reference[2] - reference[0]) - 1) > 0.12 or abs((box[3] - box[1]) / max(1, reference[3] - reference[1]) - 1) > 0.12

        use_box = not segment.get("mask") and any(far(b) for b in boxes.values())
        if use_box:
            art_box = figure_box(art) or reference
            for i in range(start, end + 1):
                frames[i] = box_warp(art, art_box, boxes[i]) if boxes[i] else Image.new("RGBA", art.size)
        else:
            frames[key] = art
            for direction, stop in ((1, end), (-1, start)):
                current = art
                for i in range(key + direction, stop + direction, direction):
                    # Flashes confuse the flow, so the frames before `flow_from` hold still.
                    if i < segment.get("flow_from", 0):
                        frames[i] = frames[segment["flow_from"]]
                        continue
                    current = flow_warp(current, pages[i - direction], pages[i])
                    frames[i] = current
        if segment.get("mask"):
            for i in range(start, end + 1):
                frames[i] = with_official_alpha(frames[i], pages[i], segment.get("left"), segment.get("feather", 48))
    for i, page in frames.items():
        page.save(work / "frames" / f"{i:02d}.png")
    cols = 10
    canvas = pages[0].size
    cell = (160, max(40, int(160 * canvas[1] / canvas[0])))
    rows = (len(pages) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1] * 2), (58, 66, 84))
    for i, page in enumerate(pages):
        x, y = (i % cols) * cell[0], (i // cols) * cell[1] * 2
        for r, item in enumerate((page, frames.get(i))):
            if item is not None:
                small = item.resize(cell, Image.LANCZOS)
                sheet.paste(small, (x, y + r * cell[1]), small)
    sheet.save(work / "compare.jpg", quality=86)
    print(name, len(frames), "of", len(pages), work / "compare.jpg", flush=True)


def main():
    command, names = sys.argv[1], sys.argv[2:] or list(CUTS)
    if command == "draw":
        jobs = [(name, s["key"]) for name in names for s in CUTS[name]["segments"] if s.get("kind", "draw") == "draw"]
        print("keys", len(jobs), flush=True)
        with ThreadPoolExecutor(4) as pool:
            for result in pool.map(lambda j: draw_key(*j), jobs):
                print(result, flush=True)
    elif command == "render":
        for name in names:
            render(name)


if __name__ == "__main__":
    main()
