"""H3 video jobs, one per clip without a sheet. Use for big acrobatic motion, where flaring cloth is the point and hands matter less.

H3 draws her at the master's size whatever size the reference shows, so the window must fit the figure tightly. Clips that travel far
use a following camera; the shift returns when the frame is placed. Local and free, about 5.5 minutes a clip, needs 18.4 GiB free commit.
"""
from __future__ import annotations

import copy
import json
import shutil
import time
import uuid

import numpy as np
from PIL import Image

from .config import ROOT, P
from .source import native_world

SIDE = 512
MARGIN = tuple(P.data.get("video_margin", (42, 12, 28, 8)))  # left, top, right, bottom in world px, for hair and costume beyond the sprite
TRACK_ABOVE = 200
GRAPH = ROOT / "design/fatfish/h3_reference_walk_v01/prompt.api.json"
STYLE = ("Clean cel-shaded anime game sprite with bold dark outlines of even weight and flat saturated colors. Locked camera, full body always visible, flat uniform medium-gray background, "
         "no ground shadow, no scene, no cuts, no zoom, no extra people. No guns, no weapons, no rings, circles, orbs, glow, sparkles, motion blur streaks or magic anywhere. No text.")


def clip_layout(start, end):
    boxes = {i: native_world(i).getbbox() for i in range(start, end + 1)}

    def window(values):
        x0 = min(b[0] for b in values) - MARGIN[0]
        y0 = min(b[1] for b in values) - MARGIN[1]
        x1 = max(b[2] for b in values) + MARGIN[2]
        y1 = max(b[3] for b in values) + MARGIN[3]
        side = max(x1 - x0, y1 - y0)
        return [(x0 + x1) // 2 - side // 2, y1 - side, side]

    fixed = window(boxes.values())
    if fixed[2] <= TRACK_ABOVE:
        return fixed, {i: [0, 0] for i in boxes}
    centers = {i: ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2) for i, b in boxes.items()}
    anchor = centers[start]
    shifts = {i: [c[0] - anchor[0], c[1] - anchor[1]] for i, c in centers.items()}
    moved = [(b[0] - shifts[i][0], b[1] - shifts[i][1], b[2] - shifts[i][0], b[3] - shifts[i][1]) for i, b in boxes.items()]
    return window(moved), shifts


def reference_frame(slot, window, shift=(0, 0)):
    x, y, side = window
    x, y = x + shift[0], y + shift[1]
    world = Image.new("RGBA", (1100, 1100), (128, 128, 128, 255))
    world.alpha_composite(native_world(slot), (300, 300))
    crop = world.crop((x + 300, y + 300, x + side + 300, y + side + 300))
    return crop.convert("RGB").resize((SIDE, SIDE), Image.Resampling.NEAREST)


def prepare_job(clip, attempt=1):
    import fatfish_full_ref2va as F
    from fatfish_h3_pose_walk import encoder, gui
    from fatfish_h3_walk import read, save, sha

    folder = P.run / "jobs" / clip["id"] / f"attempt_{attempt:02d}"
    if (folder / "job.json").exists():
        return folder
    (folder / "input").mkdir(parents=True, exist_ok=True)
    start, end = clip["start"], clip["end"]
    window, shifts = clip_layout(start, end)
    slots = end - start + 1
    period = slots * 100.0
    mapping = []
    for i in range(124):
        phase = (i % clip["loop"] + 0.5) / clip["loop"] * period if "loop" in clip else np.clip((i - 12 + 0.5) / 96, 0, 1 - 1e-9) * period
        mapping.append(start + min(slots - 1, int(phase // 100)))
    encoder(folder / "input/motion.mp4", (reference_frame(s, window, shifts[s]) for s in mapping))
    shutil.copy2(P.master, folder / "input/appearance.png")
    base = f"{P.id}_v{P.version:02d}"
    shared = F.STUDIO / "shared/input" / base / clip["id"] / f"attempt_{attempt:02d}"
    shared.mkdir(parents=True, exist_ok=True)
    for name in ("motion.mp4", "appearance.png"):
        shutil.copy2(folder / "input" / name, shared / name)
    prompt = ("Picture: Use <Picture 1> for the exact identity and costume. Use <Video 1> as the complete motion and pose timeline: replace only the character in the video. "
              + clip["motion"] + " Match the source torso tilt, head orientation, arm height, hand trajectory, leg bends and body orientation in every frame, with both arms always clearly visible. "
              + ("Repeat this one action smoothly." if "loop" in clip else "Perform the whole sequence once in source order and finish holding the final pose. Do not replace this action with walking or idle. ")
              + P.character["identity"] + " Hair and cloth react naturally to the movement and trail behind it. " + STYLE + "\nSound: Quiet neutral room tone, no speech.\nScore: No music.")
    (folder / "prompt.txt").write_text(prompt, "utf-8")
    graph = copy.deepcopy(read(GRAPH))
    relative = shared.relative_to(F.STUDIO / "shared/input").as_posix()
    graph["5"]["inputs"]["image"] = relative + "/appearance.png"
    graph["7"]["inputs"]["file"] = relative + "/motion.mp4"
    graph["6"]["inputs"].update(prompt=prompt, width=SIDE, height=SIDE)
    graph["12"]["inputs"]["noise_seed"] = 20261107 + start + attempt * 1000
    prefix = f"{base}/{clip['id']}_a{attempt:02d}"
    graph["20"]["inputs"]["filename_prefix"] = "video/" + prefix
    for key, label in (("22", "video"), ("23", "audio")):
        graph[key]["inputs"]["filename_prefix"] = "latents/" + prefix + "_" + label
    runner = F.load_runner()
    workflow = gui(graph, runner.request("/object_info", timeout=30))
    workflow["last_node_id"] = 23
    save(folder / "prompt.api.json", graph)
    save(folder / "workflow.json", workflow)
    save(folder / "reference.json", dict(clip=clip, window=window, shifts={str(k): v for k, v in shifts.items()}, side=SIDE, mapping=mapping))
    save(folder / "job.json", {"job_id": f"{P.id}_{clip['id']}_{uuid.uuid4().hex}", "status": "prepared", "mode": "one-pass",
                               "frozen_api_sha256": sha(folder / "prompt.api.json"), "frozen_gui_sha256": sha(folder / "workflow.json"),
                               "stages": [{"name": "execute", "node": "20", "width": SIDE, "height": SIDE, "client_id": str(uuid.uuid4()), "status": "prepared"}]})
    return folder


def generate(names, attempt=1):
    """Resumable: completed jobs are skipped. Clips with a sheet never run here."""
    import fatfish_full_ref2va as F
    from fatfish_h3_walk import read

    runner = F.load_runner()
    deadline = time.monotonic() + 600
    with runner.job_lock(F.STUDIO, deadline):
        runner.ensure_server(F.STUDIO, deadline)
    for clip in P.clips():
        if "sheet" in clip or (names and clip["id"] not in names):
            continue
        folder = prepare_job(clip, attempt)
        job = read(folder / "job.json")
        if job.get("status") != "completed":
            job = F.execute(folder)
        print(json.dumps(dict(clip=clip["id"], video=job["stages"][0]["videos"][0], seconds=job["stages"][0].get("elapsed_seconds")), ensure_ascii=False), flush=True)
