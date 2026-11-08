"""Female gunner source frames for the Claude patch: read-only decoding of default-costume layers from the game packs."""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from dnf_resources import ImgArchive, read_npk

ROOT = Path(__file__).resolve().parents[1]
GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
MATERIALS = ROOT / "materials/female_gunner"
RUN = ROOT / "design/claude_gunner"
OUT = ROOT / "output/Claude_Gunner_v02"
PREFIX = "sprite/character/gunner/atequipment/avatar/"
FRAMES = 143
CANVAS = 500
STREAK = 2
# Back to front. A neutral registration reference, not the game's real draw order.
ORDER = ("pants/gg_pants0000d", "hair/gg_hair0000d", "hair/gg_hair0000b", "skin/gg_body0000", "shoes/gg_shoes0000b", "shoes/gg_shoes0000a",
         "pants/gg_pants0000a", "coat/gg_coat0000d", "coat/gg_coat0000c", "coat/gg_coat0000b", "coat/gg_coat0000a", "face/gg_face10000b",
         "hair/gg_hair0000a", "cap/gg_cap0000c")
FIGURE = ("skin/gg_body0000", "pants/gg_pants0000a", "shoes/gg_shoes0000a", "shoes/gg_shoes0000b", "coat/gg_coat0000a", "coat/gg_coat0000b", "coat/gg_coat0000c")


@lru_cache(maxsize=None)
def _rows(pack):
    return {row["path"]: row for row in read_npk(GAME / pack)}


@lru_cache(maxsize=None)
def archive(layer):
    part = layer.split("/")[0]
    pack = f"sprite_character_gunner_atequipment_avatar_{part}.NPK"
    row = _rows(pack)[PREFIX + layer + ".img"]
    with (GAME / pack).open("rb") as stream:
        stream.seek(row["offset"])
        return ImgArchive(stream.read(row["length"]))


@lru_cache(maxsize=None)
def weapon_archive(kind, layer):
    pack = f"sprite_character_gunner_atequipment_weapon_{kind}.NPK"
    row = _rows(pack)[f"sprite/character/gunner/atequipment/weapon/{kind}/{layer}.img"]
    with (GAME / pack).open("rb") as stream:
        stream.seek(row["offset"])
        return ImgArchive(stream.read(row["length"]))


def place(source, index):
    world = Image.new("RGBA", (CANVAS, CANVAS))
    frame = source.resolve(index)
    if frame["width"] > 1 and frame["height"] > 1:
        world.alpha_composite(source.image(index).convert("RGBA"), (frame["x"], frame["y"]))
    return world


def layer_world(layer, index):
    return place(archive(layer), index)


def weapon_world(index, kind="rev", layer="gg_rev0000c"):
    return place(weapon_archive(kind, layer), index)


def native_world(index):
    path = MATERIALS / f"reference_composite/frames/{index:04d}.png"
    return Image.open(path).convert("RGBA")


def solid(mask):
    """Remove thin motion-blur streaks drawn into some source frames, keeping limbs and their edges."""
    core = ndimage.binary_opening(mask, structure=np.ones((3, 3)), iterations=STREAK)
    labels, count = ndimage.label(core, structure=np.ones((3, 3)))
    if not count:
        return mask
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    near = ndimage.binary_dilation(labels == sizes.argmax(), iterations=12)
    # A real limb is large and stays near the body; what is left of a streak is small or floats away from it.
    keep = np.isin(labels, np.unique(labels[near & (labels > 0)])) & (sizes[labels] >= 24)
    return ndimage.binary_dilation(keep, iterations=STREAK + 1) & mask


def figure_mask(index):
    mask = np.zeros((CANVAS, CANVAS), bool)
    for layer in FIGURE:
        mask |= np.asarray(layer_world(layer, index))[..., 3] > 0
    return solid(mask)


def export_composites():
    target = MATERIALS / "reference_composite/frames"
    target.mkdir(parents=True, exist_ok=True)
    for index in range(FRAMES):
        world = Image.new("RGBA", (CANVAS, CANVAS))
        for layer in ORDER:
            world.alpha_composite(layer_world(layer, index))
        pixels = np.array(world)
        pixels[~solid(pixels[..., 3] > 0)] = 0
        Image.fromarray(pixels, "RGBA").save(target / f"{index:04d}.png")
    (MATERIALS / "reference_composite/reference.json").write_text(json.dumps(dict(frame_count=FRAMES, canvas=CANVAS, layers_back_to_front=ORDER), indent=1), "utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    export_composites()
