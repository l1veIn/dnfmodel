"""Frame rendering shared by the review workers and the game browser: one IMG of one NPK, placed on a fixed box, and whole-unit atlases.

A unit's frames are sent as one atlas (a grid of equal cells, lossless WebP) instead of one PNG per frame, and atlases are cached
on disk under kb/cache keyed by the source files' sizes and times, so a second look costs nothing.
"""
from __future__ import annotations

import hashlib
import io
import math
import sqlite3
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
KB = ROOT / "kb" / "kb.sqlite"
CACHE = ROOT / "kb" / "cache"
PAD = 6
MAX_SIDE = 16000          # WebP limit is 16383 px per side
SCREEN_CELL = 640         # full-screen cut-ins are cached at this width; the page asks for a full frame when paused
lock = threading.Lock()
BROKEN = {}  # img path -> first decode error, for the pages to show


@lru_cache(maxsize=None)
def npk_entries(path_text):
    from dnf_resources import read_npk
    return {e["path"]: e for e in read_npk(Path(path_text))}


@lru_cache(maxsize=128)
def load_img(path_text, img_path):
    from survey_gunner_effects import reader
    entry = npk_entries(path_text)[img_path]
    with open(path_text, "rb") as stream:
        stream.seek(entry["offset"])
        return reader(stream.read(entry["length"]), entry["version"])


def reset():
    npk_entries.cache_clear()
    load_img.cache_clear()
    official_npk.cache_clear()


@lru_cache(maxsize=4096)
def official_npk(img_path):
    if not KB.exists():
        return None
    db = sqlite3.connect(f"file:{KB}?mode=ro", uri=True)
    row = db.execute("select n.name from img i join npk n on n.id=i.npk where i.path=? and lower(n.name) like 'sprite%' limit 1", (img_path,)).fetchone()
    db.close()
    return str(GAME / row[0]) if row else None


def geometry(img):
    """(x, y, w, h, canvas w, canvas h) per frame from the headers, without decoding pixels."""
    out = []
    for k in range(len(img.frames)):
        f = img.resolve(k)
        w, h = f.get("w", f.get("width", 0)), f.get("h", f.get("height", 0))
        out.append((f.get("x", 0), f.get("y", 0), w, h, f.get("cw", f.get("canvas_width")), f.get("ch", f.get("canvas_height"))))
    return out


def unit_box(sources, img_path, screen=False):
    """One box that holds every frame of this IMG in every given NPK, so original and new line up. Returns (box, frame count, canvas)."""
    boxes, canvas, count = [], None, 0
    for npk in sources:
        if not npk:
            continue
        img = load_img(npk, img_path)
        count = max(count, len(img.frames))
        for x, y, w, h, cw, ch in geometry(img):
            if w > 1 and h > 1:
                boxes.append((x, y, x + w, y + h))
            canvas = canvas or ((cw, ch) if cw and ch else None)
    if screen and canvas:
        return (0, 0, canvas[0], canvas[1]), count, canvas
    if not boxes:
        return (0, 0, 8, 8), count, canvas
    return (min(b[0] for b in boxes) - PAD, min(b[1] for b in boxes) - PAD, max(b[2] for b in boxes) + PAD, max(b[3] for b in boxes) + PAD), count, canvas


def frame(npk, img_path, k, box, palette=0):
    """Frame k of an IMG on the box; empty when the NPK lacks the IMG or the frame. palette picks a colour variant of indexed IMGs."""
    x0, y0, x1, y1 = box
    canvas = Image.new("RGBA", (x1 - x0, y1 - y0))
    if not npk:
        return canvas
    img = load_img(npk, img_path)
    if k >= len(img.frames):
        return canvas
    with lock:
        f = img.resolve(k)
        try:
            try:
                pic = img.image(k, palette) if palette else img.image(k)
            except (IndexError, TypeError):  # no such palette, or a V5 IMG (no palettes): the base colours
                pic = img.image(k)
        except Exception as error:  # a frame our reader cannot decode must not take the whole picture down; listed by broken()
            BROKEN.setdefault(img_path, f"{type(error).__name__}: {error}")
            pic = None
    if pic is not None:
        pic = pic.convert("RGBA")
        # Masked paste multiplies alpha twice (128 becomes 64), breaking exported translucent edits.
        canvas.alpha_composite(pic, (f.get("x", 0) - x0, f.get("y", 0) - y0))
    return canvas


def layout(w, h, n, screen=False):
    """Grid of an atlas: scale, cell size, columns. Deterministic, so the page can compute it from the unit's box too."""
    scale = min(1.0, SCREEN_CELL / w) if screen else 1.0
    cw, ch = max(1, round(w * scale)), max(1, round(h * scale))
    cols = max(1, min(n, math.ceil(math.sqrt(n * ch / cw))))
    while cols * cw > MAX_SIDE and cols > 1:
        cols -= 1
    rows = math.ceil(n / cols) if n else 1
    while rows * ch > MAX_SIDE:  # very long IMGs: shrink until the grid fits
        scale *= 0.8
        cw, ch = max(1, round(w * scale)), max(1, round(h * scale))
        cols = max(1, min(MAX_SIDE // cw, math.ceil(math.sqrt(n * ch / cw))))
        rows = math.ceil(n / cols)
    return dict(scale=scale, cw=cw, ch=ch, cols=cols, rows=rows, n=n)


def token(*paths):
    """Size and time of each source file, for cache keys."""
    parts = []
    for p in paths:
        if p and Path(p).exists():
            st = Path(p).stat()
            parts.append(f"{p}:{st.st_size}:{int(st.st_mtime)}")
        else:
            parts.append(f"{p}:none")
    return "|".join(parts)


def cached(key, build):
    """Bytes for key from kb/cache, building and storing them on a miss."""
    CACHE.mkdir(parents=True, exist_ok=True)
    # Shared cache schema: older images were made with masked paste and squared alpha.
    path = CACHE / f"{hashlib.sha1(('alpha-v2|' + key).encode('utf-8')).hexdigest()}.webp"
    if path.exists():
        return path.read_bytes()
    data = build()
    # Requests for the same atlas may finish together; each needs its own staging file.
    with tempfile.NamedTemporaryFile(dir=CACHE, prefix=path.stem + "_", suffix=".tmp", delete=False) as stream:
        stream.write(data)
        tmp = Path(stream.name)
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return data


def atlas(frames, grid):
    """Frames (equal-size RGBA images) packed into the grid from layout(), as lossless WebP."""
    sheet = Image.new("RGBA", (grid["cols"] * grid["cw"], grid["rows"] * grid["ch"]))
    for k, image in enumerate(frames):
        if grid["scale"] != 1.0:
            image = image.resize((grid["cw"], grid["ch"]), Image.LANCZOS)
        sheet.paste(image, ((k % grid["cols"]) * grid["cw"], (k // grid["cols"]) * grid["ch"]))
    buffer = io.BytesIO()
    sheet.save(buffer, "WEBP", lossless=True, method=0)
    return buffer.getvalue()


def img_atlas(npk, img_path, box, n, screen=False):
    """Atlas of one IMG from one NPK (None for 'the official one' is resolved by the caller)."""
    grid = layout(box[2] - box[0], box[3] - box[1], n, screen)
    key = f"img|{token(npk)}|{img_path}|{box}|{n}|{grid['scale']}"
    return cached(key, lambda: atlas([frame(npk, img_path, k, box) for k in range(n)], grid))


def webp(image):
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", lossless=True, method=0)
    return buffer.getvalue()
