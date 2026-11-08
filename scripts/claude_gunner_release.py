"""Package the Claude gunner patch: full costume-cover NPK, comparison page, hero GIF and release zip.

Usage: python claude_gunner_release.py build | install
Reads the game packs only. `install` copies this project's one package and refuses while the game runs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from collections import Counter

import numpy as np
from PIL import Image

from build_fatfish_all_avatar_v02 import sha, write_shared_npk
from build_fatfish_doll_preview import PAGE
from claude_gunner import FRAMES, GAME, OUT, PREFIX, ROOT, native_world, weapon_world
from claude_gunner_gen import clips
from dnf_resources import ImgArchive, read_npk, save_json, write_v2

NAME = "A_Claude_FGunner_v02.NPK"
OLD_NAMES = ("A_Claude_FGunner_v01.NPK",)
PARTS = ("belt", "cap", "coat", "face", "hair", "neck", "pants", "shoes", "skin")
GROWTYPE = ("growtype", "growtype_atmechanic_3rd", "growtype_atranger_3rd", "growtype_atspitfire_3rd")
BOX = (110, 170, 400, 350)
CELL = (BOX[2] - BOX[0], BOX[3] - BOX[1])
COLS = 15
EXCLUDED = ["gunner paramedic body and hair (jpm_*, 320 frames, a separate rig)", "male gunner", "weapons", "skill effects", "aura and creatures"]


def body_img():
    images, meta, seen = [], [], {}
    for index in range(FRAMES):
        world = Image.open(OUT / f"native_frames/{index:04d}.png").convert("RGBA")
        box = world.getbbox()
        crop = world.crop(box)
        key = (box, hashlib.sha256(crop.tobytes()).hexdigest())
        images.append(crop)
        if key in seen:
            meta.append({"link": seen[key]})
        else:
            seen[key] = index
            meta.append({"x": box[0], "y": box[1], "canvas_width": 500, "canvas_height": 500})
    return write_v2(images, meta), len(seen)


def build():
    body, unique = body_img()
    assert ImgArchive(body).count == FRAMES
    blanks = {}

    def blank(count):
        if count not in blanks:
            assert 0 < count <= 10000
            meta = [{"x": 0, "y": 0, "canvas_width": 500, "canvas_height": 500}] + [{"link": 0} for _ in range(count - 1)]
            blanks[count] = write_v2([Image.new("RGBA", (1, 1))] * count, meta)
        return blanks[count]

    entries, kinds = [], Counter()
    sources = []
    for part in PARTS:
        path = GAME / f"sprite_character_gunner_atequipment_avatar_{part}.NPK"
        sources.append(dict(path=str(path), sha256=sha(path)))
        for row in read_npk(path):
            assert row["path"].startswith(PREFIX + part + "/") and row["frame_count"], row["path"]
            is_skin = part == "skin"
            assert not is_skin or row["frame_count"] == FRAMES
            entries.append((row["path"], body if is_skin else blank(row["frame_count"])))
            kinds["skin" if is_skin else "costume"] += 1
    for stem in GROWTYPE:
        path = GAME / f"sprite_character_gunner_atequipment_{stem}.NPK"
        sources.append(dict(path=str(path), sha256=sha(path)))
        for row in read_npk(path):
            assert row["path"].startswith("sprite/character/gunner/atequipment/growtype/") and row["frame_count"], row["path"]
            entries.append((row["path"], blank(row["frame_count"])))
            kinds["growtype"] += 1
    assert len({name for name, _ in entries}) == len(entries)
    entries.sort(key=lambda item: item[0])
    target = OUT / NAME
    target.write_bytes(write_shared_npk(entries))

    raw = target.read_bytes()
    written = read_npk(target)
    assert [r["path"] for r in written] == [name for name, _ in entries]
    blank_refs = 0
    for row, (_, payload) in zip(written, entries, strict=True):
        assert raw[row["offset"]:row["offset"] + row["length"]] == payload
        if payload != body:
            blank_refs += row["frame_count"]
    for payload in blanks.values():
        archive = ImgArchive(payload)
        assert all(archive.image(i).getchannel("A").getbbox() is None for i in range(archive.count))
    skin = next(r for r in written if r["path"].endswith("skin/gg_body0000.img"))
    check = ImgArchive(raw[skin["offset"]:skin["offset"] + skin["length"]])
    for index in range(FRAMES):
        frame = check.resolve(index)
        world = Image.new("RGBA", (500, 500))
        world.paste(check.image(index), (frame["x"], frame["y"]))
        decoded, expected = np.array(world), np.array(Image.open(OUT / f"native_frames/{index:04d}.png").convert("RGBA"))
        assert np.array_equal(decoded[..., 3], expected[..., 3]), index
        visible = expected[..., 3] > 0
        assert np.array_equal(decoded[visible], expected[visible]), index
    report = dict(package=str(target), sha256=sha(target), bytes=target.stat().st_size, entries=len(entries), coverage=dict(kinds), frames=FRAMES, unique_frames=unique,
                  transparent_logical_frames=blank_refs, decoded_frames_match_rendered_pngs=True, excluded=EXCLUDED, source_packages=sources, game_runtime_validated=False)
    save_json(OUT / "validation.json", report)
    (OUT / (NAME + ".sha256")).write_text(report["sha256"] + "  " + NAME + "\n", "ascii")
    print(json.dumps({k: report[k] for k in ("sha256", "bytes", "entries", "coverage", "unique_frames")}, ensure_ascii=False))


def frame(i):
    return Image.open(OUT / f"native_frames/{i:04d}.png").convert("RGBA")


def armed(i):
    world = frame(i)
    world.alpha_composite(weapon_world(i, layer="gg_rev0000b"))
    world.alpha_composite(weapon_world(i))
    return world


def armed_native(i):
    world = native_world(i)
    world.alpha_composite(weapon_world(i, layer="gg_rev0000b"))
    world.alpha_composite(weapon_world(i))
    return world


def atlas(load, path):
    rows = (FRAMES + COLS - 1) // COLS
    board = Image.new("RGBA", (COLS * CELL[0], rows * CELL[1]))
    for i in range(FRAMES):
        board.paste(load(i).crop(BOX), ((i % COLS) * CELL[0], (i // COLS) * CELL[1]))
    board.save(path, optimize=True)


def preview():
    folder = OUT / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    atlas(native_world, folder / "atlas_native.png")
    atlas(frame, folder / "atlas_new.png")
    atlas(armed, folder / "atlas_armed.png")
    atlas(armed_native, folder / "atlas_native_armed.png")
    data = [dict(name=c["name"], start=c["start"], end=c["end"]) for c in clips()]
    page = PAGE.replace("__CLIPS__", json.dumps(data, ensure_ascii=False)).replace("__CELL__", json.dumps(CELL)).replace("__COLS__", str(COLS))
    page = page.replace("<title>肥鱼纸娃娃 v03</title>", "<title>Claude 大小姐女枪手 v02</title>")
    page = page.replace("大肥鱼女法师 · 原生纸娃娃 v03", "女枪手 · Claude 大小姐 v02")
    page = page.replace("原生逐帧分层 + 手绘部件。三栏", "整体绘制：动作表逐帧 + H3 + 手枪贴合。四栏")
    # A fourth column, the source sprite with the same gun, so hand and gun contact can be compared directly.
    page = page.replace("</figure>\n</div></main>", '</figure>\n<figure><figcaption>原版 + 左轮</figcaption><div class="view"><canvas data-src="atlas_native_armed.png"></canvas></div></figure>\n</div></main>')
    page = page.replace("repeat(auto-fit,minmax(280px,1fr))", "repeat(auto-fit,minmax(300px,1fr))")
    for old, new, label_old, label_new in (
            ("atlas_native.png", "atlas_native.png", "原版默认装", "原版默认装（已去拖影）"),
            ("atlas_doll.png", "atlas_new.png", "v03 原生纸娃娃（本次）", "Claude 大小姐（本次）"),
            ("atlas_v02.png", "atlas_armed.png", "v02 视频路线（上一版）", "Claude 大小姐 + 左轮（工程模拟，遮挡顺序未核实）"),
            ("atlas_native_armed.png", "atlas_native_armed.png", "原版 + 左轮", "原版 + 左轮（工程模拟）")):
        encoded = base64.b64encode((folder / new).read_bytes()).decode("ascii")
        page = page.replace(f'data-src="{old}"', f'data-src="data:image/png;base64,{encoded}"').replace(label_old, label_new)
    (folder / "index.html").write_text(page, "utf-8")


def hero():
    order = list(range(68, 76)) * 2 + list(range(0, 10)) + list(range(21, 26)) + list(range(60, 68)) + list(range(76, 82)) * 2 + list(range(103, 119)) + list(range(119, 127))
    w, h = CELL
    frames = []
    for i in order:
        board = Image.new("RGBA", (w * 2, h), (86, 97, 122, 255))
        board.paste((58, 66, 84, 255), (0, h - 18, w * 2, h))
        board.alpha_composite(native_world(i).crop(BOX), (0, 0))
        board.alpha_composite(frame(i).crop(BOX), (w, 0))
        frames.append(board.resize((w * 3, h * 3 // 2), Image.NEAREST).convert("P", palette=Image.ADAPTIVE, colors=192))
    frames[0].save(OUT / "preview/hero_compare.gif", save_all=True, append_images=frames[1:], duration=100, loop=0, disposal=2)


def release():
    package = OUT / NAME
    notes = OUT / "安装说明.txt"
    notes.write_text(f"""女枪手 · Claude 大小姐 v02

把 {NAME} 放进游戏 ImagePacks2 目录，或运行 python scripts/claude_gunner_release.py install（需先退出游戏）。
卸载：退出游戏，移走这一个文件。它只覆盖女枪手路径，可以和女法师的肥鱼补丁同时安装。

覆盖：女枪手全部时装部位，转职附加外观隐藏。枪和技能特效保持原样。
不覆盖：女枪手的“医疗”路线有独立身体（jpm_*），不受影响。

离线校验通过，尚未在游戏内验证。
Claude 娘是民间二创形象，不是 Anthropic 官方形象，原作者和授权未核实，请仅自用。

SHA256：{sha(package)}
""", "utf-8")
    archive = ROOT / "output/claude_gunner_v02.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in (package, notes, OUT / "validation.json", OUT / "preview/index.html", OUT / "preview/hero_compare.gif", OUT / "parts/raw/claude_a_0.png", ROOT / "docs/claude_gunner_v02.md"):
            bundle.write(path, "Claude_Gunner_v02/" + path.name)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    print(archive, archive.stat().st_size, sha(package))


def install():
    running = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout.lower()
    if "dnf.exe" in running:
        raise SystemExit("Game is running; exit it first")
    for old in OLD_NAMES:
        # Two versions in the game folder would fight over the same paths; keep the old one with its own output.
        if (GAME / old).exists():
            shutil.move(str(GAME / old), str(OUT.parent / "Claude_Gunner_v01" / old))
            print("moved out", old)
    target = GAME / NAME
    shutil.copy2(OUT / NAME, target)
    assert sha(target) == sha(OUT / NAME)
    print("installed", target, sha(target))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "install":
        install()
    else:
        build()
        preview()
        hero()
        release()
