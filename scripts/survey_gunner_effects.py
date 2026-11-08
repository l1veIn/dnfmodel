"""Read-only survey of the gunner skill-effect packs: size, colors, blend hints and a thumbnail per pack.

Effect IMGs are almost all V5 (DXT atlases), which dnf_resources.ImgArchive does not read.
Layout from tools/vendor/ExtractorSharp (MIT), FifthHandler.cs. Never writes into the game folder.
"""
from __future__ import annotations

import colorsys
import io
import json
import re
import struct
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from dnf_resources import ImgArchive, read_npk  # noqa: E402

GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
OUT = ROOT / "output" / "gunner_fx_survey"
EXTRA = ("sprite_character_common_3rdrare_effect_gunner", "sprite_character_common_3th_awake_gunner")


class V5:
    """Frame table and DXT atlases of one V5 IMG."""

    def __init__(self, data: bytes):
        self.data = data
        _, version, self.count = struct.unpack_from("<QII", data, 16)
        if version != 5:
            raise ValueError(f"not V5: {version}")
        off = 32
        table_count, _ = struct.unpack_from("<ii", data, off)
        off += 8
        palette = struct.unpack_from("<i", data, off)[0]
        off += 4 + palette * 4
        self.textures = []
        for _ in range(table_count):
            _, kind, _, length, full, w, h = struct.unpack_from("<7i", data, off)
            off += 28
            self.textures.append(dict(kind=kind, length=length, full=full, w=w, h=h))
        self.frames = []
        for i in range(self.count):
            kind = struct.unpack_from("<i", data, off)[0]
            off += 4
            if kind == 17:
                self.frames.append(dict(index=i, link=struct.unpack_from("<i", data, off)[0]))
                off += 4
                continue
            comp, w, h, length, x, y, cw, ch = struct.unpack_from("<8i", data, off)
            off += 32
            frame = dict(index=i, kind=kind, comp=comp, w=w, h=h, length=length, x=x, y=y, cw=cw, ch=ch)
            if kind < 17 and length != 0:
                frame["inline"] = True
            else:
                _, tex, x0, y0, x1, y1, top = struct.unpack_from("<7i", data, off)
                off += 28
                frame.update(tex=tex, rect=(x0, y0, x1, y1), rotated=top != 0)
            self.frames.append(frame)
        for tex in self.textures:
            tex["offset"] = off
            off += tex["length"]
        for frame in self.frames:
            if frame.get("inline"):
                frame["offset"] = off
                off += frame["length"]
        self._cache = {}

    def _atlas(self, index):
        if index not in self._cache:
            tex = self.textures[index]
            raw = zlib.decompress(self.data[tex["offset"]:tex["offset"] + tex["length"]])
            self._cache[index] = Image.open(io.BytesIO(raw)).convert("RGBA")
        return self._cache[index]

    def resolve(self, index):
        frame = self.frames[index]
        seen = set()
        while "link" in frame:
            if frame["index"] in seen:
                raise ValueError("cyclic link")
            seen.add(frame["index"])
            frame = self.frames[frame["link"]]
        return frame

    def image(self, index):
        frame = self.resolve(index)
        if frame["w"] <= 1 and frame["h"] <= 1:
            return None
        if frame.get("inline"):
            raw = zlib.decompress(self.data[frame["offset"]:frame["offset"] + frame["length"]]) if frame["comp"] == 6 else self.data[frame["offset"]:frame["offset"] + frame["length"]]
            if frame["kind"] == 16:
                return Image.frombytes("RGBA", (frame["w"], frame["h"]), raw, "raw", "BGRA")
            return None
        crop = self._atlas(frame["tex"]).crop(frame["rect"])
        return crop.transpose(Image.ROTATE_270) if frame["rotated"] else crop


def reader(data, version):
    if version == 5:
        return V5(data)
    img = ImgArchive(data)
    for frame in img.frames:
        if "link" not in frame:
            frame["w"], frame["h"] = frame["width"], frame["height"]
    return img


def frame_size(img, version):
    """(real frames, links, summed area, widest, tallest)."""
    real, links, area, width, height = 0, 0, 0, 0, 0
    for frame in img.frames:
        if "link" in frame:
            links += 1
            continue
        if frame["w"] <= 1 and frame["h"] <= 1:
            continue
        real += 1
        area += frame["w"] * frame["h"]
        width, height = max(width, frame["w"]), max(height, frame["h"])
    return real, links, area, width, height


def pixel_stats(image):
    """Hue and blend hints from one frame. Additive art sits on black or fades by brightness, so its transparent share is low."""
    rgba = np.asarray(image.convert("RGBA"), np.float32)
    if rgba.size == 0:
        return None
    solid = rgba[..., 3] > 16
    if solid.sum() < 16:
        return None
    rgb = rgba[..., :3][solid]
    top, low = rgb.max(1), rgb.min(1)
    black_share = float((top < 24).mean())
    lit = rgb[(top > 70) & ((top - low) / np.maximum(top, 1) > 0.18)]
    hist = np.zeros(12)
    for r, g, b in lit[:: max(1, len(lit) // 1500)] / 255:
        hist[int(colorsys.rgb_to_hsv(float(r), float(g), float(b))[0] * 12) % 12] += 1
    return dict(black=black_share, opaque=float(solid.mean()), hist=hist, saturated=len(lit) / max(1, len(rgb)), mean=float(top.mean()))


HUES = ["红", "橙", "黄", "黄绿", "绿", "青绿", "青", "天蓝", "蓝", "蓝紫", "紫", "品红"]


def scan_pack(path_text):
    path = Path(path_text)
    rows = []
    thumbs = []
    with path.open("rb") as stream:
        for entry in read_npk(path):
            row = dict(img=entry["path"], version=entry["version"], frames=entry["frame_count"], bytes=entry["length"])
            rows.append(row)
            if entry["version"] not in (2, 4, 5, 6):
                row["error"] = f"version {entry['version']}"
                continue
            stream.seek(entry["offset"])
            data = stream.read(entry["length"])
            try:
                img = reader(data, entry["version"])
                real, links, area, width, height = frame_size(img, entry["version"])
                row.update(real=real, links=links, area=area, w=width, h=height)
                if not real:
                    continue
                largest = max((f for f in img.frames if "link" not in f), key=lambda f: f["w"] * f["h"])
                picture = img.image(largest["index"])
                if picture is None:
                    continue
                stats = pixel_stats(picture)
                if stats:
                    row["black"], row["opaque"], row["mean"] = round(stats["black"], 3), round(stats["opaque"], 3), round(stats["mean"], 1)
                    row["hist"] = [int(v) for v in stats["hist"]]
                thumbs.append((area, entry["path"], picture.copy()))
            except Exception as error:  # A pack with one odd IMG must not stop the survey.
                row["error"] = repr(error)[:160]
    thumbs.sort(key=lambda t: -t[0])
    board = contact(path.stem, thumbs[:8])
    return dict(pack=path.stem, size=path.stat().st_size, imgs=rows, thumb=board)


def contact(stem, thumbs, cell=150, cols=4):
    if not thumbs:
        return None
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (20, 22, 30))
    pen = ImageDraw.Draw(sheet)
    for k, (_, name, picture) in enumerate(thumbs):
        shown = picture.copy()
        shown.thumbnail((cell - 4, cell - 4))
        x, y = (k % cols) * cell, (k // cols) * cell
        sheet.paste(shown, (x + (cell - shown.width) // 2, y + (cell - shown.height) // 2), shown)
        pen.text((x + 2, y + 1), Path(name).stem[:22], fill=(255, 225, 120))
    target = OUT / "thumbs" / f"{stem.replace('sprite_character_gunner_', '')}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, quality=82)
    return target.name


def main():
    packs = sorted(GAME.glob("sprite_character_gunner_effect*.NPK")) + [GAME / f"{name}.NPK" for name in EXTRA]
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        for k, result in enumerate(pool.map(scan_pack, map(str, packs), chunksize=4)):
            results.append(result)
            if k % 40 == 0:
                print(k, len(packs), round(time.time() - start), flush=True)
    (OUT / "survey_raw.json").write_text(json.dumps(results, ensure_ascii=False), "utf-8")
    errors = [(r["pack"], x["img"], x["error"]) for r in results for x in r["imgs"] if "error" in x]
    print("packs", len(results), "imgs", sum(len(r["imgs"]) for r in results), "errors", len(errors), "seconds", round(time.time() - start))
    print(errors[:10])


if __name__ == "__main__":
    main()
