"""A deterministic, single-frame resize/registration probe; preserves all source bytes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "design/fatfish/action_samples_v01"
DEST = BATCH / "qa/registration_probe"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    source_path = BATCH / "raw/idle_01_0.png"
    source_bytes = source_path.read_bytes()
    raw = Image.open(source_path).convert("RGBA")
    composite = Image.open(ROOT / "materials/female_mage/reference_composite/frames/0010.png").convert("RGBA")
    reference = Image.new("RGBA", (500, 500))
    reference.alpha_composite(composite, (185, 0))
    # Manually estimated visible landmarks, not a skeletal detector.
    raw_eye, raw_sole = (550, 384), (490, 950)
    target_eye, target_sole = (249, 305), (244, 386)
    native_scale = (target_sole[1] - target_eye[1]) / (raw_sole[1] - raw_eye[1])
    size = tuple(round(v * native_scale) for v in raw.size)
    actual_scale = size[0] / raw.width
    translation = tuple(round(target_sole[i] - raw_sole[i] * actual_scale) for i in range(2))
    outputs = []
    for name, resampling in (("nearest", Image.Resampling.NEAREST), ("lanczos", Image.Resampling.LANCZOS)):
        resized = raw.resize(size, resampling)
        canvas = Image.new("RGBA", (500, 500))
        canvas.alpha_composite(resized, translation)
        filename = DEST / f"idle_01_{name}_native_canvas.png"
        canvas.save(filename)
        outputs.append((name, canvas, filename))
    # Show all panels in the same fixed viewport and at an integer display zoom.
    viewport, zoom = (202, 270, 300, 400), 4
    w, h = (viewport[2] - viewport[0]) * zoom, (viewport[3] - viewport[1]) * zoom
    top = 108
    sheet = Image.new("RGB", (w * 3, top + h + 118), "#263342")
    draw = ImageDraw.Draw(sheet)
    font = lambda n: ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", n)
    draw.text((16, 12), "站立帧：缩放与坐标校正试验", font=font(25), fill="white")
    draw.text((16, 49), "同一原生坐标窗口，统一放大 4 倍显示；锚点为人工估计，尚未修正身体姿势。", font=font(17), fill="#c6d2dd")
    panels = [("原女法师动作参考", reference), ("校正 + 最近邻降采样", outputs[0][1]), ("校正 + Lanczos 降采样", outputs[1][1])]
    for i, (title, canvas) in enumerate(panels):
        check = Image.new("RGBA", (w, h), "#d7dee8")
        cd = ImageDraw.Draw(check)
        for y in range(0, h, 24):
            for x in range(0, w, 24):
                if (x // 24 + y // 24) % 2:
                    cd.rectangle((x, y, x + 23, y + 23), fill="#ecf0f4")
        check.alpha_composite(canvas.crop(viewport).resize((w, h), Image.Resampling.NEAREST))
        cd = ImageDraw.Draw(check)
        ground_y = (target_sole[1] - viewport[1]) * zoom
        cd.line((0, ground_y, w, ground_y), fill="#a87324", width=2)
        for label, point, color in (("E", target_eye, "#cf5263"), ("F", target_sole, "#43809e")):
            x, y = (point[0] - viewport[0]) * zoom, (point[1] - viewport[1]) * zoom
            cd.line((x - 8, y, x + 8, y), fill=color, width=1)
            cd.line((x, y - 8, x, y + 8), fill=color, width=1)
        sheet.paste(check.convert("RGB"), (i * w, top))
        draw.text((i * w + 12, 80), title, font=font(19), fill="white")
    draw.text((16, top + h + 12), "E：参考眼位   F：参考鞋底。缩放后高度与鞋底已接近，头部横向位置和肢体仍有差异。", font=font(17), fill="#e9c98f")
    draw.text((16, top + h + 43), "这里只比较重采样方法，没有重画、改色或二值化透明度；不作为游戏成品。", font=font(17), fill="#c6d2dd")
    draw.text((16, top + h + 74), "原小样主体约 178 原生像素高 → 校正试验约 102 像素高；最终比例应由主帧确定。", font=font(17), fill="#c6d2dd")
    sheet.save(DEST / "comparison.png")
    report = dict(
        source=str(source_path), source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        reference_frame=10, original_canvas=[500, 500], guide_window=[122, 196, 378, 452],
        manual_landmarks=dict(generated_output_pixel_eye=raw_eye, generated_output_pixel_sole=raw_sole,
                              target_native_eye=target_eye, target_native_sole=target_sole,
                              caution="Visual estimates only, approximately 1-2 native pixels uncertainty; not certified engine anchors."),
        target_native_scale=native_scale, rounded_resized_canvas=list(size), actual_native_scale=actual_scale,
        translation=list(translation),
        transformed_eye=[round(translation[i] + raw_eye[i] * actual_scale, 3) for i in range(2)],
        transformed_sole=[round(translation[i] + raw_sole[i] * actual_scale, 3) for i in range(2)],
        unresolved=["head horizontal offset", "head/body and leg proportions", "hand pose", "accessory drift between independently generated frames", "native pixel cleanup and weapon occlusion"],
        outputs=[str(o[2]) for o in outputs], comparison=str(DEST / "comparison.png"),
        source_modified=False, new_generation_jobs=0, game_ready=False,
    )
    (DEST / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == report["source_sha256"]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
