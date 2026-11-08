"""One local Wan 2.2 I2V feasibility run, with lossless frames and resource sampling."""
import ctypes
import hashlib
import json
import shutil
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "design/fatfish/local_video_v01"
OUT = BASE / "lowmem_384"
DELIVERY = ROOT / "output/Fatfish_Local_Video_LowMem_v01"
SHARED = Path(r"D:\VideoStudio\comfyUI\shared")
API = "http://127.0.0.1:8188"
SEED = 20261022
UNET_NAME = "wan2.2_ti2v_5B_fp8_local_read.pt"
SAMPLER = "euler"
SIZE, FRAMES, STEPS, FPS = 384, 25, 12, 24
PREFIX = "fatfish_local_lowmem_v01"
POSITIVE = (
    "A single full-body 2D pixel art female whale maid game sprite, exactly the same character "
    "and costume as the reference image. She performs a short relaxed walk in place, facing "
    "three-quarter right throughout. Her slender legs alternate stepping forward and back, "
    "bending naturally at the knees, her feet lifting and touching down, her attached arms "
    "swing gently in opposition. Her navy to cyan wavy hair, white frilled maid headband, "
    "navy long-sleeved dress, white whale-emblem apron with gold trim, opaque white tights, "
    "navy Mary Jane shoes, and compact whale tail remain unchanged. Small controlled motion, "
    "stable body proportions and consistent face, full body always inside the frame. "
    "Static camera, unchanged character scale, unchanged uniform medium gray background, "
    "sprite animation, crisp pixel clusters."
)
NEGATIVE = (
    "camera movement, camera shake, zoom, pan, scene change, moving background, scenery, "
    "walking across the screen, turning around, spinning, facing away, running, jumping, "
    "large body deformation, different outfit, changing face, changing hair color, "
    "extra limbs, missing limbs, disconnected wrists, floating hands, extra fingers, "
    "merged legs, thick swollen legs, changing body size, cropping, blur, photorealism, "
    "3D rendering, text, watermark, particles, lighting changes"
)


def request(path, data=None):
    req = urllib.request.Request(API + path,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MemoryStatus(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong) for name in
        ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended")]


def monitor(stop, records):
    with (OUT / "resource_samples.jsonl").open("w", encoding="utf-8") as log:
        while not stop.is_set():
            result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu,power.draw",
                                     "--format=csv,noheader,nounits"], capture_output=True, text=True)
            memory = MemoryStatus()
            memory.length = ctypes.sizeof(memory)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
            record = {"utc": datetime.now(timezone.utc).isoformat(),
                      "system_ram_available_bytes": memory.avail_phys,
                      "system_commit_available_bytes": memory.avail_page}
            if result.returncode == 0:
                used, free, util, watts = [float(x.strip()) for x in result.stdout.strip().split(",")]
                record.update(gpu_used_mib=used, gpu_free_mib=free, gpu_util_percent=util, gpu_watts=watts)
            else:
                record["gpu_query_error"] = result.returncode
            records.append(record)
            log.write(json.dumps(record) + "\n")
            log.flush()
            reason = None
            if memory.avail_phys < 4 * 1024 ** 3 or memory.avail_page < 4 * 1024 ** 3:
                reason = "RAM or commit headroom below 4 GiB"
            elif "gpu_free_mib" in record and record["gpu_free_mib"] < 1536:
                reason = "GPU headroom below 1536 MiB"
            elif "gpu_query_error" in record:
                reason = "GPU telemetry failed"
            if reason:
                save(OUT / "memory_guard_triggered.json", {"reason": reason, "sample": record})
                request("/interrupt", {})
                return
            stop.wait(1)


def graph():
    return {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET_NAME, "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "56": {"class_type": "LoadImage", "inputs": {"image": f"{PREFIX}_master_gray_{SIZE}.png"}},
        "55": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["39", 0], "start_image": ["56", 0], "width": SIZE, "height": SIZE, "length": FRAMES, "batch_size": 1}},
        "48": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["37", 0], "shift": 8.0}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": POSITIVE}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": NEGATIVE}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["48", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["55", 0], "seed": SEED, "steps": STEPS, "cfg": 5.0, "sampler_name": SAMPLER, "scheduler": "simple", "denoise": 1.0}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "60": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": f"{PREFIX}/walk_seed{SEED}"}},
    }


def collect(history, records, elapsed):
    (DELIVERY / "frames_full").mkdir(parents=True, exist_ok=True)
    (DELIVERY / "frames_native_128").mkdir(exist_ok=True)
    entries = history["outputs"]["60"]["images"]
    if len(entries) != FRAMES:
        raise ValueError(f"Expected {FRAMES} frames, got {len(entries)}")
    full, native, hashes = [], [], []
    for index, entry in enumerate(entries):
        source = SHARED / entry["type"] / entry["subfolder"] / entry["filename"]
        image = Image.open(source).convert("RGB")
        if image.size != (SIZE, SIZE):
            raise ValueError(f"Unexpected image size {image.size}")
        target = DELIVERY / "frames_full" / f"{index:04d}.png"
        shutil.copy2(source, target)
        small = image.resize((128, 128), Image.Resampling.NEAREST)
        small.save(DELIVERY / "frames_native_128" / f"{index:04d}.png")
        full.append(image)
        native.append(small)
        hashes.append(sha256(target))
    for folder, name in [("frames_full", "walk_full.mp4"), ("frames_native_128", "walk_native_128.mp4")]:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS),
                        "-i", str(DELIVERY / folder / "%04d.png"), "-c:v", "libx264", "-crf", "16",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(DELIVERY / name)], check=True)
    native[0].save(DELIVERY / "walk_native_lossless.png", save_all=True, append_images=native[1:],
                   duration=1000 / FPS, loop=0, disposal=0, blend=0)
    indices = list(range(0, FRAMES, 3))
    sheet = Image.new("RGB", (128 * len(indices), 154), "#26323e")
    draw = ImageDraw.Draw(sheet)
    for column, index in enumerate(indices):
        sheet.paste(native[index], (column * 128, 26))
        draw.text((column * 128 + 6, 7), f"Frame {index:02d}", fill="white")
    sheet.save(DELIVERY / "contact_sheet.png")
    shutil.copy2(OUT / f"input/fatfish_master_gray_{SIZE}.png", DELIVERY / "input_master.png")
    timestamps = {kind: data["timestamp"] for kind, data in history["status"]["messages"]
                  if "timestamp" in data}
    server_seconds = (timestamps["execution_success"] - timestamps["execution_start"]) / 1000
    metrics = {"elapsed_seconds": server_seconds, "client_observed_elapsed_seconds": round(elapsed, 2),
               "frames": len(full), "dimensions": [SIZE, SIZE], "steps": STEPS,
               "model_weight_dtype": "FP8 e4m3fn", "sampler": SAMPLER,
               "fps": FPS, "duration_seconds": FRAMES / FPS, "unique_png_files": len(set(hashes)),
               "peak_gpu_used_mib_sampled": max(r["gpu_used_mib"] for r in records if "gpu_used_mib" in r),
               "gpu_query_failures": sum("gpu_query_error" in r for r in records),
               "min_system_ram_available_gib_sampled": min(r["system_ram_available_bytes"] for r in records) / 1024 ** 3,
               "monitor_interval_seconds": 1, "alpha_output": False, "seed": SEED,
               "min_commit_available_gib_sampled": min(r["system_commit_available_bytes"] for r in records) / 1024 ** 3,
               "lossless_frame_sha256": hashes, "game_ready": False}
    save(OUT / "run_metrics.json", metrics)
    save(DELIVERY / "run_metrics.json", metrics)
    return metrics


def main():
    (OUT / "input").mkdir(parents=True, exist_ok=True)
    master = Image.open(BASE / "input/master_native_128.png").convert("RGBA").resize((SIZE, SIZE), Image.Resampling.NEAREST)
    background = Image.new("RGBA", master.size, (128, 128, 128, 255))
    background.alpha_composite(master)
    background.convert("RGB").save(OUT / f"input/fatfish_master_gray_{SIZE}.png")
    if not (BASE / "models/verified_models.json").exists():
        raise RuntimeError("Download and verify models first")
    conversion = json.loads((BASE / "models/lowmem_fp8_conversion.json").read_text("utf-8"))
    if not conversion["readback_passed"] or conversion["verified_tensor_count"] != 825:
        raise RuntimeError("Local model container has not passed tensor verification")
    if (OUT / "submission.json").exists():
        raise RuntimeError("This run was already submitted; inspect its saved prompt ID instead of submitting again")
    queue = request("/queue")
    if queue["queue_running"] or queue["queue_pending"]:
        raise RuntimeError("Existing ComfyUI jobs are active; leave them undisturbed")
    source = OUT / f"input/fatfish_master_gray_{SIZE}.png"
    target = SHARED / f"input/{PREFIX}_master_gray_{SIZE}.png"
    if target.exists() and sha256(target) != sha256(source):
        raise ValueError("Input name collision")
    shutil.copy2(source, target)
    prompt = graph()
    save(OUT / "workflow_api.json", prompt)
    save(OUT / "prompts.json", {"positive": POSITIVE, "negative": NEGATIVE, "seed": SEED})
    workflow = json.loads((BASE / "official_template.json").read_text("utf-8"))
    for node in workflow["nodes"]:
        if node["id"] == 37:
            node["widgets_values"] = [UNET_NAME, "default"]
        elif node["id"] == 56:
            node["mode"] = 0
            node["widgets_values"] = [target.name, "image"]
        elif node["id"] == 55:
            node["widgets_values"] = [SIZE, SIZE, FRAMES, 1]
        elif node["id"] == 6:
            node["widgets_values"] = [POSITIVE]
        elif node["id"] == 7:
            node["widgets_values"] = [NEGATIVE]
        elif node["id"] == 3:
            node["widgets_values"] = [SEED, "fixed", STEPS, 5, SAMPLER, "simple", 1]
        elif node["id"] == 58:
            node["widgets_values"] = [f"{PREFIX}/walk_gui", "auto", "auto"]
        if node["id"] == 8:
            node["outputs"][0]["links"].append(109)
    workflow["nodes"].append({"id": 60, "type": "SaveImage", "pos": [1750, 650],
                              "size": [400, 420], "flags": {}, "order": 13, "mode": 0,
                              "inputs": [{"name": "images", "type": "IMAGE", "link": 109}],
                              "outputs": [], "properties": {"Node name for S&R": "SaveImage"},
                              "widgets_values": [f"{PREFIX}/walk_seed{SEED}"]})
    workflow["links"].append([109, 8, 0, 60, 0, "IMAGE"])
    workflow["last_node_id"] = 60
    workflow["last_link_id"] = 109
    save(OUT / "workflow_ui.json", workflow)
    environment = request("/system_stats")
    save(OUT / "environment.json", environment)
    if environment["system"]["ram_free"] < 10 * 1024 ** 3 or environment["devices"][0]["vram_free"] < 8 * 1024 ** 3:
        raise RuntimeError("Preflight headroom is too low: require 10 GiB RAM and 8 GiB VRAM free")
    save(OUT / "spec.json", {"size": SIZE, "frames": FRAMES, "fps": FPS, "steps": STEPS,
                            "sampler": SAMPLER, "unet": UNET_NAME, "input_sha256": sha256(source),
                            "resize": "128 to 384 NEAREST", "batch_size": 1,
                            "memory_guard": {"min_ram_free_gib": 4, "min_commit_free_gib": 4,
                                             "min_gpu_free_mib": 1536, "sample_interval_seconds": 1}})
    started = time.monotonic()
    records = []
    stop = threading.Event()
    worker = threading.Thread(target=monitor, args=(stop, records), daemon=True)
    worker.start()
    try:
        submission = request("/prompt", {"prompt": prompt, "client_id": "fatfish-local-video-v01"})
        save(OUT / "submission.json", submission)
        print(json.dumps({"submitted": submission}), flush=True)
        prompt_id = submission["prompt_id"]
        while True:
            response = request("/history/" + prompt_id)
            if prompt_id in response:
                history = response[prompt_id]
                save(OUT / "history.json", history)
                if history["status"]["status_str"] != "success":
                    raise RuntimeError("ComfyUI execution failed; see history.json and comfy_stderr.log")
                break
            progress = request("/queue")
            print(json.dumps({"elapsed_seconds": round(time.monotonic() - started),
                              "running_jobs": len(progress["queue_running"]),
                              "gpu_used_mib": records[-1].get("gpu_used_mib") if records else None}), flush=True)
            time.sleep(15)
    finally:
        stop.set()
        worker.join(timeout=5)
    elapsed = time.monotonic() - started
    metrics = collect(history, records, elapsed)
    print(json.dumps({"complete": True, "metrics": metrics}), flush=True)


if __name__ == "__main__":
    main()
