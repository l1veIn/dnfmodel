"""Read-only inspection of user-provided Blade patches; writes evidence to validation."""
from __future__ import annotations

import csv
import hashlib
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from dnf_resources import IMG_MAGIC, NAME_KEY, NPK_MAGIC, ImgArchive, save_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dnf刃"
OUT = ROOT / "validation/blade_patch_inspection"


def index(path):
    data = path.read_bytes()
    if data[:16] != NPK_MAGIC:
        raise ValueError("Not NPK")
    count, = struct.unpack_from("<I", data, 16)
    if count > (len(data) - 20) // 264:
        raise ValueError("Invalid index size")
    rows = []
    for i in range(count):
        start = 20 + i * 264
        offset, length = struct.unpack_from("<II", data, start)
        raw = bytes(a ^ b for a, b in zip(data[start + 8:start + 264], NAME_KEY)).split(b"\0", 1)[0]
        try:
            name = raw.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            name = raw.decode("gb18030")
            encoding = "gb18030"
        if offset < 20 + count * 264 or offset + length > len(data):
            raise ValueError(f"Invalid range: {name}")
        rows.append(dict(index=i, path=name, encoding=encoding, offset=offset, length=length))
    return data, rows


def describe_image(payload, export_path=None):
    archive = ImgArchive(payload)
    visible = []
    unique_pixels = set()
    boxes = []
    for i in range(archive.count):
        im = archive.image(i)
        box = im.getchannel("A").getbbox()
        if box:
            visible.append(i)
        unique_pixels.add(hashlib.sha256(im.tobytes() + str(im.size).encode()).hexdigest())
        f = archive.resolve(i)
        boxes.append(dict(index=i, width=f["width"], height=f["height"], x=f["x"], y=f["y"],
                          canvas_width=f["canvas_width"], canvas_height=f["canvas_height"],
                          alpha_bbox=box, link=archive.frames[i].get("link")))
    result = dict(version=archive.version, frame_count=archive.count,
                  stored_frames=sum("link" not in f for f in archive.frames),
                  linked_frames=sum("link" in f for f in archive.frames),
                  visible_frame_count=len(visible), entirely_transparent=not visible,
                  unique_pixel_frames=len(unique_pixels), consumed_bytes=archive.consumed,
                  trailing_bytes=len(payload) - archive.consumed)
    if export_path:
        export_path.mkdir(parents=True, exist_ok=True)
        save_json(export_path / "frames.json", boxes)
        ids = [i for i in (0, 1, 10, 20, 30, 40, 60, 80, 100, 120, 140, 160) if i < archive.count]
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
        sheet = Image.new("RGB", (4 * 300, 3 * 360 + 62), "#283341")
        d = ImageDraw.Draw(sheet)
        d.text((16, 14), "直接从单个“本体图层”解出的帧（仅裁透明边缘并放大显示）", font=font, fill="white")
        for j, i in enumerate(ids):
            im = archive.image(i)
            im.save(export_path / f"{i:04d}.png")
            bb = im.getchannel("A").getbbox()
            if not bb:
                continue
            cut = im.crop(bb)
            zoom = min(3, 270 // cut.width, 310 // cut.height)
            zoom = max(1, zoom)
            cut = cut.resize((cut.width * zoom, cut.height * zoom), Image.Resampling.NEAREST)
            x, y = j % 4 * 300, j // 4 * 360 + 62
            cell = Image.new("RGBA", (300, 320), "#c3cbd5")
            cell.alpha_composite(cut, ((300 - cut.width) // 2, (320 - cut.height) // 2))
            sheet.paste(cell.convert("RGB"), (x, y))
            d.text((x + 12, y + 325), f"frame {i:03d}  /  {im.width}×{im.height}", font=font, fill="white")
        sheet.save(export_path / "body_contact_sheet.png")
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    all_reports = []
    for source in sorted(SOURCE.rglob("*")):
        if not source.is_file() or source.suffix.lower() != ".npk":
            continue
        data, entries = index(source)
        groups = defaultdict(list)
        for entry in entries:
            groups[(entry["offset"], entry["length"])].append(entry)
        kind = "costume_normal" if "普通脸" in source.name else "costume_gloomy" if "阴沉脸" in source.name else "weapon" if "全武器" in source.name else "voice" if "语音" in str(source.parent) else "skill_effect"
        folder = OUT / kind
        folder.mkdir(exist_ok=True)
        with (folder / "index.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(entries[0]))
            writer.writeheader()
            writer.writerows(entries)
        payloads = []
        for (offset, length), members in groups.items():
            payload = data[offset:offset + length]
            paths = [e["path"] for e in members]
            block = dict(offset=offset, length=length, sha256=hashlib.sha256(payload).hexdigest(), alias_count=len(paths),
                         representative_paths=paths[:12], folders=dict(Counter(str(Path(p).parent).replace("\\", "/") for p in paths)))
            if payload.startswith(IMG_MAGIC):
                try:
                    is_body = any(p.endswith("/本体图层.img") for p in paths)
                    block.update(describe_image(payload, folder / "body_frames" if is_body else None))
                    if is_body:
                        (folder / "body_source.img").write_bytes(payload)
                except Exception as e:
                    block["decode_error"] = str(e)
                    _, version, frames = struct.unpack_from("<QII", payload, 16)
                    block.update(version=version, frame_count=frames)
            else:
                block["format_signature"] = payload[:4].decode("ascii", "replace")
            payloads.append(block)
        report = dict(source=str(source), file_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                      entry_count=len(entries), index_bytes=20 + len(entries) * 264,
                      unique_payload_ranges=len(groups),
                      entry_folders=dict(Counter(str(Path(e["path"]).parent).replace("\\", "/") for e in entries)),
                      payloads=payloads)
        save_json(folder / "report.json", report)
        all_reports.append(dict(kind=kind, source=source.name, entries=len(entries), unique_payload_ranges=len(groups),
                                transparent_aliases=sum(p["alias_count"] for p in payloads if p.get("entirely_transparent")),
                                visible_img_aliases=sum(p["alias_count"] for p in payloads if p.get("visible_frame_count", 0)),
                                decode_errors=sum("decode_error" in p for p in payloads),
                                report=str(folder / "report.json")))
    save_json(OUT / "summary.json", all_reports)
    print(json.dumps(all_reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
