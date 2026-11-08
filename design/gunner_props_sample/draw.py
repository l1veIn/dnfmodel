"""Draws the three Claude-style prop samples through the 65535 CLI. Each name is submitted once; a redraw needs a new name."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = Path(r"C:\Users\A\Desktop\fatfish_game\.agents\skills\65535\scripts\s65535.py")
MODEL = "gpt-image-2.6-sunburst-native"
LOCK = threading.Lock()
OUT = ROOT / "output" / "gunner_props_sample"
RAW = OUT / "raw"
JOURNAL = OUT / "journal.json"
STYLE_REF = ROOT / "output/claude_gunner_v02/parts/raw/claude_a_0.png"

COMMON = """Image 1 is only the color and rendering authority: the same warm cream white, matte near-black, clay orange and thin gold trim, and the same clean cel shading with bold dark outlines of even weight. Do not draw the character from Image 1, and no flowers, ribbons or fabric.

Image 2 is a game sprite on a flat magenta background. It decides the object's silhouette, its position and size in the square, and its viewing angle, and nothing about its surface. Redraw the object in exactly the same place, at the same size and the same angle, so that it could be laid over the sprite and match its outline.

Design language: premium future hardware from a calm, thoughtful AI lab. Smooth glazed ceramic armor plates in warm cream white, matte near-black joints and machinery, clean deliberate panel lines, thin gold trim, and glowing seams and energy in clay orange, RGB 217 119 87 to 232 112 48, with a pale cream core. No blue, no green, no purple, no rust, no grime, no military olive.

{item}

Keep shapes large and simple, because this will be reduced to game size. No pixel art, no painterly texture, no extra objects. Background: completely flat uniform magenta, RGB 255 0 255, edge to edge, with no shadow, no floor, no glow spilling onto it, no grid, and no text other than what is described above.
"""

ITEMS = {
    "bomb": """The object is a huge warhead seen from the side, tilted, with its tail toward the upper left. Keep every part of the sprite's outline: the wide funnel-shaped tail ring with open struts at the upper left, the narrow neck, the clamp band with the angular hexagonal plate behind it, and the long straight cylindrical body running to the lower right. The body stops at the very same flat horizontal cut at the bottom as in Image 2, so do not add a nose and do not extend it. Make the long body smooth cream ceramic, the hexagonal plate and clamp near-black with gold edges, and the funnel ring near-black with a glowing clay orange inner rim. Add one thin glowing clay orange seam around the body. On the cream body, large and bold, running along the body's axis, paint the two characters A\\ in clay orange as a clean stencil mark: a capital A followed by a backslash. Nothing else is written on it.""",
    "mech": """The object is a humanoid combat mecha in flight, in exactly the sprite's pose: the head, the tilt of the torso, both arms holding the long rifle across the upper right, the swept fins behind the shoulders, one leg stretched down and the other bent. Armor plates are cream ceramic with near-black joints. The long rifle is matte near-black with one glowing clay orange energy line along it. The head has one smooth dark visor with a soft clay orange glow. In the center of the chest, clearly visible, is one glowing clay orange spark emblem: an asterisk-like star with about twelve tapered rays of slightly uneven length, with a pale cream center. Thin gold trim on the shoulders and belt.""",
    "g2": """The object is a very small round flying robot seen from the side, shown here hugely enlarged; in the game it is only 28 pixels wide, so it needs only a few big shapes and no fine detail. Keep the sprite's round outline, the horizontal dark band across its middle, and the big round lens on the right side. The shell is smooth cream ceramic with a thin gold edge, the band and the rim around the lens are near-black, and the lens is one big glowing clay orange circle with a pale cream center, with a simple bold asterisk spark of about eight rays in it.""",
}


def draw(name):
    prompt = COMMON.format(item=ITEMS[name.split("_")[0]])
    with LOCK:
        journal = json.loads(JOURNAL.read_text("utf-8")) if JOURNAL.exists() else {}
        if name in journal:
            return f"{name} already submitted"
        journal[name] = dict(model=MODEL, size="1:1", prompt=prompt, started=time.time())
        JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), "utf-8")
    command = [sys.executable, str(CLI), "image", "--model", MODEL, "--prompt", prompt, "--n", "1", "--size", "1:1", "--resolution", "1k", "--background", "opaque", "--quality", "high",
               "--out", str(RAW), "--name", name, "--timeout", "900", "--image", str(STYLE_REF), "--image", str(OUT / f"{name.split('_')[0]}_ref.png")]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    return name, result.returncode, result.stderr[-300:] if result.returncode else "ok"


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:] or ["bomb_v1", "mech_v1", "g2_v1"]
    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(draw, names))
    journal = json.loads(JOURNAL.read_text("utf-8"))
    for item in results:
        print(item)
        if isinstance(item, tuple):
            journal[item[0]].update(exit=item[1], finished=time.time())
    JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=1), "utf-8")
