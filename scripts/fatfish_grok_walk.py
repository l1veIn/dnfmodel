"""One durable 65535 Grok first-frame walk trial; never auto-resubmit."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops
from run_65535_samples import load_relay

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "design/fatfish/grok_walk_v01"
OUT = ROOT / "output/Fatfish_Grok_Walk_v01"
MASTER = ROOT / "design/fatfish/nearest_standing_v04/standing_canvas.png"
MASTER_SHA = "9879ff298f8ba3b5200d0ecd5edee248da34f588cc6fbe63694e75020f277446"
MODEL = "grok-imagine-video-1.5-preview"
PROMPT = """Animate the supplied first-frame image as a precise 2D game sprite walk-cycle test. The image is the approved character design, proportions, pixel-art style, outfit and fixed three-quarter view facing right. Preserve that exact character throughout: navy-to-cyan long wavy hair, curled ahoge, small whale-fin ears, white frilled maid headband, blue eyes, navy long-sleeved dress, white whale-emblem apron with gold trim, opaque white tights, navy Mary Jane shoes, and compact whale tail. Keep her face, head size, hair silhouette, costume colors and all accessories consistent.

The character walks IN PLACE at a steady moderate cadence, repeatedly alternating left and right legs through a complete natural gait. Clearly bend knees and ankles, lift each foot during swing, and show continuous connected arms and hands with small counter-swing. Each planted foot travels backward smoothly during support and returns forward only while lifted, like a treadmill walk. The head and torso remain almost fixed, with only tiny natural vertical bobbing; the pelvis does not drift across the canvas. Hair, skirt and tail follow with restrained secondary motion. Keep the same right-facing three-quarter orientation; never turn toward the camera.

Show approximately four evenly timed repetitions in four seconds. Continue the walk right to the end, reaching the starting gait phase for a clean repeat; do not pause to pose. Locked camera and scale, entire body and both shoes visible within the original margins, constant ground-contact height. Preserve the deliberately pixelated game-sprite appearance; no conversion to 3D, realistic rendering or smooth anime illustration. Background stays a perfectly flat uniform neutral gray RGB(128,128,128) with no floor, shadows, scenery, grid, text, effects, additional characters or camera movement. Silent clip, no speech."""


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def receipt(task):
    return {k: task[k] for k in ("id", "kind", "model", "operation", "status", "progress", "seconds", "size",
        "cost_usd", "error_code", "error_message", "created_at", "started_at", "finished_at", "expires_at") if k in task}


def prepare():
    if (RUN / "submission.json").exists():
        raise RuntimeError("Existing submission journal: preparation cannot reset a submitted trial")
    if sha(MASTER) != MASTER_SHA:
        raise ValueError("Approved master changed")
    reference = RUN / "input/master_gray_1024.png"
    reference.parent.mkdir(parents=True, exist_ok=True)
    crop = Image.open(MASTER).convert("RGBA").crop((186, 272, 314, 400))
    rgba = crop.resize((1024, 1024), Image.Resampling.NEAREST)
    rgb = Image.new("RGBA", rgba.size, (128, 128, 128, 255))
    rgb.alpha_composite(rgba)
    rgb.convert("RGB").save(reference)
    crop.save(RUN / "input/master_native_128_rgba.png")
    relay = load_relay()
    models = relay.http("GET", "/v1/models").get("data", [])
    prices = relay.http("GET", "/v1/pricing").get("data", [])
    model = next(x for x in models if x["id"] == MODEL)
    price = next(x for x in prices if x["id"] == MODEL)
    if not price.get("online"):
        raise RuntimeError("Selected model currently offline")
    save(RUN / "capabilities.json", {"checked_at": now(), "available_model": model, "pricing_entry": price,
        "sources": ["https://my.65535.space/api/docs/grok-video", "https://my.65535.space/api/docs/async-native-api",
                    "https://x.ai/news/grok-imagine-1-5", "https://docs.x.ai/developers/model-capabilities/video/image-to-video"],
        "selected_mode": "first_frame", "last_frame_support_verified": False, "original_pose_video_sent": False,
        "alpha_video_requested": False, "note": "Grok formal 1.5 examples do not establish preview-model last-frame support"})
    spec = {"name": "fatfish_grok_walk_v01", "created_at": now(), "provider": "65535", "model": MODEL,
        "max_generation_jobs": 1, "seconds": 4, "resolution": "720p", "aspect_ratio": "inherited square reference",
        "reference": str(reference), "reference_sha256": sha(reference), "master": str(MASTER), "master_sha256": MASTER_SHA,
        "reference_preparation": "Approved 128x128 window -> nearest 8x -> alpha-composite onto RGB128 gray; no generative image edits",
        "prompt": PROMPT, "motion_guidance": "Prompt only; no original motion video / hard pose control",
        "authorization": "User requested one 65535 Grok test; prior unrestricted spend authorization persists",
        "game_installation_changed": False, "batch_generation": False,
        "acceptance": ["same costume and face", "connected hands/arms", "stable leg widths", "alternating complete gait", "constant ground and scale", "inspect first-last seam"],
        "limitations": ["No verified hard last-frame constraint", "RGB background, not transparent video", "Original ANI timings and game root motion unverified"]}
    save(RUN / "spec.json", spec)
    save(RUN / "submission.json", {"state": "prepared", "created_at": now(), "idempotency_key": "fatfish-walk-" + str(uuid.uuid4())})
    print(json.dumps({"prepared": True, "reference": str(reference), "sha256": sha(reference), "model": MODEL, "seconds": 4}))


def submit():
    journal = json.loads((RUN / "submission.json").read_text("utf-8"))
    if journal["state"] != "prepared":
        raise RuntimeError("Refusing duplicate submission; use collect for the existing task")
    spec = json.loads((RUN / "spec.json").read_text("utf-8"))
    reference = Path(spec["reference"])
    if sha(reference) != spec["reference_sha256"] or sha(MASTER) != MASTER_SHA:
        raise ValueError("Input hash differs")
    relay = load_relay()
    data_uri = relay.to_data_uri(str(reference))
    decoded = base64.b64decode(data_uri.split(",", 1)[1], validate=True)
    if hashlib.sha256(decoded).hexdigest() != spec["reference_sha256"]:
        raise ValueError("Actual encoded reference bytes differ")
    body = {"kind": "video", "model": MODEL, "operation": "generate", "input": {
        "prompt": PROMPT, "seconds": 4, "resolution": "720p", "input_mode": "first_frame",
        "input_reference": {"image_url": data_uri}}}
    wire = json.dumps(body).encode("utf-8")
    audit = json.loads(json.dumps(body))
    audit["input"]["input_reference"]["image_url"] = {"transport": "PNG data URI", "local_path": str(reference),
        "decoded_bytes": len(decoded), "decoded_sha256": hashlib.sha256(decoded).hexdigest()}
    save(RUN / "request_audit.json", {"request": audit, "wire_sha256": hashlib.sha256(wire).hexdigest(),
        "wire_bytes": len(wire), "reference_encoded_and_verified": True})
    journal.update(state="launching", started_at=now())
    save(RUN / "submission.json", journal)
    request = urllib.request.Request(relay.BASE + "/v1/tasks", data=wire, method="POST", headers={
        "Authorization": "Bearer " + relay.load_key(), "Content-Type": "application/json",
        "Idempotency-Key": journal["idempotency_key"], "User-Agent": "fatfish-walk-trial/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            task = relay.unwrap(json.load(response))
    except urllib.error.HTTPError as e:
        message = e.read(1600).decode("utf-8", "replace")
        journal.update(state="submission_rejected", http_status=e.code, error_message=message, finished_at=now())
        save(RUN / "submission.json", journal)
        print(json.dumps({"submitted": False, "http_status": e.code, "error_message": message}, ensure_ascii=False))
        return
    if not task.get("id"):
        raise RuntimeError("No task ID; do not resubmit automatically")
    journal.update(state="submitted", task_id=task["id"], submitted_at=now())
    save(RUN / "submission.json", journal)
    save(RUN / "receipt.json", receipt(task))
    print(json.dumps({"submitted": True, "task_id": task["id"], "reference_bytes_verified": True}))


def collect(timeout):
    journal = json.loads((RUN / "submission.json").read_text("utf-8"))
    task_id = journal.get("task_id")
    if not task_id:
        raise RuntimeError("No known task ID; refusing to create a new job")
    relay = load_relay()
    deadline = time.monotonic() + timeout
    previous = None
    while True:
        task = relay.unwrap(relay.http("GET", "/v1/tasks/" + task_id))
        save(RUN / "receipt.json", receipt(task))
        state = task.get("status")
        if state != previous:
            print(json.dumps(receipt(task), ensure_ascii=False), flush=True)
            previous = state
        if state in ("done", "failed"):
            journal.update(state=state, collected_at=now())
            save(RUN / "submission.json", journal)
            break
        if state not in ("pending", "running"):
            raise RuntimeError("Unknown task status; saved receipt, no resubmission")
        if time.monotonic() >= deadline:
            print(json.dumps({"still_waiting_for_existing_task": task_id}), flush=True)
            return
        time.sleep(10)
    if state == "failed":
        print(json.dumps({"failed": True, "task_id": task_id, "error_code": task.get("error_code"),
                          "error_message": task.get("error_message")}, ensure_ascii=False))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    url = task.get("video_url") or next(iter(task.get("result_urls") or []), None)
    if not url:
        raise RuntimeError("Completed task has no video result URL")
    dest = OUT / "grok_walk_original.mp4"
    if not dest.exists():
        temp = dest.with_suffix(".mp4.part")
        req = urllib.request.Request(url, headers={"User-Agent": "fatfish-walk-trial/1.0"})
        with urllib.request.urlopen(req, timeout=180) as source, temp.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        temp.replace(dest)
    save(RUN / "download.json", {"task_id": task_id, "downloaded_at": now(), "path": str(dest), "bytes": dest.stat().st_size,
        "sha256": sha(dest), "url_host": urllib.parse.urlparse(url).netloc,
        "url_sha256": hashlib.sha256(url.encode()).hexdigest()})
    print(json.dumps({"completed": True, "task_id": task_id, "video": str(dest), "cost_usd": task.get("cost_usd")}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["prepare", "submit", "collect"])
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    if args.action == "prepare": prepare()
    elif args.action == "submit": submit()
    else: collect(args.timeout)
