"""Track the native head per frame: translation and rotation against the IMG 10 head.

Run with the ComfyUI venv python (needs cv2). Writes design/fatfish/doll_v03/head_track.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from fatfish_doll import ROOT, layer_world

OUT = ROOT / "design/fatfish/doll_v03"
HEAD_LAYERS = ("mg_hair0000a", "mg_face0000b", "mg_cap0000c")
PREVIEW_LAYERS = ("mg_body0000", "mg_hair0000a", "mg_face0000b", "mg_cap0000c")


def head_stack(index, layers=HEAD_LAYERS):
    world = Image.new("RGBA", (500, 500))
    for layer in layers:
        world.alpha_composite(layer_world(layer, index))
    return np.array(world)


def template():
    world = head_stack(10)
    hair = np.array(layer_world("mg_hair0000a", 10))[..., 3] > 0
    face = np.array(layer_world("mg_face0000b", 10))[..., 3] > 0
    ys, xs = np.nonzero(hair | face)
    box = (xs.min() - 2, ys.min() - 8, xs.max() + 4, ys.max() + 6)
    return world[box[1]:box[3], box[0]:box[2]], box


def rotated(tmpl, angle, flip):
    src = tmpl[:, ::-1] if flip else tmpl
    h, w = src.shape[:2]
    size = int(np.hypot(h, w)) + 4
    M = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1)
    M[0, 2] += size / 2 - w / 2
    M[1, 2] += size / 2 - h / 2
    return cv2.warpAffine(src, M, (size, size), flags=cv2.INTER_NEAREST, borderValue=(0, 0, 0, 0))


def centroid(index, layer):
    alpha = np.array(layer_world(layer, index))[..., 3] > 0
    if not alpha.any():
        return None
    ys, xs = np.nonzero(alpha)
    return float(xs.mean()), float(ys.mean())


def score_frame(world, tmpl):
    target = world[..., :3].astype(np.float32)
    target[world[..., 3] == 0] = 0
    best = None
    for flip in (False, True):
        for angle in range(-180, 180, 3):
            t = rotated(tmpl, angle, flip)
            mask = t[..., 3] > 0
            rgb = t[..., :3].astype(np.float32)
            rgb[~mask] = 0
            res = cv2.matchTemplate(target, rgb, cv2.TM_SQDIFF, mask=np.dstack([mask.astype(np.float32)] * 3))
            res = np.nan_to_num(res, nan=1e12, posinf=1e12, neginf=1e12)
            value, _, loc, _ = cv2.minMaxLoc(res)
            value = value / max(1, mask.sum() * 3) / 65025
            if best is None or value < best[0]:
                best = (float(value), angle, flip, int(loc[0] + t.shape[1] / 2), int(loc[1] + t.shape[0] / 2))
    return best


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    world = head_stack(10)
    ys, xs = np.nonzero(world[..., 3] > 0)
    box = (xs.min() - 1, ys.min() - 1, xs.max() + 2, ys.max() + 2)
    tmpl = world[box[1]:box[3], box[0]:box[2]]
    cap0, face0 = centroid(10, "mg_cap0000c"), centroid(10, "mg_face0000b")
    axis0 = np.degrees(np.arctan2(face0[0] - cap0[0], face0[1] - cap0[1]))
    rows = []
    for index in range(174):
        value, angle, flip, cx, cy = score_frame(head_stack(index), tmpl)
        cap, face = centroid(index, "mg_cap0000c"), centroid(index, "mg_face0000b")
        axis = None
        if cap and face:
            axis = round(float(((axis0 - np.degrees(np.arctan2(face[0] - cap[0], face[1] - cap[1]))) + 180) % 360 - 180), 1)
        rows.append(dict(index=index, error=round(value, 4), angle=angle, flip=flip, x=cx, y=cy, axis_angle=axis,
                         face=[round(v, 1) for v in face] if face else None, cap=[round(v, 1) for v in cap] if cap else None))
        print(index, round(value, 3), angle, flip, cx, cy, axis, flush=True)
    (OUT / "head_track.json").write_text(json.dumps(dict(template_box=[int(v) for v in box], frames=rows), indent=1), "utf-8")
    Z = 3
    sheet = Image.new("RGB", (15 * 44 * Z, 12 * 44 * Z), (70, 80, 95))
    draw = ImageDraw.Draw(sheet)
    for row in rows:
        full = Image.fromarray(head_stack(row["index"], PREVIEW_LAYERS))
        crop = full.crop((row["x"] - 22, row["y"] - 22, row["x"] + 22, row["y"] + 22)).resize((44 * Z, 44 * Z), Image.NEAREST)
        px, py = (row["index"] % 15) * 44 * Z, (row["index"] // 15) * 44 * Z
        sheet.paste(crop, (px, py), crop)
        draw.text((px + 2, py + 1), f"{row['index']} {row['angle']}{'F' if row['flip'] else ''} a{row['axis_angle']} {row['error']:.2f}", fill="yellow")
    sheet.save(ROOT / "output/Fatfish_Doll_v03/dev/head_track.png")


if __name__ == "__main__":
    main()
