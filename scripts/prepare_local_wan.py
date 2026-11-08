"""Download the three official Wan 2.2 5B artifacts and prepare the approved input."""
import concurrent.futures
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "design/fatfish/local_video_v01"
MODELS = Path(r"D:\VideoStudio\comfyUI\shared\models")
REPO = "Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
WANTED = {
    "wan2.2_ti2v_5B_fp16.safetensors",
    "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "wan2.2_vae.safetensors",
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(item, revision):
    relative = Path(item["path"]).relative_to("split_files")
    target = MODELS / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = item["lfs"]["oid"]
    size = item["size"]
    part = target.with_suffix(target.suffix + ".part")
    started = time.monotonic()
    if not target.exists():
        for attempt in range(3):
            have = part.stat().st_size if part.exists() else 0
            if have == size:
                break
            url = f"https://huggingface.co/{REPO}/resolve/{revision}/{item['path']}?download=true"
            request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    append = have > 0 and response.status == 206
                    if not append:
                        have = 0
                    last = time.monotonic()
                    with part.open("ab" if append else "wb") as f:
                        while chunk := response.read(4 * 1024 * 1024):
                            f.write(chunk)
                            have += len(chunk)
                            now = time.monotonic()
                            if now - last >= 20:
                                print(json.dumps({"file": target.name, "bytes": have, "total": size,
                                                  "percent": round(have / size * 100, 1)}), flush=True)
                                last = now
                if part.stat().st_size == size:
                    break
            except Exception as exc:
                print(json.dumps({"file": target.name, "attempt": attempt + 1,
                                  "error": type(exc).__name__}), flush=True)
                if attempt == 2:
                    raise
        if part.stat().st_size != size or sha256(part) != expected:
            raise ValueError(f"Model size/hash mismatch: {part.name}")
        part.rename(target)
    actual = sha256(target)
    if target.stat().st_size != size or actual != expected:
        raise ValueError(f"Existing model size/hash mismatch: {target.name}")
    record = {"repository": REPO, "revision": revision, "repository_path": item["path"],
              "local_path": str(target), "bytes": size, "sha256": actual,
              "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "elapsed_seconds": round(time.monotonic() - started, 2)}
    (OUT / "models" / (target.name + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"file": target.name, "verified": True, "seconds": record["elapsed_seconds"]}), flush=True)
    return record


def main():
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    (OUT / "input").mkdir(exist_ok=True)
    source = ROOT / "design/fatfish/nearest_standing_v04/standing_canvas.png"
    master = Image.open(source).convert("RGBA")
    crop = master.crop((186, 272, 314, 400))
    crop.save(OUT / "input/master_native_128.png")
    enlarged = crop.resize((512, 512), Image.Resampling.NEAREST)
    enlarged.save(OUT / "input/master_512_rgba.png")
    background = Image.new("RGBA", enlarged.size, (128, 128, 128, 255))
    background.alpha_composite(enlarged)
    background.convert("RGB").save(OUT / "input/fatfish_master_gray_512.png")
    spec = {"master": str(source), "master_sha256": sha256(source),
            "crop_window": [186, 272, 314, 400], "native_size": [128, 128],
            "input_size": [512, 512], "resize": "NEAREST", "background_rgb": [128, 128, 128],
            "input_sha256": sha256(OUT / "input/fatfish_master_gray_512.png"),
            "generation": "Wan2.2 TI2V 5B native ComfyUI image-to-video; initial frame only",
            "frames": 49, "fps": 24, "batch": 1, "alpha_output": False,
            "goal": "Local runtime and short in-place walking motion/identity feasibility; not a DNF patch"}
    (OUT / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{REPO}", timeout=30) as response:
        revision = json.load(response)["sha"]
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{REPO}/tree/{revision}/split_files?recursive=true&expand=false", timeout=30) as response:
        items = [x for x in json.load(response) if Path(x["path"]).name in WANTED]
    if len(items) != 3:
        raise ValueError("Official model list changed")
    (OUT / "models/source_metadata.json").write_text(json.dumps({"revision": revision, "files": items}, indent=2), encoding="utf-8")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch, item, revision) for item in items]
        receipts = [f.result() for f in futures]
    (OUT / "models/verified_models.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
