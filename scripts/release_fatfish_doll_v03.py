"""Hero GIF, install notes and the release zip for v03."""
from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image

from build_fatfish_all_avatar_v02 import sha
from fatfish_doll import ROOT
from fatfish_doll_render import OUT

NATIVE = ROOT / "materials/female_mage/reference_composite/frames"
NAME = "A_Fatfish_FMage_NativeDoll_v03.NPK"
# Idle, walk, then a three-hit combo. Native and doll side by side at 3x.
ORDER = [10, 11, 12, 13] * 2 + list(range(0, 10)) * 2 + list(range(109, 128)) + [14, 15, 16, 17] * 2
BOX = (170, 250, 330, 396)


def hero():
    w, h = BOX[2] - BOX[0], BOX[3] - BOX[1]
    frames = []
    for i in ORDER:
        board = Image.new("RGBA", (w * 2, h), (86, 97, 122, 255))
        board.paste((58, 66, 84, 255), (0, h - 18, w * 2, h))
        native = Image.new("RGBA", (500, 500))
        native.alpha_composite(Image.open(NATIVE / f"{i:04d}.png").convert("RGBA"), (185, 0))
        board.alpha_composite(native.crop(BOX), (0, 0))
        board.alpha_composite(Image.open(OUT / f"native_frames/{i:04d}.png").convert("RGBA").crop(BOX), (w, 0))
        frames.append(board.resize((w * 6, h * 3), Image.NEAREST).convert("P", palette=Image.ADAPTIVE, colors=128))
    path = OUT / "preview/hero_compare.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0, disposal=2)
    print(path, path.stat().st_size)


def release():
    package = OUT / NAME
    digest = sha(package)
    notes = OUT / "安装说明.txt"
    notes.write_text(f"""大肥鱼女法师 · 原生纸娃娃 v03

只安装一个文件：{NAME}

1. 完全退出游戏。
2. 从 C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2 移出之前的肥鱼补丁（A_Fatfish_FMage_ 开头）。
   它们覆盖相同路径，不要同装。不要移动任何 sprite 开头的官方文件。
3. 把本文件放入 ImagePacks2，重新启动游戏。

本包同样覆盖全部女法时装路径，并屏蔽转职附加外观；其他使用相同资源路径的女法角色也会显示大肥鱼。
未屏蔽通用光环、宠物、普通武器或技能效果。

离线校验通过，尚未在游戏内验证。
二创角色素材按 CC BY-NC-SA 4.0，不得商用，鸣谢见 docs/fatfish_native_doll_v03.md。

SHA256：{digest}
""", "utf-8")
    archive = ROOT / "output/fatfish_native_doll_v03.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in (package, notes, OUT / "validation.json", OUT / "preview/index.html", OUT / "preview/hero_compare.gif",
                     ROOT / "docs/fatfish_native_doll_v03.md", ROOT / "design/fatfish/references/UPSTREAM_CREDITS.md"):
            bundle.write(path, "Fatfish_Doll_v03/" + path.name)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    print(archive, archive.stat().st_size, digest)


if __name__ == "__main__":
    hero()
    release()
