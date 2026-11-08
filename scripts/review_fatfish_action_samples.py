"""Inspect immutable provider PNGs and build diagnostic sheets; no generation calls."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "design/fatfish/action_samples_v01"
QA = BATCH / "qa"
FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")
COLORS = {"idle": "站立", "walk": "走路", "cast": "施法", "jump": "跳跃"}


def font(size):
    return ImageFont.truetype(str(FONT_PATH), size) if FONT_PATH.exists() else ImageFont.load_default()


def checker(size, cell=16):
    im = Image.new("RGBA", size, "#d8dee6")
    d = ImageDraw.Draw(im)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#eef1f5")
    return im


def bbox(alpha, threshold=8):
    return Image.fromarray((alpha > threshold).astype("uint8") * 255).getbbox()


def source_image(req, window, origin, scale):
    raw = Image.open(ROOT / "materials/female_mage/reference_composite/frames" / f"{req['source_frame']:04d}.png").convert("RGBA")
    box = tuple(window[i] - origin[i % 2] for i in range(4))
    size = ((window[2] - window[0]) * scale, (window[3] - window[1]) * scale)
    return raw.crop(box).resize(size, Image.Resampling.NEAREST)


def fixed_frame(im, side, registration):
    """Same whole-canvas scaling for all samples, never center/fit the alpha box."""
    canvas = checker((side, side))
    canvas.alpha_composite(im.resize((side, side), Image.Resampling.NEAREST))
    draw = ImageDraw.Draw(canvas)
    for pos in range(0, side, max(1, side // 8)):
        draw.line((pos, 0, pos, side), fill=(80, 100, 120, 45))
        draw.line((0, pos, side, pos), fill=(80, 100, 120, 45))
    x = round(registration["preview_root_x"] * side / 1024)
    y = round(registration["preview_ground_y"] * side / 1024)
    draw.line((x, 0, x, side), fill="#6f9db3", width=1)
    draw.line((0, y, side, y), fill="#c18b3b", width=2)
    return canvas.convert("RGB")


def main():
    QA.mkdir(exist_ok=True)
    requests = json.loads((BATCH / "requests.json").read_text(encoding="utf-8"))
    journal = json.loads((BATCH / "journal.json").read_text(encoding="utf-8"))
    registration = requests["registration"]
    origin = json.loads((ROOT / "materials/female_mage/reference_composite/reference.json").read_text(encoding="utf-8"))["source_origin"]
    window = registration["source_window"]
    rows = []
    images = {}
    sources = {}
    for req in requests["requests"]:
        name = req["name"]
        job = journal["jobs"][name]
        files = [Path(p) for p in job.get("files", [])]
        if len(files) != 1 or not files[0].exists():
            raise RuntimeError(f"Expected one completed file for {name}")
        path = files[0]
        with Image.open(path) as original:
            mode = original.mode
            dimensions = original.size
            image_format = original.format
            im = original.convert("RGBA")
        a = np.asarray(im.getchannel("A"))
        ab = bbox(a)
        strict = bbox(a, 127)
        corners = [a[:16, :16], a[:16, -16:], a[-16:, :16], a[-16:, -16:]]
        ref = source_image(req, window, origin, registration["output_scale"])
        rb = bbox(np.asarray(ref.getchannel("A")))
        row = dict(
            name=name, category=req["category"], source_frame=req["source_frame"],
            task_id=job.get("task_id"), path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            format=image_format, mode=mode, dimensions=list(dimensions),
            has_real_alpha=mode in ("RGBA", "LA") and int(a.min()) == 0 and int(a.max()) > 0,
            transparent_fraction=round(float(np.mean(a == 0)), 6),
            partial_alpha_fraction=round(float(np.mean((a > 0) & (a < 255))), 6),
            transparent_corner_patches=all(np.all(c == 0) for c in corners),
            alpha_bbox_gt_8=list(ab) if ab else None,
            alpha_bbox_gt_127=list(strict) if strict else None,
            touches_canvas_edge=bool(ab and (ab[0] == 0 or ab[1] == 0 or ab[2] == dimensions[0] or ab[3] == dimensions[1])),
            reference_alpha_bbox=list(rb),
            silhouette_height_ratio=round((ab[3] - ab[1]) / (rb[3] - rb[1]), 3) if ab else None,
            silhouette_bottom_delta_output_px=ab[3] - rb[3] if ab else None,
            silhouette_bottom_delta_native_px=(ab[3] - rb[3]) / 4 if ab else None,
            metric_caution="Silhouette extents only, not detected skeletal joints. New hair/tail/hat change silhouette; bottom is only a shoe-registration proxy. No auto-fitting or alignment correction performed.",
        )
        rows.append(row)
        images[name] = im
        sources[name] = ref
    # Generous cells keep details legible; raw frame coordinates remain intact.
    side, header, footer, cell_h = 512, 110, 72, 584
    sheet = Image.new("RGB", (side * 3, header + cell_h * 4 + footer), "#1d2735")
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 14), "大肥鱼 × 女法师｜12 张透明动作小样", font=font(30), fill="white")
    draw.text((24, 60), "同一画布比例；未按人物外框居中。橙线=原参考地面，蓝线=参考中轴。", font=font(19), fill="#b8c9d9")
    for i, row in enumerate(rows):
        x, y = (i % 3) * side, header + (i // 3) * cell_h
        sheet.paste(fixed_frame(images[row["name"]], side, registration), (x, y + 58))
        draw.text((x + 12, y + 5), f"{COLORS[row['category']]} {i % 3 + 1}  ·  {row['name']}", font=font(22), fill="white")
        draw.text((x + 12, y + 31), f"透明 PNG / 参考帧 {row['source_frame']:03d}", font=font(16), fill="#b8c9d9")
    draw.text((24, sheet.height - 58), "这是关键姿势测试，不是完整动画循环；尚未转换为游戏 IMG 或完成关节对齐。", font=font(20), fill="#eacb8f")
    sheet.save(QA / "contact_sheet.png")
    # Four category comparison sheets, 3 rows each: source on left, generated on right.
    comparisons = []
    for category in COLORS:
        cat_rows = [r for r in rows if r["category"] == category]
        compare = Image.new("RGB", (1024, 118 + 3 * 450), "#1d2735")
        cd = ImageDraw.Draw(compare)
        cd.text((20, 12), f"{COLORS[category]}｜原动作 / 生图原始结果", font=font(28), fill="white")
        cd.text((20, 57), "左：DNF 动作参考。右：生成图。画布等比显示，未校正位移和比例。", font=font(18), fill="#b8c9d9")
        for index, row in enumerate(cat_rows):
            y = 118 + index * 450
            cd.text((20, y), f"{row['name']} / frame {row['source_frame']:03d}", font=font(20), fill="white")
            cd.text((520, y), f"外框高度 {row['silhouette_height_ratio']:.2f}× / 底缘偏移 {row['silhouette_bottom_delta_native_px']:+.1f} 原生像素", font=font(17), fill="#eacb8f")
            compare.paste(fixed_frame(sources[row["name"]], 400, registration), (42, y + 40))
            compare.paste(fixed_frame(images[row["name"]], 400, registration), (554, y + 40))
        filename = f"alignment_{category}.png"
        compare.save(QA / filename)
        comparisons.append(str(QA / filename))
    # Slow pose flips make drift visible without claiming original timing or interpolation.
    previews = []
    for category in COLORS:
        frames = []
        for row in [r for r in rows if r["category"] == category]:
            fr = Image.new("RGB", (512, 584), "#1d2735")
            ImageDraw.Draw(fr).text((12, 12), f"{row['name']} | 3-pose test / not full cycle", font=font(18), fill="white")
            fr.paste(fixed_frame(images[row["name"]], 512, registration), (0, 60))
            frames.append(fr)
        path = QA / f"pose_flip_{category}.gif"
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=650, loop=0, optimize=False)
        previews.append(str(path))
    report = dict(
        inspected_at=datetime.now(timezone.utc).isoformat(), provider="65535", model="gpt-image-2.5",
        completed=len(rows), authorized_count=requests["count"], budget_usd=journal["budget_usd"],
        observed_account_cost_delta=journal.get("observed_cost_delta"), cost_unit=journal.get("usage_unit"),
        cost_caution=journal.get("spending_note"),
        alpha_pass=sum(r["has_real_alpha"] and r["transparent_corner_patches"] for r in rows),
        clipped_count=sum(r["touches_canvas_edge"] for r in rows),
        registration_analysis="Full original 1024 square retained. No bbox centering, rescaling, pose correction, matting, or pixel repainting of raw PNGs.",
        animation_caution="Three poses per category selected for a small test. Source animation names and timings not certified from ANI; pose GIFs are inspection flips only.",
        rows=rows, contact_sheet=str(QA / "contact_sheet.png"), alignment_sheets=comparisons, pose_flips=previews,
    )
    (QA / "alpha_and_registration_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("completed", "alpha_pass", "clipped_count", "observed_account_cost_delta", "cost_unit")}, ensure_ascii=False))
    for row in rows:
        print(json.dumps({k: row[k] for k in ("name", "dimensions", "alpha_bbox_gt_8", "silhouette_height_ratio", "silhouette_bottom_delta_native_px")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
