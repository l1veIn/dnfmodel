"""Writes the redrawn props back in the official frame order, recolors their cool glow layers, and merges everything with the Claude gunner patch into one NPK. Only reads the game folder."""
from __future__ import annotations

import colorsys
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from dnf_resources import NAME_KEY, NPK_MAGIC, ImgArchive, read_npk, write_v2  # noqa: E402
from gunner_props import FAMILIES, WORK, collect, geometry, load_img  # noqa: E402
from survey_gunner_effects import GAME, reader  # noqa: E402

OUT = ROOT / "output" / "claude_gunner_v06"
BASE = ROOT / "output" / "claude_gunner_v02" / "A_Claude_FGunner_v02.NPK"
NPK_NAME = "A_Claude_FGunner_v06.NPK"
FX = "sprite_character_gunner_effect_"
GLOW_PACKS = ["atg5falcon", "g0", "g1", "g2", "g3", "atmechboltmx", "at_sowalker", "atg-4_frisbee", "atg-operater", "atc_aed", "laserriflecharge", "laserriflecharge_90lvhcannon", "steyrheavyrifle", "steyrheavyrifle_90lvhcannon",
              "heavyweaponalteration", "heavyweaponalteration_90lvhcannon", "extruder", "extruder_90lvhcannon", "atpt-15prototype", "atoperationraze", "atsolasystem", "plasmaboost", "atplasmaboost"]
GLOW_LIMIT = 8_000_000
# Third-awakening cut-ins come from Grok first-frame videos (scripts/gunner_cutin_video.py); the others from key frames.
VIDEO = WORK.parent / "gunner_cutin_video"
VIDEO_CUTINS = {"mechanic_neo": VIDEO / "mechanic_neo/attempt_02/frames", "launcher_neo": VIDEO / "launcher_neo/attempt_01/frames", "spitfire_neo": VIDEO / "spitfire_neo/attempt_01/frames",
                "ranger_neo": VIDEO / "ranger_neo/attempt_01/frames", "paramedic_neo": VIDEO / "paramedic_neo/attempt_01/frames"}
CUTINS = {"launcher_neo": ["atgunner_launcher_neo", "(18)atgunner_launcher_neo"], "stormtrooper": ["atgunner_stormtrooper"], "spitfire_neo": ["atgunner_spitfire_neo"], "freyja": ["atgunner_freyja"], "mechanic_neo": ["atgunner_mechanic_neo"], "optimus": ["atgunner_optimus"],
          "ranger_neo": ["atgunner_ranger_neo"], "crimsonrose": ["atgunner_crimsonrose"], "paramedic_neo": ["atgunner_paramedic_neo"], "paramedic": ["atgunner_paramedic", "(18)atgunner_paramedic"], "coronis": ["atgunner_coronis", "(18)atgunner_coronis"]}
STOPS = np.array([[0, 0, 0], [92, 28, 10], [222, 98, 44], [248, 158, 84], [255, 236, 208]], np.float32)
POS = np.array([0, 0.2, 0.52, 0.8, 1.0], np.float32)


def write_shared_npk(entries):
    """Identical IMGs share one payload, as in the character patch. Thousands of its paths are the same blank image."""
    unique, payloads = {}, []
    offset = 52 + 264 * len(entries)
    header = bytearray(NPK_MAGIC + struct.pack("<I", len(entries)))
    for name, payload in entries:
        if payload not in unique:
            unique[payload] = offset
            payloads.append(payload)
            offset += len(payload)
        encoded = name.encode("utf-8")
        assert len(encoded) < 256
        header.extend(struct.pack("<II", unique[payload], len(payload)))
        header.extend(bytes(a ^ b for a, b in zip(encoded.ljust(256, b"\0"), NAME_KEY)))
    return bytes(header) + hashlib.sha256(header[:len(header) // 17 * 17]).digest() + b"".join(payloads)


def blank(frame):
    return Image.new("RGBA", (max(1, frame.get("w", 1)), max(1, frame.get("h", 1))))


def fitted(new, record):
    """A reused drawing on a frame up to a few pixels different in size: center it, so the object stays put."""
    w, h = record["w"], record["h"]
    if new.size == (w, h):
        return new
    page = Image.new("RGBA", (w, h))
    page.paste(new, ((w - new.width) // 2, (h - new.height) // 2))
    return page


def assemble():
    """{img path: bytes} for every redrawn IMG."""
    results, report = {}, {}
    for family, spec in FAMILIES.items():
        draw, records = collect(family)
        folder = WORK / "frames" / family
        keep_ids = set(spec.get("original_ids", [])) | set(spec.get("recolor_ids", []))
        orange_ids = set(spec.get("recolor_ids", []))
        done = {}
        for d in draw:
            path = folder / f"{d['id']:04d}.png"
            done[d["id"]] = None if d["id"] in keep_ids or not path.exists() else Image.open(path).convert("RGBA")
        missing = [d["id"] for d in draw if done[d["id"]] is None and d["id"] not in keep_ids]
        by_img = {}
        for record in records:
            by_img.setdefault((record["pack"], record["img"]), []).append(record)
        frames_total = 0
        for (pack, img_path), items in by_img.items():
            source_img, _ = load_img(pack, Path(img_path).stem)
            images, metadata = [], []
            for record in items:
                frame = source_img.frames[record["index"]]
                frames_total += 1
                if "link" in record:
                    images.append(Image.new("RGBA", (1, 1)))
                    metadata.append(dict(link=record["link"]))
                    continue
                metadata.append(geometry(frame))
                wanted = record.get("drawing", record.get("same_as"))
                new = done.get(wanted) if wanted is not None else None
                if new is None:
                    original = source_img.image(record["index"]) if frame["w"] * frame["h"] > 1 else None
                    if original is not None and wanted in orange_ids:
                        original = to_orange(original)
                    images.append(original.convert("RGBA") if original is not None else blank(frame))
                else:
                    images.append(fitted(new, record))
            results[img_path] = write_v2(images, metadata, preserve_links=True)
        report[family] = dict(imgs=len(by_img), frames=frames_total, drawn=len(draw) - len(keep_ids), missing=missing)
        print(family, report[family], flush=True)
    return results, report


def hue_share(rgba):
    a = np.asarray(rgba, np.float32)
    seen = a[..., 3] > 16
    rgb = a[..., :3][seen] / 255
    top, low = rgb.max(1), rgb.min(1)
    lit = rgb[(top > 0.27) & ((top - low) / np.maximum(top, 1e-3) > 0.18)]
    if len(lit) < 12:
        return 0, 0
    sample = lit[:: max(1, len(lit) // 1200)]
    cool = sum(1 for r, g, b in sample if 0.3 <= colorsys.rgb_to_hsv(float(r), float(g), float(b))[0] <= 0.92)
    return cool / len(sample), len(lit)


def to_orange(image):
    a = np.asarray(image.convert("RGBA"), np.float32)
    rgb = a[..., :3] / 255
    level = 0.65 * (0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2]) + 0.35 * rgb.max(2)
    out = np.stack([np.interp(level, POS, STOPS[:, c]) for c in range(3)], 2)
    return Image.fromarray(np.dstack([out, a[..., 3]]).astype(np.uint8), "RGBA")


def glow(done):
    """Cool-colored effect layers in the same packs, so an orange robot does not fire a blue beam."""
    results, skipped = {}, []
    for name in GLOW_PACKS:
        path = GAME / f"{FX}{name}.NPK"
        if not path.exists():
            continue
        with path.open("rb") as stream:
            for entry in read_npk(path):
                if entry["path"] in done or entry["version"] not in (2, 4, 5, 6):
                    continue
                stream.seek(entry["offset"])
                img = reader(stream.read(entry["length"]), entry["version"])
                real = [f for f in img.frames if "link" not in f and f["w"] * f["h"] > 16]
                if not real:
                    continue
                area = sum(f["w"] * f["h"] for f in real)
                mid = img.image(real[len(real) // 2]["index"])
                if mid is None:
                    continue
                share, lit = hue_share(mid)
                if share < 0.5:
                    continue
                if area > GLOW_LIMIT:
                    skipped.append((name, Path(entry["path"]).stem, round(area / 1e6, 1)))
                    continue
                images, metadata = [], []
                for frame in img.frames:
                    if "link" in frame:
                        images.append(Image.new("RGBA", (1, 1)))
                        metadata.append(dict(link=frame["link"]))
                        continue
                    metadata.append(geometry(frame))
                    pic = img.image(frame["index"]) if frame["w"] * frame["h"] > 1 else None
                    images.append(to_orange(pic) if pic is not None else blank(frame))
                results[entry["path"]] = write_v2(images, metadata, preserve_links=True)
    return results, skipped


def cutins():
    """Redrawn cut-ins, each in the official frame rectangles. The (18) twin is the same art."""
    results = {}
    for folder, stems in CUTINS.items():
        frames = VIDEO_CUTINS.get(folder, WORK.parent / "gunner_cutin" / folder / "frames")
        for stem in stems:
            img, entry = load_img(FX + "cutin", stem)
            images, metadata = [], []
            for frame in img.frames:
                if "link" in frame:
                    images.append(Image.new("RGBA", (1, 1)))
                    metadata.append(dict(link=frame["link"]))
                    continue
                # Each frame by its own extent: the new art is not the official shape, and an official rectangle would slice it.
                page = Image.open(frames / f"{frame['index']:02d}.png").convert("RGBA")
                box = page.getbbox()
                meta = geometry(frame)
                if box:
                    meta.update(x=box[0], y=box[1])
                    images.append(page.crop(box))
                else:
                    images.append(Image.new("RGBA", (1, 1)))
                metadata.append(meta)
            results[entry["path"]] = write_v2(images, metadata, preserve_links=True)
    return results


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    props, report = assemble()
    props.update(cutins())
    glows, skipped = glow(props)
    print("redrawn IMG", len(props), "glow IMG", len(glows), "glow MB", round(sum(map(len, glows.values())) / 1e6, 1), "props MB", round(sum(map(len, props.values())) / 1e6, 1))
    print("glow skipped as too large", skipped)
    base = []
    with BASE.open("rb") as stream:
        for entry in read_npk(BASE):
            stream.seek(entry["offset"])
            base.append((entry["path"], stream.read(entry["length"])))
    names = {n for n, _ in base}
    overlap = [p for p in {**props, **glows} if p in names]
    assert not overlap, overlap[:5]
    data = write_shared_npk(base + sorted({**glows, **props}.items()))
    target = OUT / NPK_NAME
    target.write_bytes(data)
    entries = read_npk(target)
    assert len(entries) == len(base) + len(props) + len(glows)
    assert len({e["path"] for e in entries}) == len(entries)
    # Read back: every new IMG parses, with the official frame count and offsets.
    checked = 0
    new_paths = {**glows, **props}
    by_path = {e["path"]: e for e in entries}
    sources = {}
    for family, spec in FAMILIES.items():
        _, records = collect(family)
        for record in records:
            sources[record["img"]] = record["pack"]
    with target.open("rb") as stream:
        for path, blob in new_paths.items():
            entry = by_path[path]
            stream.seek(entry["offset"])
            raw = stream.read(entry["length"])
            assert raw == blob
            new = ImgArchive(raw)
            pack = sources.get(path) or (FX + "cutin" if "/cutin/" in path else None)
            if pack is None:
                pack = next(FX + n for n in GLOW_PACKS if (GAME / f"{FX}{n}.NPK").exists() and any(e["path"] == path for e in read_npk(GAME / f"{FX}{n}.NPK")))
            old, _ = load_img(pack, Path(path).stem)
            assert new.count == len(old.frames), path
            for fo, fn in zip(old.frames, new.frames):
                assert ("link" in fo) == ("link" in fn), path
                if "link" not in fo and "/cutin/" not in path:
                    assert geometry(fo)["x"] == fn["x"] and geometry(fo)["y"] == fn["y"], path
            for k in range(new.count):
                new.image(k)
            checked += 1
    sha = hashlib.sha256(data).hexdigest()
    summary = dict(npk=NPK_NAME, bytes=len(data), sha256=sha, entries=len(entries), base_entries=len(base), redrawn_imgs=len(props), glow_imgs=len(glows), checked=checked, families=report, glow_skipped=skipped)
    (OUT / "validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    print({k: v for k, v in summary.items() if k not in ("families", "glow_skipped")})
    for family, item in report.items():
        if item["missing"]:
            print("MISSING", family, item["missing"])


if __name__ == "__main__":
    main()
