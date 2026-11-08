"""Cut-ins from Grok first-frame videos. Each submit is journaled and never repeated automatically.

    python scripts/gunner_cutin_video.py submit <name> <key> <seconds> <resolution> [attempt]
    python scripts/gunner_cutin_video.py collect <name> [attempt]
    python scripts/gunner_cutin_video.py cut <name> [attempt]
    python scripts/gunner_cutin_video.py run <attempt> <name:key:seconds> ...    submit and collect several in parallel

The first frame fills the whole 16:9 canvas (the key frame on magenta), so the video's edges are the screen's edges.
Writes only to output/gunner_cutin_video. Key frames come from output/gunner_cutin/<name>/raw.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import av
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gunner_cutins_all import BASE, CUTS, layout, official  # noqa: E402
from gunner_props import cut_key  # noqa: E402
from run_65535_samples import load_relay  # noqa: E402

OUT = ROOT / "output/gunner_cutin_video"
MODEL = "grok-imagine-video-1.5-preview"
BACK = (70, 78, 98)
KEY = (255, 0, 255)
STEMS = {"launcher_neo": "atgunner_launcher_neo", "spitfire_neo": "atgunner_spitfire_neo", "mechanic_neo": "atgunner_mechanic_neo", "ranger_neo": "atgunner_ranger_neo", "paramedic_neo": "atgunner_paramedic_neo"}
KEEP = "Preserve her exact face, her very long straight orange hair, the orange flower ornament with the black ribbon, and every part of her costume with its colors in every frame. Polished anime cel shading with clean even dark outlines, the same as the first frame. Wherever the first frame shows flat magenta, the background stays a perfectly flat uniform magenta, RGB 255 0 255, for the whole clip, with no shadow, scenery or particles on it. One continuous shot with no cuts. All motion is smooth, continuous and fluid, with no sudden jumps. No text. Silent."
PROMPTS = {
    "mechanic_neo": "A calm, thoughtful moment. The camera stays locked, with no zoom and no pan, so she stays the same size in the frame. She slowly raises her gaze from looking down to looking toward the viewer with a composed, knowing expression, blinking once. Her fingers shift slightly at her chin. Loose strands of hair, the ribbon tails and the earring tassel sway gently, as if in a light breeze.",
    "launcher_neo": "A dramatic hero shot. It starts as an extreme close-up of her determined face, framed by a huge cream ceramic and near-black fictional science-fiction exo-rig with long cylindrical barrels and rocket pods with clay orange lights. The camera pulls back smoothly and steadily until she is seen small and whole in the middle of the frame, standing inside the rig with its long barrels spread out on both sides. At the very end the barrels glow and release bright clay orange energy bursts. Her hair and ribbons stream in the wind.",
    "spitfire_neo": "She flies fast through the air toward the camera, with small fictional thruster boots and sharp cream and near-black fin blades on her back. The camera follows her smoothly; she swoops close past the camera, turning her face toward the viewer for a moment, then dives away diagonally and becomes small again. Her very long orange hair streams behind her and her long dress flows around her legs, modest and elegant.",
    "ranger_neo": "A fast, elegant motion seen close up. She lifts her head with a sharp, focused look, her long orange hair swinging across her face, then dashes forward to the right with a sweeping turn so that her capelet, dress and gold-trimmed ribbons sweep through the frame, and she leaves the frame at the right edge. The camera holds steady.",
    "paramedic_neo": "An intense extreme close-up of her face. Her eyes close slowly and then open with a calm, resolute gaze. Her long orange hair blows strongly in the wind and thin wisps of pale warm gray steam drift beside her face. At the end the camera pulls back quickly and she recedes and drops away toward the bottom of the frame.",
}


def folder(name, attempt):
    path = OUT / name / f"attempt_{int(attempt):02d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=1), "utf-8")
    temp.replace(path)


def receipt(task):
    return {k: task.get(k) for k in ("id", "model", "status", "progress", "seconds", "size", "cost_usd", "error_code", "error_message", "created_at", "finished_at")}


def latest_key(name, key):
    files = sorted((BASE / name / "raw").glob(f"key{int(key):02d}_v*_0.png"), key=lambda p: int(p.stem.split("_v")[1].split("_")[0]))
    return files[-1]


def first_frame(name, key, target, height=1080):
    """The key frame placed on the whole canvas, at the height the video will have."""
    pages, canvas = official(STEMS[name])
    plan = layout(pages)
    box = plan["box"]
    scale = height / canvas[1]
    width = round(canvas[0] * scale)
    art = Image.open(latest_key(name, key)).convert("RGB")
    # The key art covers the sheet board; one board pixel is 1/zoom canvas pixels.
    board_px = art.width / plan["board"][0]
    size = (round(plan["board"][0] / plan["zoom"] * scale), round(plan["board"][1] / plan["zoom"] * scale))
    origin = (round((box[0] - plan["ox"] / plan["zoom"]) * scale), round((box[1] - plan["oy"] / plan["zoom"]) * scale))
    # Pad with the key art's own magenta: a slightly different one would leave a visible band.
    corners = np.asarray(art)[[0, 0, -1, -1], [0, -1, 0, -1]]
    page = Image.new("RGB", (width, height), tuple(int(v) for v in np.median(corners, axis=0)))
    page.paste(art.resize(size, Image.LANCZOS), origin)
    page.save(target, optimize=True)
    return target, board_px


def submit(name, key, seconds, resolution, attempt=1):
    work = folder(name, attempt)
    journal = work / "journal.json"
    if journal.exists():
        return f"{name}: journal exists; collect instead"
    first, _ = first_frame(name, key, work / "first_frame.png")
    relay = load_relay()
    prompt = PROMPTS[name] + " " + KEEP
    body = {"kind": "video", "model": MODEL, "operation": "generate", "input": {"prompt": prompt, "seconds": int(seconds), "resolution": resolution, "input_mode": "first_frame", "input_reference": {"image_url": relay.to_data_uri(str(first))}}}
    idempotency = uuid.uuid4().hex
    save(journal, dict(state="launching", name=name, key=key, seconds=int(seconds), resolution=resolution, model=MODEL, prompt=prompt, idempotency=idempotency, started=time.time()))
    request = urllib.request.Request(relay.BASE + "/v1/tasks", data=json.dumps(body).encode("utf-8"), method="POST", headers={"Authorization": "Bearer " + relay.load_key(), "Content-Type": "application/json", "Idempotency-Key": idempotency, "User-Agent": "dnf-cutin-trial/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            task = relay.unwrap(json.load(response))
    except urllib.error.HTTPError as error:
        message = error.read(1200).decode("utf-8", "replace")
        save(journal, {**json.loads(journal.read_text("utf-8")), "state": "rejected", "http": error.code, "error": message})
        return f"{name}: rejected {error.code}: {message[:200]}"
    save(journal, {**json.loads(journal.read_text("utf-8")), "state": "submitted", "task_id": task["id"]})
    return f"{name}: submitted {task['id']}"


def collect(name, attempt=1, wait=560):
    work = folder(name, attempt)
    data = json.loads((work / "journal.json").read_text("utf-8"))
    if "task_id" not in data:
        return f"{name}: no task id ({data.get('state')})"
    relay = load_relay()
    deadline = time.monotonic() + wait
    while True:
        task = relay.unwrap(relay.http("GET", "/v1/tasks/" + data["task_id"]))
        save(work / "receipt.json", receipt(task))
        if task.get("status") in ("done", "failed"):
            break
        if time.monotonic() > deadline:
            return f"{name}: still running; collect again, do not resubmit"
        time.sleep(8)
    if task["status"] == "failed":
        return f"{name}: failed {task.get('error_code')} {task.get('error_message')} cost {task.get('cost_usd')}"
    url = task.get("video_url") or next(iter(task.get("result_urls") or []))
    target = work / "video.mp4"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "dnf-cutin-trial/1.0"}), timeout=240) as source:
        target.write_bytes(source.read())
    return f"{name}: done {task.get('size')} {task.get('seconds')}s cost {task.get('cost_usd')}"


def decode(path):
    with av.open(str(path)) as box:
        stream = box.streams.video[0]
        frames = [f.to_image().convert("RGB") for f in box.decode(stream)]
        print("video", frames[0].size, len(frames), "frames", float(stream.average_rate), "fps")
    return frames


def cut(name, attempt=1):
    work = folder(name, attempt)
    pages, canvas = official(STEMS[name])
    video = decode(work / "video.mp4")
    count = len(pages)
    picks = [round(i * (len(video) - 1) / (count - 1)) for i in range(count)]
    out = work / "frames"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    scratch = work / "_key.png"
    made, change, edges = [], [], []
    for i, k in enumerate(picks):
        video[k].save(scratch)
        page = cut_key(scratch).resize(canvas, Image.LANCZOS)
        page.save(out / f"{i:02d}.png")
        a = np.asarray(page)[..., 3] > 128
        if made:
            change.append(float((a ^ made[-1]).sum() / max(a.sum(), 1)))
        made.append(a)
    scratch.unlink()
    print(name, "sampled", count, "of", len(video), "outline change mean", round(float(np.mean(change)), 4), "worst", round(max(change), 4), "at", int(np.argmax(change)) + 1)
    pink = 0
    for i in range(count):
        p = np.asarray(Image.open(out / f"{i:02d}.png").convert("RGBA"), np.int32)
        seen = p[..., 3] > 128
        pink = max(pink, int((seen & (p[..., 0] > 170) & (p[..., 2] > 150) & (p[..., 1] < p[..., 2] - 45)).sum()))
    print(name, "worst frame pink pixels on figure", pink)
    cols, cell = 8, (200, 112)
    rows = (count + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1] * 2), BACK)
    for i in range(count):
        for r, item in enumerate((pages[i], Image.open(out / f"{i:02d}.png").convert("RGBA"))):
            small = item.resize(cell, Image.LANCZOS)
            sheet.paste(small, ((i % cols) * cell[0], (i // cols) * cell[1] * 2 + r * cell[1]), small)
    sheet.save(work / "frames.jpg", quality=88)
    size = (534, 300)
    frames = []
    for i in range(count):
        page = Image.new("RGB", (size[0] * 2 + 8, size[1]), (32, 36, 46))
        for col, item in enumerate((pages[i], Image.open(out / f"{i:02d}.png").convert("RGBA"))):
            cell_page = Image.new("RGB", canvas, BACK)
            cell_page.paste(item, (0, 0), item)
            page.paste(cell_page.resize(size, Image.LANCZOS), (col * (size[0] + 8), 0))
        frames.append(page.quantize(200))
    frames[0].save(work / "compare.gif", save_all=True, append_images=frames[1:], duration=100, loop=0, optimize=True)
    print(work / "frames.jpg")


def run(attempt, specs):
    jobs = [s.split(":") for s in specs]
    for name, key, seconds in jobs:
        print(submit(name, key, seconds, "1080p", attempt), flush=True)
    with ThreadPoolExecutor(len(jobs)) as pool:
        for result in pool.map(lambda j: collect(j[0], attempt), jobs):
            print(result, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    command = sys.argv[1]
    if command == "submit":
        print(submit(*sys.argv[2:]))
    elif command == "collect":
        print(collect(*sys.argv[2:]))
    elif command == "cut":
        cut(*sys.argv[2:])
    elif command == "run":
        run(sys.argv[2], sys.argv[3:])
