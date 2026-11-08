"""Package v06: NPK, comparison page, hero GIF and release zip."""
from __future__ import annotations

import base64
import json
import zipfile

from PIL import Image

from build_fatfish_all_avatar_v02 import sha
from build_fatfish_doll_preview import PAGE, world_native
from build_fatfish_doll_v03 import build
from fatfish_doll import ROOT
from fatfish_final import OUT, clips
from release_fatfish_luxe_v04 import BOX, CELL, COLS, atlas, frame

NAME = "A_Fatfish_FMage_Final_v06.NPK"
OLD = ROOT / "output/Fatfish_Complete_v01/native_frames"


def preview():
    folder = OUT / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    atlas(world_native, folder / "atlas_native.png")
    atlas(lambda i: frame(OUT / "native_frames", i), folder / "atlas_final.png")
    atlas(lambda i: frame(OLD, i), folder / "atlas_old.png")
    data = [dict(name=c["name"], start=c["start"], end=c["end"]) for c in clips()]
    page = PAGE.replace("__CLIPS__", json.dumps(data, ensure_ascii=False)).replace("__CELL__", json.dumps(CELL)).replace("__COLS__", str(COLS))
    page = page.replace("<title>肥鱼纸娃娃 v03</title>", "<title>大肥鱼普通版 v06</title>")
    page = page.replace("大肥鱼女法师 · 原生纸娃娃 v03", "大肥鱼女法师 · 普通版 v06")
    page = page.replace("原生逐帧分层 + 手绘部件。三栏", "整体绘制：新母版 + H3 + 姿态匹配抽帧。三栏")
    for old, new, label_old, label_new in (
            ("atlas_native.png", "atlas_native.png", "原版默认装", "原版默认装"),
            ("atlas_doll.png", "atlas_final.png", "v03 原生纸娃娃（本次）", "v06 普通版（本次）"),
            ("atlas_v02.png", "atlas_old.png", "v02 视频路线（上一版）", "旧 H3（v02）")):
        encoded = base64.b64encode((folder / new).read_bytes()).decode("ascii")
        page = page.replace(f'data-src="{old}"', f'data-src="data:image/png;base64,{encoded}"').replace(label_old, label_new)
    (folder / "index.html").write_text(page, "utf-8")


def hero():
    order = [10, 11, 12, 13] * 2 + list(range(0, 10)) * 2 + list(range(109, 128)) + list(range(135, 144)) + list(range(18, 22)) * 3
    w, h = CELL
    frames = []
    for i in order:
        board = Image.new("RGBA", (w * 2, h), (86, 97, 122, 255))
        board.paste((58, 66, 84, 255), (0, h - 18, w * 2, h))
        board.alpha_composite(frame(OLD, i).crop(BOX), (0, 0))
        board.alpha_composite(frame(OUT / "native_frames", i).crop(BOX), (w, 0))
        frames.append(board.resize((w * 4, h * 2), Image.NEAREST).convert("P", palette=Image.ADAPTIVE, colors=192))
    frames[0].save(OUT / "preview/hero_compare.gif", save_all=True, append_images=frames[1:], duration=100, loop=0, disposal=2)


def release():
    package = OUT / NAME
    notes = OUT / "安装说明.txt"
    notes.write_text(f"""大肥鱼女法师 · 普通版 v06

只安装一个肥鱼包：{NAME}
与其他肥鱼补丁覆盖相同路径，不要同装。切换可运行 scripts/switch_fatfish.py final（需先退出游戏）。
全时装覆盖与转职屏蔽范围与之前相同。

离线校验通过，尚未在游戏内验证。
二创角色素材按 CC BY-NC-SA 4.0，不得商用，鸣谢见 docs/fatfish_final_v06.md。

SHA256：{sha(package)}
""", "utf-8")
    archive = ROOT / "output/fatfish_final_v06.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in (package, notes, OUT / "validation.json", OUT / "preview/index.html", OUT / "preview/hero_compare.gif", OUT / "parts/raw/fit_b_0.png",
                     ROOT / "docs/fatfish_final_v06.md", ROOT / "design/fatfish/references/UPSTREAM_CREDITS.md"):
            bundle.write(path, "Fatfish_Final_v06/" + path.name)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    print(archive, archive.stat().st_size, sha(package))


if __name__ == "__main__":
    build(OUT, NAME)
    preview()
    hero()
    release()
