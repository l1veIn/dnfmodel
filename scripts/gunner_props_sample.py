"""Reference images for the Claude-style prop samples: each original frame, enlarged, on flat magenta. Read-only for the game folder."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from survey_gunner_effects import GAME, read_npk, reader  # noqa: E402

OUT = ROOT / "output" / "gunner_props_sample"
FX = "sprite_character_gunner_effect_"
ITEMS = {
    "bomb": (FX + "aturaniumbomb", "aturaniumbombvpmissile", 0),
    "mech": (FX + "atmechboltmx", "04_gun2", 0),
    "g2": (FX + "g2", "g2_body", 0),
}
KEY = (255, 0, 255)


def load(pack, stem):
    path = GAME / f"{pack}.NPK"
    for entry in read_npk(path):
        if Path(entry["path"]).stem == stem:
            with path.open("rb") as stream:
                stream.seek(entry["offset"])
                return reader(stream.read(entry["length"]), entry["version"]), entry
    raise KeyError(stem)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    facts = {}
    for name, (pack, stem, index) in ITEMS.items():
        img, entry = load(pack, stem)
        frames = [f for f in img.frames if "link" not in f and f["w"] * f["h"] > 16]
        frame = frames[index]
        picture = img.image(frame["index"]).convert("RGBA")
        picture.save(OUT / f"{name}_original.png")
        zoom = max(2, min(1000 // picture.width, 1000 // picture.height))
        big = picture.resize((picture.width * zoom, picture.height * zoom), Image.NEAREST)
        board = Image.new("RGB", (1024, 1024), KEY)
        board.paste(big, ((1024 - big.width) // 2, (1024 - big.height) // 2), big)
        board.save(OUT / f"{name}_ref.png")
        facts[name] = dict(pack=pack, img=entry["path"], version=entry["version"], frames=len(frames), frame=frame["index"], size=picture.size, zoom=zoom)
        print(name, facts[name])
    (OUT / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()
