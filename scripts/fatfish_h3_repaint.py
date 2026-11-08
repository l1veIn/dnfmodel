"""H3 trial: the layered normal-proportion frames drive Ref2VA, so pose and costume start correct.

Reuses the frozen Ref2VA job builder and runner, swapping only the appearance image and the
motion frames. Run with the ComfyUI venv python. Output is a trial only; nothing is packaged.
"""
from __future__ import annotations

import json
import sys
import time

from PIL import Image

import fatfish_full_ref2va as F
from fatfish_doll import ROOT

RUN = ROOT / "design/fatfish/h3_repaint_v05"
DOLL = ROOT / "output/Fatfish_Normal_v05/native_frames"
MASTER = ROOT / "output/Fatfish_Idle_Body_Native_v02/raw/idle_0010_0.png"
CLIPS = {"walk": ("clip_000_009", "默认走路", 0, 9, True), "combo": ("clip_109_127", "三段平A", 109, 127, False)}
ATTEMPT = 5


def appearance():
    path = RUN / "appearance_gray.png"
    if not path.exists():
        RUN.mkdir(parents=True, exist_ok=True)
        image = Image.open(MASTER).convert("RGBA")
        base = Image.new("RGBA", image.size, (128, 128, 128, 255))
        base.alpha_composite(image)
        base.convert("RGB").save(path)
    return path


def reference_frame(slot):
    """Same fixed world window as the frozen pipeline, showing the dressed layered frame."""
    world = Image.new("RGBA", (500, 500), (128, 128, 128, 255))
    world.alpha_composite(Image.open(DOLL / f"{slot:04d}.png").convert("RGBA"))
    return world.convert("RGB").transform((320, 192), Image.Transform.AFFINE, (2 / 3, 0, 143.3333333333333, 0, 2 / 3, 272), resample=Image.Resampling.NEAREST)


def main(names):
    F.RUN, F.HD, F.reference_frame = RUN, appearance(), reference_frame
    # The job builder reads node schemas from the server, so it has to be up first.
    runner = F.load_runner()
    deadline = time.monotonic() + 600
    with runner.job_lock(F.STUDIO, deadline):
        runner.ensure_server(F.STUDIO, deadline)
    for name in names:
        ident, title, start, end, cycle = CLIPS[name]
        clip = dict(id=ident, name=title, start=start, end=end, frame_ms=[100] * (end - start + 1), cycle=cycle)
        folder = F.prepare_job(clip, ATTEMPT)
        job = F.execute(folder)
        print(json.dumps(dict(clip=name, video=job["stages"][0]["videos"][0], seconds=job["stages"][0].get("elapsed_seconds"))), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(CLIPS))
