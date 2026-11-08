"""v06 whole-figure route: new master, square framing per clip, then pose-matched frame choice.

What changes from the old H3 run: the figure fills far more of the video because each clip gets
its own tight square window, frames are chosen by comparing poses to the native sprite instead
of by time, and the crisp downscale in fatfish_final_post replaces plain resizing.
Run generation with the ComfyUI venv python.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

import fatfish_full_ref2va as F
from fatfish_doll import ROOT
from fatfish_h3_pose_walk import encoder, gui
from fatfish_h3_walk import read, save, sha

RUN = ROOT / "design/fatfish/final_v06"
OUT = ROOT / "output/Fatfish_Final_v06"
MASTER = OUT / "parts/raw/fit_b_0.png"  # attempt_01 jobs used master_0.png; attempt_02 onward use this one
NATIVE = ROOT / "materials/female_mage/reference_composite/frames"
SIDE = 512
MARGIN = (26, 12, 16, 8)  # left, top, right, bottom in world px: room for hair and tail behind her
LOOP_FRAMES = {0: 40, 10: 48, 14: 48, 18: 28, 53: 48, 155: 48, 163: 48}

IDENTITY = ("Keep the exact character and body proportions from <Picture 1>: whale-girl maid with a small head, oval face, thick wavy very long deep-blue hair with a large bright sky-blue fade over its lower half, "
            "white ruffled headband, sky-blue bow, navy whale-fin ears, curled antenna hair, navy puffed sleeves with white frilled cuffs, white blouse, navy corset with gold buttons, "
            "large white frilled apron with a small blue whale emblem, navy skirt with gold trim and gold bows, white frilled hem, white stockings, navy Mary Jane shoes, "
            "and a short chubby navy whale tail with pale belly, coming out from under the skirt and hanging close behind her legs. The tail stays short and separate from the skirt and hair.")
STYLE = ("Clean cel-shaded anime game sprite with bold dark outlines of even weight and flat saturated colors. Locked camera, full body always visible, flat uniform medium-gray background, "
         "no ground shadow, no scene, no cuts, no zoom, no extra people, no red hair or red clothes, no hat, no glasses, no weapons, no spell effects, no text.")
RETRY = ("Her hands are empty: absolutely no rings, circles, orbs, glow, sparkles or magic anywhere in the frame. A lifted leg is always a white-stocking leg with a navy shoe, "
         "never the tail; the tail stays short behind her skirt. A raised arm stays fully visible in front of the hair, with the navy sleeve and white cuff clearly readable. ")


def clips():
    data = json.loads((ROOT / "design/fatfish/action_catalog/manual_motion.json").read_text("utf-8"))
    return sorted(data["clips"], key=lambda c: c["start"])


def native_world(slot):
    world = Image.new("RGBA", (500, 500))
    world.alpha_composite(Image.open(NATIVE / f"{slot:04d}.png").convert("RGBA"), (185, 0))
    return world


def clip_window(start, end):
    """Square world window holding every pose of the clip plus room behind her."""
    boxes = [native_world(i).getbbox() for i in range(start, end + 1)]
    x0 = min(b[0] for b in boxes) - MARGIN[0]
    y0 = min(b[1] for b in boxes) - MARGIN[1]
    x1 = max(b[2] for b in boxes) + MARGIN[2]
    y1 = max(b[3] for b in boxes) + MARGIN[3]
    side = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    # Keep the ground in view at the bottom edge rather than centering vertically on air.
    return [cx - side // 2, cy - side // 2, side]


def reference_frame(slot, window):
    x, y, side = window
    world = Image.new("RGBA", (500 + 400, 500 + 400), (128, 128, 128, 255))
    world.alpha_composite(native_world(slot), (200, 200))
    crop = world.crop((x + 200, y + 200, x + side + 200, y + side + 200))
    return crop.convert("RGB").resize((SIDE, SIDE), Image.Resampling.NEAREST)


def motion_text(start):
    return F.DESCRIPTIONS.get(start, "Follow the reference motion exactly.")


def prepare_job(clip, attempt=1, side=SIDE):
    folder = RUN / "jobs" / clip["id"] / f"attempt_{attempt:02d}"
    if (folder / "job.json").exists():
        return folder
    (folder / "input").mkdir(parents=True, exist_ok=True)
    start, end = clip["start"], clip["end"]
    window = clip_window(start, end)
    slots = end - start + 1
    period = slots * 100.0
    mapping = []
    for i in range(124):
        if start in LOOP_FRAMES:
            phase = (i % LOOP_FRAMES[start] + 0.5) / LOOP_FRAMES[start] * period
        else:
            phase = np.clip((i - 12 + 0.5) / 96, 0, 1 - 1e-9) * period
        mapping.append(start + min(slots - 1, int(phase // 100)))
    encoder(folder / "input/motion.mp4", (reference_frame(s, window) for s in mapping))
    shutil.copy2(MASTER, folder / "input/appearance.png")
    shared = F.STUDIO / "shared/input/fatfish_final_v06" / clip["id"] / f"attempt_{attempt:02d}"
    shared.mkdir(parents=True, exist_ok=True)
    for name in ("motion.mp4", "appearance.png"):
        shutil.copy2(folder / "input" / name, shared / name)
    cycle = start in LOOP_FRAMES
    prompt = ("Picture: Use <Picture 1> for the exact identity and costume. Use <Video 1> as the complete motion and pose timeline: replace only the character in the video. "
              + motion_text(start) + " Match the source torso tilt, head orientation, arm height, hand trajectory, leg bends and body orientation in every frame, with both arms and both legs always clearly visible. "
              + ("Repeat this one action smoothly." if cycle else "Perform the whole sequence once in source order and finish holding the final pose. Do not replace this action with walking or idle. ")
              + IDENTITY + " Hair, ears, antenna hair and tail react naturally to the movement. "
              + (RETRY if attempt >= 3 else "") + STYLE + "\nSound: Quiet neutral room tone, no speech.\nScore: No music.")
    (folder / "prompt.txt").write_text(prompt, "utf-8")
    graph = copy.deepcopy(read(ROOT / "design/fatfish/h3_reference_walk_v01/prompt.api.json"))
    relative = shared.relative_to(F.STUDIO / "shared/input").as_posix()
    graph["5"]["inputs"]["image"] = relative + "/appearance.png"
    graph["7"]["inputs"]["file"] = relative + "/motion.mp4"
    graph["6"]["inputs"].update(prompt=prompt, width=side, height=side)
    graph["12"]["inputs"]["noise_seed"] = 20261106 + start + attempt * 1000
    prefix = f"fatfish_final_v06/{clip['id']}_a{attempt:02d}"
    graph["20"]["inputs"]["filename_prefix"] = "video/" + prefix
    for key, label in (("22", "video"), ("23", "audio")):
        graph[key]["inputs"]["filename_prefix"] = "latents/" + prefix + "_" + label
    runner = F.load_runner()
    workflow = gui(graph, runner.request("/object_info", timeout=30))
    workflow["last_node_id"] = 23
    save(folder / "prompt.api.json", graph)
    save(folder / "workflow.json", workflow)
    save(folder / "reference.json", dict(clip=clip, window=window, side=side, mapping=mapping))
    save(folder / "job.json", {"job_id": "fatfish_final_" + clip["id"] + "_" + uuid.uuid4().hex, "status": "prepared", "mode": "one-pass",
                               "frozen_api_sha256": sha(folder / "prompt.api.json"), "frozen_gui_sha256": sha(folder / "workflow.json"),
                               "stages": [{"name": "execute", "node": "20", "width": side, "height": side, "client_id": str(uuid.uuid4()), "status": "prepared"}]})
    return folder


def generate(names, attempt=1, side=SIDE):
    import time
    runner = F.load_runner()
    deadline = time.monotonic() + 600
    with runner.job_lock(F.STUDIO, deadline):
        runner.ensure_server(F.STUDIO, deadline)
    for clip in clips():
        ident = f"clip_{clip['start']:03d}_{clip['end']:03d}"
        if names and ident not in names:
            continue
        clip = dict(id=ident, name=clip["name"], start=clip["start"], end=clip["end"])
        folder = prepare_job(clip, attempt, side)
        job = read(folder / "job.json")
        if job.get("status") != "completed":
            job = F.execute(folder)
        print(json.dumps(dict(clip=ident, video=job["stages"][0]["videos"][0], seconds=job["stages"][0].get("elapsed_seconds"),
                              ram=job.get("memory_after")), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("clips", nargs="*")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--side", type=int, default=SIDE)
    args = parser.parse_args()
    generate(args.clips, args.attempt, args.side)
