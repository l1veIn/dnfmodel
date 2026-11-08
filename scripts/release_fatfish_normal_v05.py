"""Package the normal-proportion version: NPK, three-way page, release zip."""
from __future__ import annotations

import base64
import json
import zipfile

from build_fatfish_all_avatar_v02 import sha
from build_fatfish_doll_preview import PAGE, world_native
from build_fatfish_doll_v03 import build
from fatfish_doll import ROOT
from fatfish_doll_render import clips
from fatfish_normal import OUT
from release_fatfish_luxe_v04 import CELL, COLS, atlas, frame

NAME = "A_Fatfish_FMage_Normal_v05.NPK"
OLD = ROOT / "output/Fatfish_Complete_v01/native_frames"


def preview():
    folder = OUT / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    atlas(world_native, folder / "atlas_native.png")
    atlas(lambda i: frame(OUT / "native_frames", i), folder / "atlas_normal.png")
    atlas(lambda i: frame(OLD, i), folder / "atlas_h3.png")
    data = [dict(name=c["name"], start=c["start"], end=c["end"]) for c in clips()]
    page = PAGE.replace("__CLIPS__", json.dumps(data, ensure_ascii=False)).replace("__CELL__", json.dumps(CELL)).replace("__COLS__", str(COLS))
    page = page.replace("<title>肥鱼纸娃娃 v03</title>", "<title>大肥鱼正常比例 v05</title>")
    page = page.replace("大肥鱼女法师 · 原生纸娃娃 v03", "大肥鱼女法师 · 正常比例版 v05")
    for old, new, label_old, label_new in (
            ("atlas_native.png", "atlas_native.png", "原版默认装", "原版默认装"),
            ("atlas_doll.png", "atlas_normal.png", "v03 原生纸娃娃（本次）", "v05 分层正常比例（本次）"),
            ("atlas_v02.png", "atlas_h3.png", "v02 视频路线（上一版）", "v02 H3 抽帧（10 月旧版）")):
        encoded = base64.b64encode((folder / new).read_bytes()).decode("ascii")
        page = page.replace(f'data-src="{old}"', f'data-src="data:image/png;base64,{encoded}"').replace(label_old, label_new)
    (folder / "index.html").write_text(page, "utf-8")


def release():
    package = OUT / NAME
    notes = OUT / "安装说明.txt"
    notes.write_text(f"""大肥鱼女法师 · 正常比例版 v05

只安装一个肥鱼包：{NAME}
它与大头版、华丽大头版覆盖相同路径，不要同装。切换可运行 scripts/switch_fatfish.py normal、big 或 luxe（需先退出游戏）。
全时装覆盖与转职屏蔽范围与 v03 相同。

离线校验通过，尚未在游戏内验证。
二创角色素材按 CC BY-NC-SA 4.0，不得商用，鸣谢见 docs/fatfish_normal_v05.md。

SHA256：{sha(package)}
""", "utf-8")
    archive = ROOT / "output/fatfish_normal_v05.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in (package, notes, OUT / "validation.json", OUT / "preview/index.html", ROOT / "docs/fatfish_normal_v05.md",
                     ROOT / "design/fatfish/references/UPSTREAM_CREDITS.md"):
            bundle.write(path, "Fatfish_Normal_v05/" + path.name)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    print(archive, archive.stat().st_size, sha(package))


if __name__ == "__main__":
    build(OUT, NAME)
    preview()
    release()
