"""Fetch only the small official VACE backbone and its Wan 2.1 VAE."""
import concurrent.futures
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "design/fatfish/local_walk_control_v01/models"
MODELS = Path(r"D:\VideoStudio\comfyUI\shared\models")
REPO = "Comfy-Org/Wan_2.1_ComfyUI_repackaged"
NAMES = {"wan2.1_vace_1.3B_fp16.safetensors", "wan_2.1_vae.safetensors"}
CHUNK = 32 * 1024 * 1024


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.load(urllib.request.urlopen(f"https://huggingface.co/api/models/{REPO}/tree/main/split_files?recursive=true&expand=false", timeout=30))
    items = [x for x in meta if Path(x["path"]).name in NAMES]
    if len(items) != 2:
        raise ValueError("Official artifact list differs")
    (OUT / "official_metadata.json").write_text(json.dumps(items, indent=2), encoding="utf-8")
    for item in items:
        target = MODELS / Path(item["path"]).relative_to("split_files")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".safetensors.vace_download")
        if not target.exists():
            if not temporary.exists():
                with temporary.open("wb") as f:
                    f.truncate(item["size"])
            def chunk(start):
                end = min(start + CHUNK, item["size"]) - 1
                url = f"https://modelscope.cn/models/{REPO}/resolve/master/{item['path']}?part={start}"
                req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(req, timeout=60) as response:
                    if response.headers.get("Content-Range") != f"bytes {start}-{end}/{item['size']}":
                        raise ValueError("Incorrect range")
                    data = response.read()
                if len(data) != end - start + 1:
                    raise ValueError("Incomplete range")
                with temporary.open("r+b") as f:
                    f.seek(start)
                    f.write(data)
                return len(data)
            completed = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                jobs = [pool.submit(chunk, start) for start in range(0, item["size"], CHUNK)]
                for job in concurrent.futures.as_completed(jobs):
                    completed += job.result()
                    if completed // (512 * 1024 * 1024) != (completed - CHUNK) // (512 * 1024 * 1024):
                        print(json.dumps({"file": target.name, "downloaded": completed, "total": item["size"]}), flush=True)
            if sha(temporary) != item["lfs"]["oid"]:
                raise ValueError("Official SHA-256 mismatch")
            temporary.rename(target)
        if target.stat().st_size != item["size"] or sha(target) != item["lfs"]["oid"]:
            raise ValueError("Existing model does not match")
        receipt = {"repository": REPO, "file": item["path"], "local_path": str(target),
                   "bytes": item["size"], "sha256": item["lfs"]["oid"], "verified": True,
                   "transport": "Official Comfy-Org ModelScope mirror"}
        (OUT / (target.name + ".json")).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
