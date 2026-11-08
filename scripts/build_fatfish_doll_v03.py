"""Package the 174 native-doll frames as the full costume-cover NPK v03.

Takes every path and transparent payload from v02 unchanged and swaps only the shared
skin IMG. Frames with identical pixels and position are written as links.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from build_fatfish_all_avatar_v02 import read_payload, sha, write_shared_npk
from dnf_resources import ImgArchive, read_npk, save_json, write_v2
from fatfish_doll import ROOT
from fatfish_doll_render import OUT

BASE = ROOT / "output/Fatfish_AllAvatar_v02/A_Fatfish_FMage_AllAvatar_NoGrowtype_v02.NPK"
NAME = "A_Fatfish_FMage_NativeDoll_v03.NPK"
SKIN = "sprite/character/mage/equipment/avatar/skin/"


def body_img(source=OUT):
    images, meta, seen = [], [], {}
    for index in range(174):
        world = Image.open(source / f"native_frames/{index:04d}.png").convert("RGBA")
        box = world.getbbox()
        crop = world.crop(box)
        key = (box, hashlib.sha256(crop.tobytes()).hexdigest())
        images.append(crop)
        if key in seen:
            meta.append({"link": seen[key]})
        else:
            seen[key] = index
            meta.append({"x": box[0], "y": box[1], "canvas_width": 500, "canvas_height": 500})
    return write_v2(images, meta), len(seen)


def build(source=OUT, name=NAME):
    target = source / name
    if target.exists():
        target.unlink()
    assert sha(BASE) == "250c60ee880314ebbc19bfe361f1c5a3a0803f13d8562e621c004430962e29d6"
    rows = read_npk(BASE)
    body, unique = body_img(source)
    archive = ImgArchive(body)
    assert archive.count == 174 and archive.consumed == len(body)
    entries = []
    skin_paths = 0
    for row in rows:
        if row["path"].startswith(SKIN):
            assert row["frame_count"] == 174
            entries.append((row["path"], body))
            skin_paths += 1
        else:
            entries.append((row["path"], read_payload(BASE, row)))
    assert skin_paths == 38 and len(entries) == 12167
    target.write_bytes(write_shared_npk(entries))

    written = read_npk(target)
    raw = target.read_bytes()
    assert [r["path"] for r in written] == [r["path"] for r in rows]
    blank_refs = 0
    for row, before in zip(written, rows, strict=True):
        assert row["frame_count"] == before["frame_count"]
        payload = raw[row["offset"]:row["offset"] + row["length"]]
        if row["path"].startswith(SKIN):
            assert payload == body
        else:
            assert payload == read_payload(BASE, before)
            blank_refs += row["frame_count"]
    # Every frame decoded from the package equals the rendered world image.
    check = ImgArchive(raw[written[0]["offset"]:written[0]["offset"] + written[0]["length"]]) if written[0]["path"].startswith(SKIN) else ImgArchive(body)
    for index in range(174):
        frame = check.resolve(index)
        # Paste, not composite: blending would round semi-transparent pixels. RGB under alpha 0 is meaningless.
        world = Image.new("RGBA", (500, 500))
        world.paste(check.image(index), (frame["x"], frame["y"]))
        decoded, expected = np.array(world), np.array(Image.open(source / f"native_frames/{index:04d}.png").convert("RGBA"))
        assert np.array_equal(decoded[..., 3], expected[..., 3]), index
        visible = expected[..., 3] > 0
        assert np.array_equal(decoded[visible], expected[visible]), index
    report = dict(package=str(target), sha256=sha(target), bytes=target.stat().st_size, entries=len(entries), skin_paths=skin_paths,
                  frames=174, unique_frames=unique, transparent_logical_frames=blank_refs,
                  decoded_frames_match_rendered_pngs=True, base_package=str(BASE), base_transparent_payloads_unchanged=True,
                  game_runtime_validated=False)
    save_json(source / "validation.json", report)
    (source / (name + ".sha256")).write_text(report["sha256"] + "  " + name + "\n", "ascii")
    print(json.dumps({k: report[k] for k in ("sha256", "bytes", "entries", "unique_frames")}))


if __name__ == "__main__":
    build()
