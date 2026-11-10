"""Validated, non-destructive fitting-room colour recipes and world-space pixel edits."""
from __future__ import annotations

import copy
import json
import math
import re
from functools import lru_cache

import numpy as np
from PIL import Image

SLOTS = {"skin", "hair", "cap", "face", "neck", "coat", "belt", "pants", "shoes", "weapon"}
HEX = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z")
MAX_PIXELS = 2000


def number(value, low, high, name, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"bad {name}")
    if integer and int(value) != value:
        raise ValueError(f"bad {name}")
    return int(value) if integer else value


def color(value, alpha=False):
    if not isinstance(value, str) or not HEX.fullmatch(value) or (not alpha and len(value) != 7):
        raise ValueError("bad colour")
    return value.lower() + ("ff" if alpha and len(value) == 7 else "")


def recipe(value=None, frames=None):
    if value is None:
        return {"dyes": {}, "pixels": []}
    if not isinstance(value, dict) or set(value) - {"dyes", "pixels"}:
        raise ValueError("bad customization")
    dyes, pixels = value.get("dyes", {}), value.get("pixels", [])
    if not isinstance(dyes, dict) or set(dyes) - SLOTS or not isinstance(pixels, list) or len(pixels) > MAX_PIXELS:
        raise ValueError("bad customization")
    out = {"dyes": {}, "pixels": []}
    for slot, rule in dyes.items():
        if not isinstance(rule, dict) or set(rule) - {"hue", "saturation", "lightness", "colors"}:
            raise ValueError("bad dye")
        r = dict(hue=number(rule.get("hue", 0), -180, 180, "hue"),
                 saturation=number(rule.get("saturation", 1), 0, 2, "saturation"),
                 lightness=number(rule.get("lightness", 0), -100, 100, "lightness"), colors=[])
        replacements = rule.get("colors", [])
        if not isinstance(replacements, list) or len(replacements) > 256:
            raise ValueError("too many colours")
        for c in replacements:
            if not isinstance(c, dict) or set(c) - {"from", "to", "tolerance"}:
                raise ValueError("bad colour replacement")
            r["colors"].append({"from": color(c.get("from")), "to": color(c.get("to")),
                                "tolerance": number(c.get("tolerance", 0), 0, 255, "tolerance")})
        if r["hue"] or r["saturation"] != 1 or r["lightness"] or r["colors"]:
            out["dyes"][slot] = r
    # Last brush operation wins for a frame/pixel, keeping repeated strokes compact.
    points = {}
    for p in pixels:
        if not isinstance(p, dict) or set(p) != {"frame", "x", "y", "color"}:
            raise ValueError("bad pixel")
        f = number(p["frame"], 0, (frames - 1) if frames else 9999, "frame", True)
        x, y = (number(p[a], -4096, 4096, a, True) for a in ("x", "y"))
        points[f, x, y] = dict(frame=f, x=x, y=y, color=color(p["color"], True))
    out["pixels"] = list(points.values())
    return out


def key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def rgba(value):
    return tuple(bytes.fromhex(value[1:]))


def dye(image, rule):
    """Transform RGB only. Replacement tests use the source colours, so rules never cascade."""
    if not rule:
        return image
    data = np.array(image.convert("RGBA"))
    src = data[..., :3].copy()
    rgb = src.astype(np.float32) / 255
    if rule.get("hue", 0) or rule.get("saturation", 1) != 1:
        hsv = np.asarray(Image.fromarray(src).convert("HSV")).copy()
        hsv[..., 0] = (hsv[..., 0].astype(float) + rule.get("hue", 0) * 256 / 360) % 256
        hsv[..., 1] = np.clip(hsv[..., 1].astype(float) * rule.get("saturation", 1), 0, 255)
        rgb = np.asarray(Image.fromarray(hsv, "HSV").convert("RGB")).astype(np.float32) / 255
    light = rule.get("lightness", 0) / 100
    rgb = rgb + (1 - rgb) * light if light > 0 else rgb * (1 + light)
    data[..., :3] = np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    for c in rule.get("colors", []):
        source = np.array(rgba(c["from"]), dtype=np.int16)
        mask = np.max(np.abs(src.astype(np.int16) - source), axis=-1) <= c["tolerance"]
        data[..., :3][mask] = rgba(c["to"])
    return Image.fromarray(data, "RGBA")


@lru_cache(maxsize=128)
def _indexed_reader(npk, path, stamp, palette, rule_text):
    # A shallow reader copy shares immutable compressed pixels, but owns its palette.
    import render
    img = copy.copy(render.load_img(npk, path))
    img.palettes = list(img.palettes)
    table = img.palettes[palette]
    image = Image.new("RGBA", (len(table), 1))
    image.putdata([tuple(c) for c in table])
    img.palettes[palette] = np.asarray(dye(image, json.loads(rule_text))).reshape(-1, 4).tolist()
    return img


def layer_frame(layer, k, box, rules):
    import render
    rule = rules.get(layer["slot"])
    if not rule:
        return render.frame(layer["source"], layer["path"], k, box, layer["palette"])
    img = render.load_img(layer["source"], layer["path"])
    palette = layer["palette"] if layer["palette"] < len(getattr(img, "palettes", [])) else 0
    if (k < len(img.frames) and getattr(img, "palettes", []) and img.resolve(k).get("color") == 14
            and img.resolve(k).get("compression") == 6):
        altered = _indexed_reader(layer["source"], layer["path"], render.token(layer["source"]), palette, key(rule))
        canvas = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]))
        with render.lock:
            f, pic = altered.resolve(k), altered.image(k, palette)
        canvas.alpha_composite(pic, (f.get("x", 0) - box[0], f.get("y", 0) - box[1]))
        return canvas
    return dye(render.frame(layer["source"], layer["path"], k, box, layer["palette"]), rule)


def pixels(image, frame, box, points):
    for p in points:
        if p["frame"] == frame:
            x, y = p["x"] - box[0], p["y"] - box[1]
            if 0 <= x < image.width and 0 <= y < image.height:
                image.putpixel((x, y), rgba(p["color"]))
    return image


def expanded_box(box, points, frames):
    if points:
        box = (min(box[0], min(p["x"] for p in points)), min(box[1], min(p["y"] for p in points)),
               max(box[2], max(p["x"] for p in points) + 1), max(box[3], max(p["y"] for p in points) + 1))
    w, h = box[2] - box[0], box[3] - box[1]
    if w > 2048 or h > 2048 or w * h * frames > 40_000_000:
        raise ValueError("preview is too large; keep pixel edits close to the character")
    return box
