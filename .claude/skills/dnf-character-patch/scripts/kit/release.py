"""Package: full costume-cover NPK with read-back checks, four-column comparison page, hero GIF, zip, install.

Skin paths share the new body. Every other costume path gets a transparent IMG with the same frame count, so no paid costume or
class add-on shows through. Paths with a frame count of another skeleton in the same class stay out of the package, so that skeleton
keeps its official look instead of turning invisible.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import struct
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from dnf_resources import NAME_KEY, NPK_MAGIC, ImgArchive, read_npk, save_json, write_v2

from .config import GAME, PARTS, ROOT, P
from .source import armed, native_world

COLS = 15
PAGE = Path(__file__).resolve().parents[2] / "assets/preview.html"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_shared_npk(entries):
    unique = {}
    payloads = []
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
    checksum = hashlib.sha256(header[:len(header) // 17 * 17]).digest()
    return bytes(header) + checksum + b"".join(payloads)


def frame(i):
    return Image.open(P.out / f"native_frames/{i:04d}.png").convert("RGBA")


def body_img():
    images, meta, seen = [], [], {}
    for index in range(P.frames):
        world = frame(index)
        box = world.getbbox()
        crop = world.crop(box)
        key = (box, hashlib.sha256(crop.tobytes()).hexdigest())
        images.append(crop)
        if key in seen:
            meta.append({"link": seen[key]})
        else:
            seen[key] = index
            meta.append({"x": box[0], "y": box[1], "canvas_width": P.canvas, "canvas_height": P.canvas})
    return write_v2(images, meta), len(seen)


def build():
    body, unique = body_img()
    assert ImgArchive(body).count == P.frames
    blanks = {}

    def blank(count):
        if count not in blanks:
            assert 0 < count <= 10000
            meta = [{"x": 0, "y": 0, "canvas_width": P.canvas, "canvas_height": P.canvas}] + [{"link": 0} for _ in range(count - 1)]
            blanks[count] = write_v2([Image.new("RGBA", (1, 1))] * count, meta)
        return blanks[count]

    skin_counts = Counter(r["frame_count"] for r in read_npk(GAME / f"{P.pack}_avatar_skin.NPK"))
    other_rigs = {count for count in skin_counts if count != P.frames}
    entries, kinds, skipped, sources = [], Counter(), Counter(), []
    for part in PARTS:
        path = GAME / f"{P.pack}_avatar_{part}.NPK"
        sources.append(dict(path=str(path), sha256=sha(path)))
        for row in read_npk(path):
            assert row["path"].startswith(P.prefix + part + "/") and row["frame_count"], row["path"]
            if row["frame_count"] in other_rigs:
                skipped[row["frame_count"]] += 1
                continue
            entries.append((row["path"], body if part == "skin" else blank(row["frame_count"])))
            kinds["skin" if part == "skin" else "costume"] += 1
    for path in sorted(GAME.glob(f"{P.pack}_growtype*.NPK")):
        sources.append(dict(path=str(path), sha256=sha(path)))
        for row in read_npk(path):
            assert row["path"].startswith(f"sprite/character/{P.cls}/{P.equipment}/growtype/") and row["frame_count"], row["path"]
            entries.append((row["path"], blank(row["frame_count"])))
            kinds["growtype"] += 1
    assert len({name for name, _ in entries}) == len(entries)
    entries.sort(key=lambda item: item[0])
    target = P.out / P.npk
    target.write_bytes(write_shared_npk(entries))

    raw = target.read_bytes()
    written = read_npk(target)
    assert [r["path"] for r in written] == [name for name, _ in entries]
    for row, (_, payload) in zip(written, entries, strict=True):
        assert raw[row["offset"]:row["offset"] + row["length"]] == payload
    for payload in blanks.values():
        archive = ImgArchive(payload)
        assert all(archive.image(i).getchannel("A").getbbox() is None for i in range(archive.count))
    skin = next(r for r in written if r["path"].endswith(P.body.split("/")[1] + ".img"))
    check = ImgArchive(raw[skin["offset"]:skin["offset"] + skin["length"]])
    for index in range(P.frames):
        info = check.resolve(index)
        world = Image.new("RGBA", (P.canvas, P.canvas))
        world.paste(check.image(index), (info["x"], info["y"]))
        decoded, expected = np.array(world), np.array(frame(index))
        assert np.array_equal(decoded[..., 3], expected[..., 3]), index
        visible = expected[..., 3] > 0
        assert np.array_equal(decoded[visible], expected[visible]), index
    report = dict(package=str(target), sha256=sha(target), bytes=target.stat().st_size, entries=len(entries), coverage=dict(kinds), other_rig_paths_left_official={str(k): v for k, v in skipped.items()},
                  frames=P.frames, unique_frames=unique, decoded_frames_match_rendered_pngs=True, source_packages=sources, game_runtime_validated=False)
    save_json(P.out / "validation.json", report)
    (P.out / (P.npk + ".sha256")).write_text(report["sha256"] + "  " + P.npk + "\n", "ascii")
    print(json.dumps({k: report[k] for k in ("sha256", "bytes", "entries", "coverage", "other_rig_paths_left_official", "unique_frames")}, ensure_ascii=False))


def _box():
    if P.preview_box:
        return tuple(P.preview_box)
    # Her costume and hair reach past the sprite and the weapon past both, so measure everything, or the page would crop them.
    boxes = [armed(image, i).getbbox() for i in range(P.frames) for image in (native_world(i), frame(i))]
    return (min(b[0] for b in boxes) - 10, min(b[1] for b in boxes) - 10, max(b[2] for b in boxes) + 10, max(b[3] for b in boxes) + 10)


def preview():
    folder = P.out / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    box = _box()
    cell = (box[2] - box[0], box[3] - box[1])
    rows = (P.frames + COLS - 1) // COLS

    def atlas(load, name):
        board = Image.new("RGBA", (COLS * cell[0], rows * cell[1]))
        for i in range(P.frames):
            board.paste(load(i).crop(box), ((i % COLS) * cell[0], (i // COLS) * cell[1]))
        board.save(folder / name, optimize=True)
        return "data:image/png;base64," + base64.b64encode((folder / name).read_bytes()).decode("ascii")

    weapon = P.weapon["label"] if P.weapon else "武器"
    columns = [("原版默认装（已去拖影）", atlas(native_world, "atlas_native.png")), (f"{P.character.get('name', '新角色')}（本次）", atlas(frame, "atlas_new.png"))]
    if P.weapon:
        columns += [(f"{P.character.get('name', '新角色')} + {weapon}（工程模拟，遮挡顺序未核实）", atlas(lambda i: armed(frame(i), i), "atlas_armed.png")),
                    (f"原版 + {weapon}（工程模拟）", atlas(lambda i: armed(native_world(i), i), "atlas_native_armed.png"))]
    html = "\n".join(f'<figure><figcaption>{label}</figcaption><div class="view"><canvas data-src="{src}"></canvas></div></figure>' for label, src in columns)
    data = [dict(name=c["name"], start=c["start"], end=c["end"]) for c in P.clips()]
    method = "动作表逐帧" + (" + H3" if any("sheet" not in c for c in P.clips()) else "")
    page = PAGE.read_text("utf-8").replace("__TITLE__", f"{P.title} v{P.version:02d}").replace("__COLUMNS__", html).replace("__METHOD__", method)
    page = page.replace("__CLIPS__", json.dumps(data, ensure_ascii=False)).replace("__CELL__", json.dumps(cell)).replace("__COLS__", str(COLS))
    (folder / "index.html").write_text(page, "utf-8")

    picks = [c for c in P.clips() if c["end"] - c["start"] >= 3][:10]
    order = [i for c in picks for i in range(c["start"], c["end"] + 1)]
    w, h = cell
    frames = []
    for i in order:
        board = Image.new("RGBA", (w * 2, h), (86, 97, 122, 255))
        board.paste((58, 66, 84, 255), (0, h - 18, w * 2, h))
        board.alpha_composite(native_world(i).crop(box), (0, 0))
        board.alpha_composite(frame(i).crop(box), (w, 0))
        frames.append(board.resize((w * 3, h * 3 // 2), Image.NEAREST).convert("P", palette=Image.ADAPTIVE, colors=192))
    frames[0].save(folder / "hero_compare.gif", save_all=True, append_images=frames[1:], duration=100, loop=0, disposal=2)


def release():
    package = P.out / P.npk
    notes = P.out / "安装说明.txt"
    notes.write_text(f"""{P.title} v{P.version:02d}

把 {P.npk} 放进游戏 ImagePacks2 目录（需先退出游戏）。卸载：退出游戏，移走这一个文件。

覆盖：这个职业的全部时装部位，转职附加外观隐藏。武器和技能特效保持原样。
离线校验通过，尚未在游戏内验证。
{P.notes}

SHA256：{sha(package)}
""", "utf-8")
    stem = P.out.name
    archive = P.out.parent / f"{stem}.zip"
    doc = ROOT / "docs" / f"{stem}.md"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in (package, notes, P.out / "validation.json", P.out / "preview/index.html", P.out / "preview/hero_compare.gif", P.master, doc):
            if path.exists():
                bundle.write(path, stem + "/" + path.name)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    print(archive, archive.stat().st_size, sha(package))


def install():
    running = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout.lower()
    # dnf_asura.exe (about 48 MB, protected path) stays after the game is closed; it is not the client, so only DNF.exe counts.
    if "dnf.exe" in running.split():
        raise SystemExit("Game is running; exit it first")
    archive = P.out.parent / f"{P.id}_retired_npks"
    for old in P.old_npks:
        # Two versions in the game folder would fight over the same paths; keep the old one with this project's output.
        if (GAME / old).exists():
            archive.mkdir(exist_ok=True)
            shutil.move(str(GAME / old), str(archive / old))
            print("moved out", old, "->", archive)
    target = GAME / P.npk
    shutil.copy2(P.out / P.npk, target)
    assert sha(target) == sha(P.out / P.npk)
    print("installed", target, sha(target))
