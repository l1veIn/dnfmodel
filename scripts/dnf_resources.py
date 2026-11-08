"""Local DNF NPK/IMG preparation utilities. Never writes into the game directory.

Format references: d-mod/ExtractorSharp (MIT), commit
433a8fddd85dea669623a1de905c2dec536b9ec5. See tools/vendor/ExtractorSharp/LICENSE.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import struct
import zlib
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
NPK_MAGIC = b"NeoplePack_Bill\0"
IMG_MAGIC = b"Neople Img File\0"
PREFIX = b"puchikon@neople dungeon and fighter "
NAME_KEY = PREFIX + bytes(b"DNF"[i % 3] for i in range(len(PREFIX), 255)) + b"\0"


def read_npk(path: Path) -> list[dict]:
    size = path.stat().st_size
    with path.open("rb") as stream:
        if stream.read(16) != NPK_MAGIC:
            raise ValueError(f"Not a DNF NPK: {path}")
        count, = struct.unpack("<I", stream.read(4))
        if count > (size - 20) // 264:
            raise ValueError("NPK entry count exceeds file size")
        entries = []
        for _ in range(count):
            offset, length = struct.unpack("<II", stream.read(8))
            encoded = stream.read(256)
            raw = bytes(a ^ b for a, b in zip(encoded, NAME_KEY)).split(b"\0", 1)[0]
            name = raw.decode("utf-8", errors="strict")
            if offset < 20 + count * 264 or offset + length > size:
                raise ValueError(f"Out-of-bounds NPK entry: {name}")
            entries.append(dict(npk=path.name, path=name, offset=offset, length=length))
        for entry in entries:
            stream.seek(entry["offset"])
            header = stream.read(min(32, entry["length"]))
            if header.startswith(IMG_MAGIC) and len(header) >= 32:
                index_length, version, frames = struct.unpack_from("<QII", header, 16)
                entry.update(version=version, frame_count=frames, index_length=index_length)
            else:
                entry.update(version=None, frame_count=None, index_length=None)
        return entries


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ImgArchive:
    """Read the V2/V4/V6 formats used by the selected female-mage templates."""

    def __init__(self, data: bytes):
        self.data = data
        if data[:16] != IMG_MAGIC:
            raise ValueError("Not a Neople IMG file")
        self.index_length, self.version, self.count = struct.unpack_from("<QII", data, 16)
        if self.version not in (2, 4, 6):
            raise NotImplementedError(f"IMG V{self.version}: use a compatible editor; no silent conversion")
        if self.count > 10000:
            raise ValueError("Unreasonable IMG frame count")
        stream = io.BytesIO(data)
        stream.seek(32)
        self.palettes = []
        if self.version in (4, 6):
            table_count = 1 if self.version == 4 else self._int(stream)
            if not 0 < table_count < 1024:
                raise ValueError("Invalid palette count")
            for _ in range(table_count):
                count = self._int(stream)
                if not 0 < count <= 256:
                    raise ValueError("Invalid palette size")
                self.palettes.append([list(stream.read(4)) for _ in range(count)])
        index_start = stream.tell()
        self.frames = []
        for i in range(self.count):
            color = self._int(stream)
            if color == 17:
                target = self._int(stream)
                if not 0 <= target < self.count or target == i:
                    raise ValueError(f"Invalid link frame {i} -> {target}")
                self.frames.append(dict(index=i, color=color, link=target))
            else:
                values = struct.unpack("<8i", stream.read(32))
                frame = dict(zip(["compression", "width", "height", "length", "x", "y", "canvas_width", "canvas_height"], values))
                frame.update(index=i, color=color)
                if frame["width"] < 0 or frame["height"] < 0 or frame["width"] * frame["height"] > 16_777_216:
                    raise ValueError(f"Invalid dimensions in frame {i}")
                self.frames.append(frame)
        if stream.tell() - index_start != self.index_length:
            raise ValueError("IMG frame index length does not match header")
        for frame in self.frames:
            if "link" in frame:
                continue
            size = frame["length"]
            if frame["compression"] == 5:
                size = frame["width"] * frame["height"] * (4 if frame["color"] == 16 else 2)
            if size < 0 or stream.tell() + size > len(data):
                raise ValueError("IMG payload exceeds file bounds")
            frame["data_offset"] = stream.tell()
            frame["data_length"] = size
            stream.seek(size, 1)
        self.consumed = stream.tell()

    @staticmethod
    def _int(stream):
        return struct.unpack("<i", stream.read(4))[0]

    def resolve(self, index: int) -> dict:
        seen = set()
        frame = self.frames[index]
        while "link" in frame:
            if frame["index"] in seen:
                raise ValueError("Cyclic frame reference")
            seen.add(frame["index"])
            frame = self.frames[frame["link"]]
        return frame

    def image(self, index: int, palette: int = 0) -> Image.Image:
        f = self.resolve(index)
        width, height = f["width"], f["height"]
        if width == 0 or height == 0:
            return Image.new("RGBA", (max(1, width), max(1, height)))
        raw = self.data[f["data_offset"]:f["data_offset"] + f["data_length"]]
        if f["compression"] == 6:
            raw = zlib.decompress(raw)
        elif f["compression"] != 5:
            raise NotImplementedError(f"Compression mode {f['compression']}")
        if self.version in (4, 6) and f["color"] == 14 and f["compression"] == 6:
            table = self.palettes[palette]
            if len(raw) != width * height or max(raw, default=0) >= len(table):
                raise ValueError("Palette-index payload is invalid")
            rgba = bytes(c for value in raw for c in table[value])
            return Image.frombytes("RGBA", (width, height), rgba)
        if f["color"] == 16:
            if len(raw) != width * height * 4:
                raise ValueError("BGRA payload size mismatch")
            return Image.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
        if f["color"] in (14, 15):
            if len(raw) != width * height * 2:
                raise ValueError("16-bit payload size mismatch")
            rgba = bytearray()
            for value, in struct.iter_unpack("<H", raw):
                if f["color"] == 14:
                    channels = [(value >> shift) & 31 for shift in (10, 5, 0)]
                    rgba.extend([(c << 3) | (c >> 2) for c in channels] + [255 if value & 32768 else 0])
                else:
                    rgba.extend([((value >> shift) & 15) * 17 for shift in (8, 4, 0, 12)])
            return Image.frombytes("RGBA", (width, height), bytes(rgba))
        raise NotImplementedError(f"Color format {f['color']}")


def write_v2(images: list[Image.Image], metadata: list[dict], preserve_links=True) -> bytes:
    headers, payloads = [], []
    for index, (image, frame) in enumerate(zip(images, metadata, strict=True)):
        if preserve_links and "link" in frame:
            headers.append(struct.pack("<ii", 17, frame["link"]))
            continue
        image = image.convert("RGBA")
        width, height = image.size
        payload = zlib.compress(image.tobytes("raw", "BGRA"))
        headers.append(struct.pack("<9i", 16, 6, width, height, len(payload), frame["x"], frame["y"], frame["canvas_width"], frame["canvas_height"]))
        payloads.append(payload)
    index_data = b"".join(headers)
    return IMG_MAGIC + struct.pack("<QII", len(index_data), 2, len(images)) + index_data + b"".join(payloads)


def write_npk(entries: list[tuple[str, bytes]]) -> bytes:
    header = bytearray(NPK_MAGIC + struct.pack("<I", len(entries)))
    offset = 52 + len(entries) * 264
    for name, data in entries:
        encoded = name.encode("utf-8")
        if len(encoded) >= 256:
            raise ValueError("IMG path exceeds NPK name field")
        padded = encoded.ljust(256, b"\0")
        header.extend(struct.pack("<II", offset, len(data)))
        header.extend(bytes(a ^ b for a, b in zip(padded, NAME_KEY)))
        offset += len(data)
    digest = hashlib.sha256(header[:len(header) // 17 * 17]).digest()
    return bytes(header) + digest + b"".join(data for _, data in entries)


def export_entry(entry: dict) -> dict:
    npk = ROOT / "sources/npk" / entry["npk"]
    with npk.open("rb") as stream:
        stream.seek(entry["offset"])
        raw = stream.read(entry["length"])
    img = ImgArchive(raw)
    stem = Path(entry["path"]).stem
    img_path = ROOT / "sources/img" / (stem + ".img")
    img_path.write_bytes(raw)
    dest = ROOT / "materials/female_mage/layers" / stem
    (dest / "frames").mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(img.count):
        source = img.frames[index]
        effective = img.resolve(index)
        record = dict(source)
        record.update({k: effective[k] for k in ("width", "height", "x", "y", "canvas_width", "canvas_height")})
        record["resolved_index"] = effective["index"]
        record["png"] = f"frames/{index:04d}.png"
        img.image(index).save(dest / record["png"])
        records.append(record)
    metadata = dict(source_npk=entry["npk"], img_path=entry["path"],
                    original_sha256=hashlib.sha256(raw).hexdigest(),
                    source_version=img.version, frame_count=img.count, palette_exported=0,
                    palettes=img.palettes, frames=records)
    save_json(dest / "frames.json", metadata)
    return dict(name=stem, frame_count=img.count, source_version=img.version,
                img_path=entry["path"], directory=str(dest.relative_to(ROOT)))


def contact_sheet(folder: Path, prefix: str, files: list[Path], columns=12, rows=6) -> list[str]:
    result = []
    cell = 112
    for start in range(0, len(files), columns * rows):
        selected = files[start:start + columns * rows]
        height = ((len(selected) + columns - 1) // columns) * (cell + 22)
        sheet = Image.new("RGB", (columns * cell, height), "#303641")
        draw = ImageDraw.Draw(sheet)
        for position, path in enumerate(selected):
            index = start + position
            left, top = (position % columns) * cell, (position // columns) * (cell + 22)
            image = Image.open(path).convert("RGBA")
            box = image.getbbox()
            if box:
                image = image.crop(box)
            scale = min((cell - 8) / image.width, (cell - 8) / image.height)
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.NEAREST)
            sheet.paste(image, (left + (cell - image.width) // 2, top + (cell - image.height) // 2), image)
            draw.text((left + 5, top + cell), f"#{index:03d}", fill="#ffffff")
        name = f"{prefix}_{start // (columns * rows) + 1:02d}.png"
        sheet.save(folder / name)
        result.append(name)
    return result


def prepare_templates() -> None:
    entries = json.loads((ROOT / "sources/img_index.json").read_text(encoding="utf-8"))
    pattern = re.compile(r"/avatar/(?:skin/mg_body0000|(?:hair|cap|face|neck|coat|belt|pants|shoes)/mg_[a-z]+0000[a-z](?:_mask1)?)\.img$")
    selected = [e for e in entries if pattern.search(e["path"])]
    layers = [export_entry(e) for e in selected]
    base = ROOT / "materials/female_mage"
    # This is a neutral design/registration reference, not a game-accurate draw-order implementation.
    order = ["mg_pants0000d", "mg_neck0000d", "mg_hair0000b", "mg_body0000",
             "mg_shoes0000b", "mg_shoes0000a", "mg_pants0000a", "mg_coat0000c",
             "mg_coat0000b", "mg_coat0000a", "mg_belt0000a", "mg_face0000b",
             "mg_hair0000a", "mg_cap0000c"]
    catalogs = {name: json.loads((base / "layers" / name / "frames.json").read_text(encoding="utf-8")) for name in order}
    count = catalogs["mg_body0000"]["frame_count"]
    resolved = [c["frames"][i] for c in catalogs.values() for i in range(min(count, c["frame_count"]))]
    min_x = min(f["x"] for f in resolved)
    min_y = min(f["y"] for f in resolved)
    max_x = max(f["x"] + f["width"] for f in resolved)
    max_y = max(f["y"] + f["height"] for f in resolved)
    canvas = (max_x - min_x, max_y - min_y)
    dest = base / "reference_composite"
    (dest / "frames").mkdir(parents=True, exist_ok=True)
    for i in range(count):
        image = Image.new("RGBA", canvas)
        for name in order:
            cat = catalogs[name]
            if i >= cat["frame_count"]:
                continue
            frame = cat["frames"][i]
            piece = Image.open(base / "layers" / name / frame["png"]).convert("RGBA")
            image.alpha_composite(piece, (frame["x"] - min_x, frame["y"] - min_y))
        image.save(dest / "frames" / f"{i:04d}.png")
    sheets = contact_sheet(dest, "contact", sorted((dest / "frames").glob("*.png")))
    save_json(dest / "reference.json", dict(frame_count=count, canvas=canvas, source_origin=[min_x, min_y],
              layers_back_to_front=order, sheets=sheets,
              note="Registration/design reference only. Layer order is provisional. Frame index order is not animation timing."))
    summary = dict(layer_count=len(layers), exported_png_count=sum(e["frame_count"] for e in layers),
                   reference_frame_count=count, layers=layers)
    save_json(base / "manifest.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "layers"}, indent=2))


def pack_layer(folder: Path, destination: Path, preserve_links=False) -> bytes:
    metadata = json.loads((folder / "frames.json").read_text(encoding="utf-8"))
    images = [Image.open(folder / frame["png"]).convert("RGBA") for frame in metadata["frames"]]
    data = write_v2(images, metadata["frames"], preserve_links=preserve_links)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return data


def validate_roundtrip() -> None:
    base = ROOT / "materials/female_mage/layers"
    records, entries = [], []
    for folder in sorted(base.iterdir()):
        if not (folder / "frames.json").exists():
            continue
        metadata = json.loads((folder / "frames.json").read_text(encoding="utf-8"))
        dest = ROOT / "validation/roundtrip/img" / (folder.name + ".img")
        data = pack_layer(folder, dest, preserve_links=True)
        img = ImgArchive(data)
        for i, record in enumerate(metadata["frames"]):
            expected = Image.open(folder / record["png"]).convert("RGBA")
            actual = img.image(i)
            if actual.size != expected.size or actual.tobytes() != expected.tobytes():
                raise AssertionError(f"Pixel mismatch: {folder.name}#{i}")
            effective = img.resolve(i)
            if any(effective[k] != record[k] for k in ("x", "y", "canvas_width", "canvas_height")):
                raise AssertionError(f"Coordinate mismatch: {folder.name}#{i}")
        entries.append((metadata["img_path"], data))
        records.append(dict(layer=folder.name, frames=img.count, pixels_and_coordinates_match=True,
                            links_preserved=sum("link" in f for f in img.frames)))
    package = ROOT / "validation/roundtrip/A_female_mage_template_check.NPK"
    package.write_bytes(write_npk(entries))
    reread = read_npk(package)
    for entry, (name, data) in zip(reread, entries, strict=True):
        with package.open("rb") as stream:
            stream.seek(entry["offset"])
            if entry["path"] != name or stream.read(entry["length"]) != data:
                raise AssertionError("NPK archive roundtrip failed")
    report = dict(status="passed", layers=len(records), frames=sum(r["frames"] for r in records),
                  npk_entry_count=len(reread), results=records,
                  scope="Offline pixel/coordinate/link and archive roundtrip only; not installed or tested in game.")
    save_json(ROOT / "validation/roundtrip_report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))


def build_index() -> None:
    rows = []
    packages = []
    for path in sorted((ROOT / "sources/npk").glob("*.NPK")):
        entries = read_npk(path)
        rows.extend(entries)
        packages.append(dict(name=path.name, count=len(entries),
                             versions=dict(Counter(str(e["version"]) for e in entries))))
    save_json(ROOT / "sources/img_index.json", rows)
    with (ROOT / "sources/img_index.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["npk", "path", "offset", "length", "version", "frame_count", "index_length"])
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(npk_count=len(packages), img_count=len(rows), packages=packages,
                   versions=dict(Counter(str(e["version"]) for e in rows)))
    save_json(ROOT / "sources/index_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["index", "prepare", "validate", "extract", "pack-layer", "pack-npk"])
    parser.add_argument("--layer", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--img", action="append", help="Exact IMG resource path; repeat to extract several")
    parser.add_argument("--manifest", type=Path, help="JSON list of {img_path, file}, paths relative to the manifest")
    args = parser.parse_args()
    if args.command == "index":
        build_index()
    elif args.command == "prepare":
        prepare_templates()
    elif args.command == "validate":
        validate_roundtrip()
    elif args.command == "pack-layer":
        if not args.layer or not args.output:
            parser.error("pack-layer requires --layer and --output")
        resolved_output = args.output.resolve()
        if not resolved_output.is_relative_to(ROOT):
            parser.error("Output must be inside this workspace")
        data = pack_layer(args.layer, resolved_output)
        print(json.dumps(dict(output=str(resolved_output), bytes=len(data))))
    elif args.command == "extract":
        if not args.img:
            parser.error("extract requires --img")
        index = json.loads((ROOT / "sources/img_index.json").read_text(encoding="utf-8"))
        selected = [e for e in index if e["path"] in args.img]
        if len(selected) != len(set(args.img)):
            parser.error("One or more IMG paths were not found unambiguously")
        print(json.dumps([export_entry(e) for e in selected], ensure_ascii=False, indent=2))
    elif args.command == "pack-npk":
        if not args.manifest or not args.output:
            parser.error("pack-npk requires --manifest and --output")
        destination = args.output.resolve()
        if not destination.is_relative_to(ROOT):
            parser.error("Output must be inside this workspace")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        entries = []
        for item in manifest:
            path = (args.manifest.parent / item["file"]).resolve()
            if not path.is_relative_to(ROOT):
                parser.error("Input IMG must be inside this workspace")
            data = path.read_bytes()
            ImgArchive(data)
            entries.append((item["img_path"], data))
        if len(set(name for name, _ in entries)) != len(entries):
            parser.error("Duplicate IMG paths")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(write_npk(entries))
        print(json.dumps(dict(output=str(destination), entries=len(entries), bytes=destination.stat().st_size)))


if __name__ == "__main__":
    main()
