"""Diagnostic sheets and byte/registration checks for the v02 master/action test."""
from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from fatfish_v02 import BATCH, ROOT, WINDOW, digest, save

LABELS = {"master": "站姿主帧", "walk": "走路测试", "cast": "施法测试", "jump": "跳跃测试"}


def font(n):
    return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", n)


def check(size, cell=16):
    im = Image.new("RGBA", size, "#d2dae5")
    d = ImageDraw.Draw(im)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#edf1f6")
    return im


def render(native, scale, ground=None):
    im = check((128 * scale, 128 * scale), max(1, 8 * scale))
    im.alpha_composite(native.resize(im.size, Image.Resampling.NEAREST))
    if ground is not None:
        y = round((ground - WINDOW[1]) * scale)
        ImageDraw.Draw(im).line((0, y, im.width, y), fill="#b48134", width=1)
    return im.convert("RGB")


def native(path):
    im = Image.open(path).convert("RGBA")
    if im.size == (500, 500):
        im = im.crop(WINDOW)
    return im


def main():
    qa = BATCH / "qa"
    qa.mkdir(exist_ok=True)
    selection = json.loads((BATCH / "master/selection.json").read_text(encoding="utf-8"))
    chosen = selection["name"]
    pose_selection_path = qa / "action_selection.json"
    pose_selection = json.loads(pose_selection_path.read_text(encoding="utf-8")) if pose_selection_path.exists() else {}
    meta = json.loads((BATCH / "references/pose_landmarks.json").read_text(encoding="utf-8"))["poses"]
    journal = json.loads((BATCH / "journal.json").read_text(encoding="utf-8"))
    receipts = json.loads((qa / "provider_receipts.json").read_text(encoding="utf-8"))
    raw_reports = []
    for name, job in journal["jobs"].items():
        if job["state"] != "downloaded":
            raise RuntimeError(f"Incomplete job {name}")
        path = Path(job["files"][0])
        im = Image.open(path)
        a = np.asarray(im.convert("RGBA"))[:, :, 3]
        mask = Image.fromarray((a >= 128).astype("uint8") * 255)
        bb = mask.getbbox()
        corners = [a[:16, :16], a[:16, -16:], a[-16:, :16], a[-16:, -16:]]
        raw_reports.append(dict(name=name, task_id=job["task_id"], file=str(path), sha256=digest(path),
                                mode=im.mode, size=list(im.size), alpha_range=[int(a.min()), int(a.max())],
                                real_alpha=bool(im.mode == "RGBA" and a.min() == 0 and a.max() > 0),
                                transparent_corners=all(np.all(c == 0) for c in corners),
                                solid_bbox=bb, clipped=bb[0] == 0 or bb[1] == 0 or bb[2] == im.width or bb[3] == im.height))
    specimens = {}
    registrations = {}
    native_checks = []
    for name in LABELS:
        key = chosen if name == "master" else pose_selection.get(name, name)
        folder = BATCH / ("master" if name == "master" else "registered")
        stage = Image.open(folder / f"{key}_clean_canvas.png").convert("RGBA")
        bb = stage.getchannel("A").getbbox()
        if not bb:
            raise RuntimeError(f"Empty registered result: {name}")
        native_checks.append(dict(name=name, visible_bbox=bb,
                                  wholly_inside_native_window=bb[0] >= WINDOW[0] and bb[1] >= WINDOW[1] and bb[2] <= WINDOW[2] and bb[3] <= WINDOW[3],
                                  strict_alpha_values=[int(v) for v in np.unique(np.asarray(stage)[:, :, 3])]))
        specimens[name] = native(folder / f"{key}_clean_canvas.png")
        registrations[name] = json.loads((folder / f"{key}.registration.json").read_text(encoding="utf-8"))
    # Art review at a common 3x zoom and at native 1x, without hiding scale drift.
    sheet = Image.new("RGB", (1536, 698), "#243242")
    d = ImageDraw.Draw(sheet)
    d.text((20, 12), "大肥鱼女法师 v02｜主帧与三张动作测试", font=font(28), fill="white")
    d.text((20, 53), "统一原生坐标窗口；上排 3 倍显示，下排原生尺寸。棋盘格仅供检查透明背景。", font=font(18), fill="#b8cbdc")
    for i, (name, label) in enumerate(LABELS.items()):
        x = i * 384
        d.text((x + 12, 88), label, font=font(23), fill="white")
        sheet.paste(render(specimens[name], 3), (x, 128))
        sheet.paste(render(specimens[name], 1), (x + 128, 550))
        d.text((x + 12, 520), "原生 128×128 窗口（人物约 100 px）", font=font(15), fill="#b8cbdc")
    sheet.save(qa / "v02_contact_sheet.png")
    # Old vs new nearest/strict-alpha and area averaging. Same coordinates.
    old = native(ROOT / "design/fatfish/action_samples_v01/qa/registration_probe/idle_01_nearest_native_canvas.png")
    # Old registration probe used a different crop, but the saved file is a 500 square.
    folder = BATCH / "master"
    method_panels = [("旧站姿缩小", old), ("新主帧：最近邻＋边缘清理", specimens["master"]),
                    ("新主帧：BOX 面积平均", native(folder / f"{chosen}_box_canvas.png"))]
    comparison = Image.new("RGB", (1536, 686), "#243242")
    cd = ImageDraw.Draw(comparison)
    cd.text((20, 10), "缩小方法与源图简化的对照", font=font(27), fill="white")
    cd.text((20, 50), "全部是同一游戏像素尺度，统一放大 4 倍。未强制减色；旧图与新图均保留原文件。", font=font(18), fill="#b8cbdc")
    for i, (label, im) in enumerate(method_panels):
        cd.text((i * 512 + 12, 82), label, font=font(21), fill="white")
        comparison.paste(render(im, 4), (i * 512, 122))
    cd.text((20, 650), "主帧改画、尺寸对齐与透明边缘清理共同影响观感；本图不是严格的单变量实验。", font=font(17), fill="#dfc792")
    comparison.save(qa / "master_cleanup_comparison.png")
    alignment = Image.new("RGB", (1024, 106 + 4 * 430), "#243242")
    ad = ImageDraw.Draw(alignment)
    ad.text((20, 12), "动作位置对照：左原动作，右本轮校正结果", font=font(27), fill="white")
    ad.text((20, 54), "橙线为参考鞋底高度；锚点由人工目测，不代表完整骨骼或实机验收。", font=font(18), fill="#b8cbdc")
    metrics = []
    for i, (name, label) in enumerate(LABELS.items()):
        row_y = 106 + i * 430
        reg = registrations[name]
        eye_error = [reg["actual_eye"][j] - reg["target_eye"][j] for j in (0, 1)]
        sole_error = [reg["actual_sole"][j] - reg["target_sole"][j] for j in (0, 1)]
        metric = dict(name=name, eye_residual_native_px=eye_error, sole_residual_native_px=sole_error,
                      raw_silhouette_scale_before_registration=reg["scale_y"] * 8,
                      caution="Eye/sole are used to fit scale and placement, not independent hold-out validation. Hands, knees and body proportions require visual or separate landmark checks.")
        metrics.append(metric)
        ad.text((16, row_y), f"{label} / frame {meta[name]['frame']:03d}", font=font(21), fill="white")
        ad.text((520, row_y), f"眼位残差 {math.hypot(*eye_error):.1f}px；鞋底 {math.hypot(*sole_error):.1f}px", font=font(18), fill="#dfc792")
        src = Image.open(BATCH / f"references/{name}_original_native.png").convert("RGBA")
        alignment.paste(render(src, 3, meta[name]["sole"][1]), (64, row_y + 38))
        alignment.paste(render(specimens[name], 3, meta[name]["sole"][1]), (576, row_y + 38))
    alignment.save(qa / "v02_alignment_comparison.png")
    # Same-window overlay is diagnostic; no motion interpolation implied.
    frames = []
    for name, label in LABELS.items():
        im = Image.new("RGB", (512, 580), "#243242")
        ImageDraw.Draw(im).text((15, 10), label + "（关键姿势轮播）", font=font(22), fill="white")
        im.paste(render(specimens[name], 4), (0, 56))
        frames.append(im)
    frames[0].save(qa / "pose_review.gif", save_all=True, append_images=frames[1:], duration=1000, loop=0, optimize=False)
    holdout_report = []
    holdout_path = qa / "holdout_annotations.json"
    if holdout_path.exists():
        holdouts = json.loads(holdout_path.read_text(encoding="utf-8"))
        for name, points in holdouts["poses"].items():
            reg = registrations[name]
            for label, point in points.items():
                matrix = reg.get("matrix_2x3", [[reg["scale_x"],0,reg["translation"][0]],[0,reg["scale_y"],reg["translation"][1]]])
                actual = [sum(matrix[j][k] * point["raw"][k] for k in (0,1)) + matrix[j][2] for j in (0,1)]
                residual = [actual[j] - point["target_native"][j] for j in (0, 1)]
                holdout_report.append(dict(name=name, landmark=label, actual_native=actual,
                                           target_native=point["target_native"], residual_native_px=residual,
                                           distance_native_px=math.hypot(*residual),
                                           caution="Manual visual annotation, about 1-2 native pixel uncertainty; not used for scale/translation fitting."))
    report = dict(provider="65535", model="gpt-image-2.5", task_count=len(raw_reports), chosen_master=chosen,
                  selected_actions=pose_selection, raw_files=raw_reports, real_alpha_pass=sum(r["real_alpha"] and r["transparent_corners"] for r in raw_reports),
                  clipped_count=sum(r["clipped"] for r in raw_reports),
                  observations=metrics, independent_landmark_checks=holdout_report, native_canvas_checks=native_checks,
                  observed_account_cost_delta=journal["observed_cost_delta"], unit=journal["usage_unit"],
                  reported_task_cost_total_usd=float(sum(Decimal(str(r["cost_usd"])) for r in receipts if r.get("cost_usd") is not None)),
                  cost_caution=journal["spending_note"], master_selection=selection,
                  native_window=list(WINDOW), native_window_size=[128, 128],
                  processing="Each provider result is scaled to native once. Inspection images are integer enlargements only. No forced palette reduction; strict-alpha candidate thresholds alpha at 128.",
                  animation_timing_certified=False, game_runtime_validated=False)
    save(qa / "validation_report.json", report)
    print(json.dumps({k:report[k] for k in ("task_count","chosen_master","real_alpha_pass","clipped_count","observed_account_cost_delta","unit")},ensure_ascii=False))


if __name__ == "__main__":
    main()
