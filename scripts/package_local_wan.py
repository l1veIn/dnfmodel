"""Verify the successful small trial and package its frames, workflow and provenance."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "design/fatfish/local_video_v01"
RUN = BASE / "lowmem_384"
OUT = ROOT / "output/Fatfish_Local_Video_LowMem_v01"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    metrics = json.loads((RUN / "run_metrics.json").read_text("utf-8"))
    full = [Image.open(OUT / "frames_full" / f"{i:04d}.png").convert("RGB") for i in range(25)]
    native = [Image.open(OUT / "frames_native_128" / f"{i:04d}.png").convert("RGB") for i in range(25)]
    for i, (big, small) in enumerate(zip(full, native)):
        if big.size != (384, 384) or small.size != (128, 128):
            raise ValueError("Unexpected frame dimensions")
        if ImageChops.difference(big.resize((128, 128), Image.Resampling.NEAREST), small).getbbox():
            raise ValueError(f"Native frame {i} differs from exact NEAREST output")
        if digest(OUT / "frames_full" / f"{i:04d}.png") != metrics["lossless_frame_sha256"][i]:
            raise ValueError(f"Original frame {i} hash differs")
    durations = [round((i + 1) * 1000 / 24) - round(i * 1000 / 24) for i in range(25)]
    for name, images in [("walk_native_lossless.png", native),
                         ("walk_native_3x.png", [im.resize((384, 384), Image.Resampling.NEAREST) for im in native])]:
        images[0].save(OUT / name, save_all=True, append_images=images[1:], duration=durations,
                       loop=0, disposal=0, blend=0)
        result = Image.open(OUT / name)
        if result.n_frames != 25:
            raise ValueError(f"Unexpected APNG frame count: {result.n_frames}")
        for i, expected in enumerate(images):
            result.seek(i)
            if ImageChops.difference(result.convert("RGB"), expected).getbbox():
                raise ValueError(f"APNG readback failed at {name}, frame {i}")
    video = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                                "-show_entries", "stream=width,height,nb_frames,r_frame_rate,duration",
                                                "-of", "json", str(OUT / "walk_full.mp4")]))["streams"][0]
    if (video["width"], video["height"], int(video["nb_frames"]), video["r_frame_rate"]) != (384, 384, 25, "24/1"):
        raise ValueError("Encoded video does not match source timing/dimensions")
    (OUT / "evidence").mkdir(exist_ok=True)
    for name in ["workflow_api.json", "workflow_ui.json", "prompts.json", "spec.json", "submission.json",
                 "history.json", "environment.json", "resource_samples.jsonl", "browser_check.json"]:
        shutil.copy2(RUN / name, OUT / "evidence" / name)
    for name in ["verified_models.json", "source_metadata.json", "lowmem_fp8_conversion.json"]:
        shutil.copy2(BASE / "models" / name, OUT / "evidence" / name)
    shutil.copy2(ROOT / "design/fatfish/references/UPSTREAM_CREDITS.md", OUT / "evidence/UPSTREAM_CREDITS.md")
    report = {"result": "One completed local feasibility video, not a game patch",
              "successful_prompt_id": json.loads((RUN / "submission.json").read_text())["prompt_id"],
              "metrics": metrics, "validation": {"source_png_sha256": True,
                  "native_nearest_pixel_readback": True, "apng_pixel_readback": True, "ffprobe": video,
                  "memory_guard_triggered": (RUN / "memory_guard_triggered.json").exists()},
              "visual_review": {"character_identity": "Broad silhouette, colors and costume retained",
                  "motion": "Small stepping/weight shift; not a full walk cycle",
                  "issues": ["Leg/shoe and apron/hem details vary", "First/last poses are not matched",
                             "Gray RGB background, no alpha", "No DNF ANI timing/anchor adaptation"]},
              "attempt_history": "Six preceding FP16 startup/solver/interruption attempts saved in design/fatfish/local_video_v01/attempts",
              "previous_system_events": "22:30 app crash and NVIDIA event observed; causal relationship unconfirmed",
              "source_files_changed": False, "game_installation_changed": False, "paid_api_used": False,
              "next_step": "Review the small clip before any increased resolution, length or batch; motion controls still needed",
              "memory_guard_limits": "Interrupts at execution boundaries; reserve-vram is not a hard cap and one-second telemetry can miss shorter peaks",
              "technical_sources": ["https://docs.comfy.org/tutorials/video/wan/wan2_2",
                  "https://github.com/Comfy-Org/ComfyUI/issues/15255",
                  "https://github.com/Comfy-Org/ComfyUI/issues/14250"]}
    save(OUT / "review_report.json", report)
    save(RUN / "review_report.json", report)
    state = json.loads((ROOT / "preparation_status.json").read_text("utf-8"))
    state["local_video"] = {"status": "One small FP8 local video completed; no batch",
        "location": str(RUN.relative_to(ROOT)), "preview": str((OUT / "preview.html").relative_to(ROOT)),
        "preview_url": "http://127.0.0.1:8786/preview.html", "model": "Wan2.2 TI2V 5B FP8 unscaled cast",
        "size": [384, 384], "frames": 25, "fps": 24, "elapsed_seconds": metrics["elapsed_seconds"],
        "peak_gpu_used_mib_sampled": metrics["peak_gpu_used_mib_sampled"],
        "min_ram_free_gib_sampled": metrics["min_system_ram_available_gib_sampled"],
        "alpha": False, "game_ready": False, "game_installation_changed": False}
    (ROOT / "preparation_status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = ROOT / "README.md"
    text = readme.read_text("utf-8")
    marker = "本地视频首次试跑已完成"
    if marker not in text:
        text += ("\n\n本地视频首次试跑已完成：复用 D 盘 ComfyUI，在 RTX 4070 SUPER 上使用 Wan2.2 TI2V 5B 的本地 FP8 权重，"
                 "生成 384×384、25 帧、24fps 的灰底片段，首次推理约 11.6 秒。1 秒采样的显存峰值为 10.17GiB，"
                 "系统内存最低剩余 12.49GiB。预览为 `output/Fatfish_Local_Video_LowMem_v01/preview.html`，"
                 "工作流副本为 `D:/VideoStudio/comfyUI/workflows/fatfish_walk_lowmem_v01.json`，"
                 "启动配置为 `D:/VideoStudio/comfyUI/start-fatfish-lowmem.bat`。原始 PNG、最近邻 128×128 PNG、"
                 "无损 APNG、MP4 和参数/内存记录已保留；动作偏小、脚部/裙摆仍变化，未抠透明或做 ANI/锚点适配，尚不能接入游戏。"
                 "此前大样在加载、采样兼容性和应用/驱动退出时中止，日志均保留；没有继续批量生成。\n")
        readme.write_text(text, encoding="utf-8")
    hashes = {str(path.relative_to(OUT)).replace("\\", "/"): digest(path)
              for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "SHA256.json"}
    save(OUT / "SHA256.json", hashes)
    bundle = ROOT / "output/fatfish_local_video_lowmem_v01.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                z.write(path, str(path.relative_to(OUT.parent)))
    with zipfile.ZipFile(bundle) as z:
        if z.testzip() is not None:
            raise ValueError("ZIP CRC failed")
    print(json.dumps({"verified": True, "frames": 25, "bundle": str(bundle),
                      "bundle_bytes": bundle.stat().st_size, "bundle_sha256": digest(bundle)}))


if __name__ == "__main__":
    main()
