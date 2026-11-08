"""Reproduce the user's selected legacy NN standing probe; build an offline A/B NPK.

No provider calls, repainting, palette reduction, alpha thresholding, or game writes.
The six non-standing drawn slots and all hidden layers are inherited from v03.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from dnf_resources import ImgArchive, read_npk, save_json, write_npk, write_v2

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "design/fatfish/nearest_standing_v04"
DELIVERY = ROOT / "output/Fatfish_Nearest_Standing_v04"
PROBE = ROOT / "design/fatfish/action_samples_v01/qa/registration_probe"
BASE = ROOT / "output/Fatfish_v03_Pilot/A_Fatfish_FMage_7Frame_Pilot_v03.NPK"
NAME = "A_Fatfish_FMage_Nearest_Standing_v04.NPK"
WINDOW = (186, 252, 314, 400)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgba(path):
    return Image.open(path).convert("RGBA")


def font(size):
    return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)


def canvas_frame(archive, index):
    frame = archive.resolve(index)
    result = Image.new("RGBA", (500, 500))
    result.alpha_composite(archive.image(index), (frame["x"], frame["y"]))
    return result


def render(canvas, zoom, background="checker"):
    width, height = WINDOW[2] - WINDOW[0], WINDOW[3] - WINDOW[1]
    size = width * zoom, height * zoom
    result = Image.new("RGBA", size, "#d3dce7" if background == "checker" else "#121924")
    if background == "checker":
        draw = ImageDraw.Draw(result)
        cell = 8 * zoom
        for y in range(0, size[1], cell):
            for x in range(0, size[0], cell):
                if (x // cell + y // cell) % 2:
                    draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#ecf0f5")
    result.alpha_composite(canvas.crop(WINDOW).resize(size, Image.Resampling.NEAREST))
    return result.convert("RGB")


def make_previews(previous, chosen):
    ref = Image.new("RGBA", (500, 500))
    ref.alpha_composite(rgba(ROOT / "materials/female_mage/reference_composite/frames/0010.png"), (185, 0))
    panels = [("原女法师参考", ref), ("上版 v03：修整后的源图", previous), ("本次：早期源图＋最近邻", chosen)]
    sheet = Image.new("RGB", (1536, 1000), "#263342")
    draw = ImageDraw.Draw(sheet)
    draw.text((18, 12), "大肥鱼站姿 v04｜复现你选中的早期最近邻方案", font=font(28), fill="white")
    draw.text((18, 56), "相同游戏坐标、相同显示倍率；右图同时更换源图，不能将差别全部归因于滤镜。", font=font(18), fill="#c7d4e2")
    for col, (label, im) in enumerate(panels):
        x = col * 512
        draw.text((x + 14, 96), label, font=font(22), fill="white")
        view = render(im, 4)
        ImageDraw.Draw(view).line((0, (386 - WINDOW[1]) * 4, 511, (386 - WINDOW[1]) * 4), fill="#af7a31", width=2)
        sheet.paste(view, (x, 136))
        draw.text((x + 14, 747), "下方：原生 1 倍 / 深色背景", font=font(18), fill="#c7d4e2")
        sheet.paste(render(im, 1, "dark"), (x + 192, 782))
    draw.text((18, 966), "本次未重新生图、未减色、未锐化、未二值化透明度；肢体和遮挡尚需实机确认。", font=font(17), fill="#ddc18f")
    sheet.save(WORK / "standing_comparison.png")
    chosen.crop(WINDOW).save(WORK / "standing_native.png")
    render(chosen, 4).save(WORK / "standing_preview_4x.png")
    render(chosen, 4, "dark").save(WORK / "standing_dark_4x.png")


def main():
    # A failed partial build can resume, but never replace a published artifact.
    for marker in (WORK / "npk_validation.json", DELIVERY / "manifest.json"):
        if marker.exists():
            raise FileExistsError(f"Preserve existing version: {marker}")
    if (ROOT / "output" / NAME).exists():
        raise FileExistsError(NAME)
    probe = json.loads((PROBE / "report.json").read_text(encoding="utf-8"))
    source = Path(probe["source"])
    inputs = [source, PROBE / "report.json", PROBE / "idle_01_nearest_native_canvas.png", BASE]
    before = {str(p): digest(p) for p in inputs}
    assert before[str(source)] == probe["source_sha256"]
    assert before[str(BASE)] == "b8f2ace519f20a320c9a054657df1c26f93d6a729265f6a27834dc697a84b501"
    WORK.mkdir(parents=True, exist_ok=True)
    DELIVERY.mkdir(parents=True, exist_ok=True)

    raw = rgba(source)
    # Exact historical operation: one NN resize, then an integer translation.
    chosen = Image.new("RGBA", (500, 500))
    chosen.alpha_composite(raw.resize(tuple(probe["rounded_resized_canvas"]), Image.Resampling.NEAREST), tuple(probe["translation"]))
    assert np.array_equal(np.asarray(chosen), np.asarray(rgba(PROBE / "idle_01_nearest_native_canvas.png")))
    chosen.save(WORK / "standing_canvas.png")
    bbox = chosen.getchannel("A").getbbox()
    assert bbox is not None
    assert bbox[0] >= WINDOW[0] and bbox[1] >= WINDOW[1] and bbox[2] <= WINDOW[2] and bbox[3] <= WINDOW[3], bbox

    old_bytes = BASE.read_bytes()
    old_records = read_npk(BASE)
    skins = [r for r in old_records if "/avatar/skin/" in r["path"]]
    assert len(skins) == 38 and len(old_records) == 64
    old_payload = lambda r: old_bytes[r["offset"]:r["offset"] + r["length"]]
    payload = old_payload(skins[0])
    assert all(old_payload(r) == payload for r in skins)
    old_archive = ImgArchive(payload)
    assert old_archive.count == 174
    previous = canvas_frame(old_archive, 10)
    assert np.array_equal(np.asarray(previous), np.asarray(rgba(ROOT / "design/fatfish/master_and_actions_v02/master/master_feet_clean_canvas.png")))
    make_previews(previous, chosen)

    metadata = [dict(f) for f in old_archive.frames]
    images = [old_archive.image(i) for i in range(174)]
    metadata[10] = dict(x=bbox[0], y=bbox[1], canvas_width=500, canvas_height=500)
    images[10] = chosen.crop(bbox)
    body = write_v2(images, metadata, preserve_links=True)
    entries = [(r["path"], body if "/avatar/skin/" in r["path"] else old_payload(r)) for r in old_records]
    npk = ROOT / "output" / NAME
    npk.write_bytes(write_npk(entries))

    new_records = read_npk(npk)
    new_bytes = npk.read_bytes()
    assert [r["path"] for r in old_records] == [r["path"] for r in new_records]
    expected = [np.asarray(chosen if old_archive.resolve(i)["index"] == 10 else canvas_frame(old_archive, i)) for i in range(174)]
    updated_slots = [i for i in range(174) if old_archive.resolve(i)["index"] == 10]
    retained_slots = [i for i in range(174) if i not in updated_slots]
    count = 0
    for old, new in zip(old_records, new_records, strict=True):
        data = new_bytes[new["offset"]:new["offset"] + new["length"]]
        is_skin = "/avatar/skin/" in new["path"]
        if not is_skin:
            assert data == old_payload(old), new["path"]
        archive = ImgArchive(data)
        assert archive.count == 174
        for i in range(174):
            if is_skin:
                assert np.array_equal(np.asarray(canvas_frame(archive, i)), expected[i]), (new["path"], i)
                if i != 10:
                    assert archive.frames[i].get("link") == old_archive.frames[i].get("link")
                    for key in ("x", "y", "canvas_width", "canvas_height"):
                        assert archive.frames[i].get(key) == old_archive.frames[i].get(key)
            else:
                assert archive.image(i).getchannel("A").getbbox() is None
            count += 1
    assert retained_slots == [0, 1, 2, 3, 23, 65]
    assert count == 11136
    for path, initial_hash in before.items():
        assert digest(Path(path)) == initial_hash, path

    alpha = np.asarray(chosen)[:, :, 3]
    report = dict(
        package=str(npk), sha256=digest(npk), bytes=npk.stat().st_size,
        entry_count=len(new_records), skin_paths=38, unchanged_hidden_default_layers=26,
        img_frame_count=174, direct_standing_slot=10, updated_slots=updated_slots,
        unchanged_drawn_slots=retained_slots, fallback="167 unsupported slots still link to standing slot 10",
        decoded_frames_checked=count, all_pixel_position_link_checks_passed=True,
        source_inputs_sha256=before, sources_unchanged=True, legacy_probe_pixels_reproduced_exactly=True,
        visible_bbox=bbox, visible_height=bbox[3] - bbox[1],
        alpha_value_count=len(np.unique(alpha)), partially_transparent_pixels=int(((alpha > 0) & (alpha < 255)).sum()),
        processing="Original idle_01_0.png -> 147x147 NEAREST -> integer translation (174,250) on 500x500; unchanged alpha. No recolor/sharpen/threshold or new generation.",
        target_eye=probe["manual_landmarks"]["target_native_eye"], transformed_eye=probe["transformed_eye"],
        target_sole=probe["manual_landmarks"]["target_native_sole"], transformed_sole=probe["transformed_sole"],
        landmark_caution="Manual fitting anchors, not independent validation; original probe retains about 4 native px horizontal eye residual. No local limb correction was applied to this old standing art.",
        comparison_caution="v03 standing was already NEAREST with alpha thresholding. v04 also changes source art; this is a selected-look reproduction, not a filter-only A/B.",
        game_runtime_validated=False, game_installation_changed=False, new_generation_jobs=0,
        remaining_limits=["Six retained v03 poses use the later artwork and may pop against the legacy standing art", "Only default costume layers hidden", "No growtype additions", "Not a full walk cycle or full animation set"],
    )
    save_json(WORK / "npk_validation.json", report)
    save_json(WORK / "recipe.json", dict(
        source=str(source), source_sha256=digest(source), source_probe=str(PROBE / "report.json"),
        resample="NEAREST", resized_size=probe["rounded_resized_canvas"], translation=probe["translation"],
        alpha="preserved", palette_reduction=False, sharpening=False, canvas=[500, 500], viewport=list(WINDOW),
        base_npk=str(BASE), base_npk_sha256=digest(BASE), output_npk=str(npk),
        user_request="我觉得可以试试之前的矫正+最近邻采样方案（附旧站姿校正图）",
        generation_provenance=str(ROOT / "design/fatfish/action_samples_v01/journal.json"),
        source_requests=str(ROOT / "design/fatfish/action_samples_v01/requests.json"),
    ))
    instructions = f"""大肥鱼女法师 v04：早期站姿＋坐标矫正＋最近邻试装

补丁：{NAME}
本包精确复现你贴图里的早期站姿，未重新生图、减色、锐化或二值化透明度。
重要：v03 站姿本来已采用最近邻并清理透明度；本次换回了更早的源图，并非只改滤镜。

安装比较：
1. 退出游戏。将 ImagePacks2 内旧的 A_Fatfish_FMage_7Frame_Pilot_v03.NPK 移到游戏目录外备份。
2. 将本版 {NAME} 复制到 C:\\WeGameApps\\地下城与勇士：创新世纪\\ImagePacks2。
3. 相同资源的试装包一次只保留一个版本；无需替换官方 NPK。我们未自动写入游戏目录。
4. 用现有元素师即可，不要求未转职。先脱下装扮栏时装、让默认装扮显示；装备栏武器和防具无需脱下。
5. 对比同一场景、同一界面倍率下的站姿，优先看眼睛、蓝发高光、裙边、透明边缘和脚底位置。

范围与限制：
- 与 v03 完全相同的 64 个资源路径：38 个女法皮肤，26 个默认装扮隐藏层。
- IMG 10 改为这张早期站姿，167 个站姿占位槽随它更新。
- 0、1、2、3、23、65 六个已修动作与坐标保留 v03 原样；切换动作可能出现新旧画稿差异。本次优先比较静态站姿。
- 未完成动作仍会站姿占位，不代表完整动画。未新增隐藏职业装饰、技能或武器。
- 这次复用旧图的整体缩放和定位；眼位仍约有 4 个原生像素横向偏差，手脚姿势没有重新局部修正。
- 离线逐帧回读像素、坐标和引用已核对；本版实际显示与武器遮挡还需游戏内确认。

卸载或恢复：退出游戏，只移出本版 {NAME}。若要恢复 v03，再放回备份的 v03 NPK。
"""
    (WORK / "安装说明.txt").write_text(instructions, encoding="utf-8")
    (WORK / "README.md").write_text(
        "# v04：复现早期站姿最近邻方案\n\n"
        "复用用户所指的旧站姿原图和历史坐标；没有追加生成任务。保持 v03 覆盖范围与六个动作原样，仅更新站姿及引用站姿的占位槽。\n\n"
        "`standing_comparison.png` 上排为 4 倍最近邻显示，下排为原生 1 倍。旧图和 v03 源图不同，不是单变量滤镜实验。\n\n"
        "原输入和 v03 NPK 均保留；`recipe.json` 记录来源、哈希和操作，`npk_validation.json` 记录 11,136 帧位回读核对。未改动游戏安装目录，未宣称本版实机验收。\n",
        encoding="utf-8",
    )
    shutil.copy2(npk, DELIVERY / NAME)
    for filename in ("standing_comparison.png", "standing_native.png", "standing_preview_4x.png", "standing_dark_4x.png", "standing_canvas.png", "安装说明.txt", "npk_validation.json", "recipe.json", "README.md"):
        shutil.copy2(WORK / filename, DELIVERY / filename)
    for credit in (ROOT / "design/fatfish/references/UPSTREAM_CREDITS.md", ROOT / "design/fatfish/UPSTREAM_CREDITS.md"):
        if credit.exists():
            shutil.copy2(credit, DELIVERY / "UPSTREAM_CREDITS.md")
            break
    manifest = {p.name: dict(sha256=digest(p), bytes=p.stat().st_size) for p in sorted(DELIVERY.iterdir()) if p.is_file()}
    save_json(DELIVERY / "manifest.json", manifest)
    (npk.parent / (NAME + ".sha256")).write_text(digest(npk) + "  " + NAME + "\n", encoding="ascii")
    bundle = ROOT / "output/fatfish_nearest_standing_v04.zip"
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DELIVERY.iterdir()):
            archive.write(path, path.name)
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None
        for name, info in manifest.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == info["sha256"]
    print(json.dumps({k: report[k] for k in ("package", "sha256", "bytes", "decoded_frames_checked", "visible_bbox", "visible_height", "partially_transparent_pixels", "legacy_probe_pixels_reproduced_exactly", "all_pixel_position_link_checks_passed")}, ensure_ascii=False, indent=2))
    print(str(bundle))


if __name__ == "__main__":
    main()
