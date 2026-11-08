"""Resumable ranged transfer; compare all bytes against the official HF LFS hashes."""
import concurrent.futures
import hashlib
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "design/fatfish/local_video_v01/models"
MODELS = Path(r"D:\VideoStudio\comfyUI\shared\models")
CACHE = Path(r"D:\VideoStudio\comfyUI\shared\wan_download\ranges")
TRANSPORT = "https://modelscope.cn"
CHUNK = 32 * 1024 * 1024
LOCK = threading.Lock()
STATE = {"completed_bytes": 0, "total_bytes": 0, "completed_chunks": 0}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def transfer(item, revision, start):
    end = min(start + CHUNK, item["size"]) - 1
    folder = CACHE / Path(item["path"]).name
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{start:012d}.chunk"
    expected_size = end - start + 1
    if not target.exists() or target.stat().st_size != expected_size:
        temporary = target.with_suffix(".partial")
        for attempt in range(4):
            try:
                url = f"{TRANSPORT}/models/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/master/{item['path']}?part={start}"
                request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{item['size']}":
                        raise ValueError("Incorrect byte range returned")
                    with temporary.open("wb") as f:
                        while data := response.read(1024 * 1024):
                            f.write(data)
                if temporary.stat().st_size != expected_size:
                    raise ValueError("Incomplete chunk")
                temporary.replace(target)
                break
            except Exception:
                if attempt == 3:
                    raise
        
    with LOCK:
        STATE["completed_bytes"] += expected_size
        STATE["completed_chunks"] += 1
    return str(target)


def main():
    metadata = json.loads((OUT / "source_metadata.json").read_text("utf-8"))
    items = metadata["files"]
    revision = metadata["revision"]
    started = time.monotonic()
    STATE["total_bytes"] = sum(x["size"] for x in items)
    receipts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(transfer, item, revision, start)
                   for start_index in range(max((x["size"] + CHUNK - 1) // CHUNK for x in items))
                   for item in items
                   if (start := start_index * CHUNK) < item["size"]]
        pending = set(futures)
        while pending:
            done, pending = concurrent.futures.wait(pending, timeout=20, return_when=concurrent.futures.FIRST_EXCEPTION)
            for future in done:
                future.result()
            with LOCK:
                state = dict(STATE)
            state.update(seconds=round(time.monotonic() - started, 1),
                         percent=round(state["completed_bytes"] / state["total_bytes"] * 100, 2))
            (OUT / "download_progress.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
            print(json.dumps(state), flush=True)
    for item in items:
        target = MODELS / Path(item["path"]).relative_to("split_files")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".safetensors.assembled")
        if not target.exists():
            with temporary.open("wb") as f:
                for start in range(0, item["size"], CHUNK):
                    chunk = CACHE / Path(item["path"]).name / f"{start:012d}.chunk"
                    with chunk.open("rb") as source:
                        for data in iter(lambda: source.read(8 * 1024 * 1024), b""):
                            f.write(data)
            if temporary.stat().st_size != item["size"] or digest(temporary) != item["lfs"]["oid"]:
                raise ValueError(f"Official SHA-256 verification failed: {target.name}")
            temporary.rename(target)
        actual = digest(target)
        if target.stat().st_size != item["size"] or actual != item["lfs"]["oid"]:
            raise ValueError(f"Existing target does not match official model: {target.name}")
        record = {"repository": "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "revision": revision,
                  "repository_path": item["path"], "transport": TRANSPORT,
                  "local_path": str(target), "bytes": item["size"], "sha256": actual,
                  "sha256_source": "Official huggingface.co repository LFS metadata"}
        receipts.append(record)
        (OUT / (target.name + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps({"file": target.name, "verified": True}), flush=True)
    (OUT / "verified_models.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")
    print(json.dumps({"complete": True, "seconds": round(time.monotonic() - started, 2)}), flush=True)


if __name__ == "__main__":
    main()
