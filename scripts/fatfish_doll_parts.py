"""Paint doll parts through the existing 65535 CLI. One recorded request per part; never resubmits."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

from fatfish_doll import ROOT, costume

RUN = ROOT / "output/Fatfish_Doll_v03/parts"
CLI = Path(r"C:\Users\A\Desktop\fatfish_game\.agents\skills\65535\scripts\s65535.py")
UPSTREAM = RUN / "refs/dafeiyu-chibi-character-sheet.png"
JOURNAL = RUN / "journal.json"


def style_ref():
    """The recolored native sprite at 8x, so the model sees the exact target pixel density."""
    path = RUN / "refs/native_style_8x.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        world = Image.new("RGBA", (500, 500))
        hair = Image.open(ROOT / "materials/female_mage/reference_composite/frames/0010.png").convert("RGBA")
        world.alpha_composite(hair, (185, 0))
        crop = world.crop((186, 272, 314, 400))
        board = Image.new("RGB", (1024, 1024), (200, 205, 215))
        big = crop.resize((1024, 1024), Image.NEAREST)
        board.paste(big, (0, 0), big)
        board.save(path)
    return path


def submit(name, prompt, refs, size, model="gpt-image-2.6-sunburst-native", resolution="1k", background="transparent"):
    journal = json.loads(JOURNAL.read_text("utf-8")) if JOURNAL.exists() else {}
    if name in journal:
        raise RuntimeError(f"{name} already submitted; refusing to resubmit")
    (RUN / "raw").mkdir(parents=True, exist_ok=True)
    journal[name] = dict(model=model, size=size, resolution=resolution, refs=[str(r) for r in refs],
                         prompt=prompt, started=time.time())
    JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), "utf-8")
    command = [sys.executable, str(CLI), "image", "--model", model, "--prompt", prompt, "--n", "1", "--size", size,
               "--resolution", resolution, "--background", background, "--quality", "high",
               "--out", str(RUN / "raw"), "--name", name, "--timeout", "900"]
    for ref in refs:
        command += ["--image", str(ref)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    journal[name].update(exit=result.returncode, stdout=result.stdout[-1000:], stderr=result.stderr[-600:], finished=time.time())
    JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), "utf-8")
    print(name, result.returncode, result.stdout[-300:], result.stderr[-300:])
    return result.returncode
