"""Package the luxe version: NPK, three-way preview page, hero GIF and release zip."""
from __future__ import annotations

import base64
import json
import zipfile

from PIL import Image

from build_fatfish_all_avatar_v02 import sha
from build_fatfish_doll_preview import PAGE, world_native
from build_fatfish_doll_v03 import build
from fatfish_doll import ROOT
from fatfish_doll_render import clips
from fatfish_luxe import OUT

NAME = "A_Fatfish_FMage_LuxeBigHead_v04.NPK"
BIG = ROOT / "output/Fatfish_Doll_v03/native_frames"
BOX = (130, 230, 400, 400)
CELL = (BOX[2] - BOX[0], BOX[3] - BOX[1])
COLS = 15


def frame(folder, i):
    return Image.open(folder / f"{i:04d}.png").convert("RGBA")


def atlas(load, path):
    board = Image.new("RGBA", (COLS * CELL[0], 12 * CELL[1]))
    for i in range(174):
        board.paste(load(i).crop(BOX), ((i % COLS) * CELL[0], (i // COLS) * CELL[1]))
    board.save(path, optimize=True)


def preview():
    folder = OUT / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    atlas(world_native, folder / "atlas_native.png")
    atlas(lambda i: frame(BIG, i), folder / "atlas_big.png")
    atlas(lambda i: frame(OUT / "native_frames", i), folder / "atlas_luxe.png")
    data = [dict(name=c["name"], start=c["start"], end=c["end"]) for c in clips()]
    page = PAGE.replace("__CLIPS__", json.dumps(data, ensure_ascii=False)).replace("__CELL__", json.dumps(CELL)).replace("__COLS__", str(COLS))
    page = page.replace("<title>肥鱼纸娃娃 v03</title>", "<title>大肥鱼华丽大头版 v04</title>")
    page = page.replace("大肥鱼女法师 · 原生纸娃娃 v03", "大肥鱼女法师 · 鲸歌女王华丽大头版 v04")
    page = page.replace("原生逐帧分层 + 手绘部件。三栏", "原版动作分层 + 手绘礼服、光翼与粒子。三栏")
    for old, new, label_old, label_new in (
            ("atlas_native.png", "atlas_native.png", "原版默认装", "原版默认装"),
            ("atlas_doll.png", "atlas_big.png", "v03 原生纸娃娃（本次）", "v03 大头版"),
            ("atlas_v02.png", "atlas_luxe.png", "v02 视频路线（上一版）", "v04 华丽大头版")):
        encoded = base64.b64encode((folder / new).read_bytes()).decode("ascii")
        page = page.replace(f'data-src="{old}"', f'data-src="data:image/png;base64,{encoded}"').replace(label_old, label_new)
    (folder / "index.html").write_text(page, "utf-8")


def hero():
    order = [10, 11, 12, 13] * 2 + list(range(0, 10)) * 2 + list(range(109, 128)) + list(range(135, 144))
    w, h = CELL
    frames = []
    for i in order:
        board = Image.new("RGBA", (w * 2, h), (86, 97, 122, 255))
        board.paste((58, 66, 84, 255), (0, h - 18, w * 2, h))
        board.alpha_composite(frame(BIG, i).crop(BOX), (0, 0))
        board.alpha_composite(frame(OUT / "native_frames", i).crop(BOX), (w, 0))
        frames.append(board.resize((w * 4, h * 2), Image.NEAREST).convert("P", palette=Image.ADAPTIVE, colors=192))
    path = OUT / "preview/hero_compare.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0, disposal=2)
    still = Image.new("RGBA", (w * 6, h * 3), (86, 97, 122, 255))
    still.alpha_composite(frame(OUT / "native_frames", 10).crop(BOX).resize((w * 3, h * 3), Image.NEAREST), (0, 0))
    still.alpha_composite(frame(OUT / "native_frames", 74).crop(BOX).resize((w * 3, h * 3), Image.NEAREST), (w * 3, 0))
    still.convert("RGB").save(OUT / "preview/hero_still.png")


def release():
    package = OUT / NAME
    notes = OUT / "安装说明.txt"
    notes.write_text(f"""大肥鱼女法师 · 鲸歌女王华丽大头版 v04

只安装一个肥鱼包：{NAME}
它与大头版 v03 覆盖相同路径，不要同装。切换可运行 scripts/switch_fatfish.py big 或 luxe（需先退出游戏）。

手动安装：
1. 完全退出游戏。
2. 从 C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2 移出 A_Fatfish_FMage_ 开头的旧补丁。不要动 sprite 开头的官方文件。
3. 把本文件放入 ImagePacks2，重新启动游戏。

全时装覆盖与转职屏蔽范围与 v03 相同。光翼使用半透明像素。
离线校验通过，尚未在游戏内验证。
二创角色素材按 CC BY-NC-SA 4.0，不得商用，鸣谢见 docs/fatfish_luxe_v04.md。

SHA256：{sha(package)}
""", "utf-8")
    archive = ROOT / "output/fatfish_luxe_bighead_v04.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in (package, notes, OUT / "validation.json", OUT / "preview/index.html", OUT / "preview/hero_compare.gif",
                     OUT / "parts/raw/concept_0.png", ROOT / "docs/fatfish_luxe_v04.md", ROOT / "design/fatfish/references/UPSTREAM_CREDITS.md"):
            bundle.write(path, "Fatfish_Luxe_v04/" + path.name)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    print(archive, archive.stat().st_size, sha(package))


if __name__ == "__main__":
    build(OUT, NAME)
    preview()
    hero()
    release()
