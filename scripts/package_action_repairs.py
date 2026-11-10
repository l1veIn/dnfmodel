"""Copy reviewed character repairs over a complete illustration NPK.

Only the selected avatar/skin payload changes. This tool never invokes final,
reads no official package, does not edit design pointers or issue events, and
has no game-install operation. Review the separate repair candidate first.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from dnf_resources import ImgArchive, NAME_KEY, NPK_MAGIC, read_npk, write_v2

PROFILES = {
    "dragon": dict(
        ident="gpt_dragon_slayer_v03", source="output/gpt_dragon_slayer_v03",
        output="output/gpt_dragon_slayer_v05", version=5, frames=246,
        base="output/gpt_dragon_slayer_v04/A_GPTDragon_FSlayer_v04.NPK",
        base_sha256="28cfe3543ac511dfb3dc5a447877b060b45d49c74a59af35942eb31072f92a3e",
        name="A_GPTDragon_FSlayer_v05.NPK", entries=10099, skin_count=24,
        skin_prefix="sprite/character/swordman/atequipment/avatar/skin/",
        slots=list(range(4)) + list(range(5, 13)) + list(range(123, 132))
              + [230] + list(range(232, 236)) + list(range(243, 246)),
    ),
    "whale": dict(
        ident="fatfish_whale_maid", source="output/fatfish_whale_maid_v01",
        output="output/fatfish_whale_maid_v03", version=3, frames=174,
        base="output/fatfish_whale_maid_v02/A_FatfishWhaleMaid_FMage_v02.NPK",
        base_sha256="07ffd0f1551a1def5660b1c8ace50ac0cca82668b3f73077b2428f87fb48fd4d",
        name="A_FatfishWhaleMaid_FMage_v03.NPK", entries=12054, skin_count=38,
        skin_prefix="sprite/character/mage/equipment/avatar/skin/",
        slots=list(range(10, 18)),
    ),
}


def stamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def native_records(folder, count):
    records = {}
    for slot in range(count):
        path = folder / f"{slot:04d}.png"
        assert path.is_file(), path
        with Image.open(path) as im:
            assert im.size == (500, 500), (path, im.size)
        records[path.name] = dict(sha256=sha(path), mtime_ns=path.stat().st_mtime_ns)
    assert len(list(folder.glob("*.png"))) == count, "Unexpected native PNG count"
    return records


def protected_files(profile):
    files = set()
    source = ROOT / profile["source"]
    for sub in ("native_frames", "parts", "clips"):
        files.update(p for p in (source / sub).rglob("*") if p.is_file())
    files.add(ROOT / profile["base"])
    run = ROOT / "design" / profile["ident"]
    for name in ("pose_sheets.json", "clips.json", "hand_overrides.json", "reuse.json"):
        if (run / name).is_file():
            files.add(run / name)
    for folder in ("claude_buff_v07", "dragon_buff_v05", "whale_buff_v02"):
        files.update(p for p in (ROOT / "output" / folder / "preview").rglob("*") if p.is_file())
    for path in ("design/claude_gunner/buff_v07.json",
                 "design/gpt_dragon_slayer_v03/buff_v05.json",
                 "design/fatfish_whale_maid/buff_v02.json"):
        files.add(ROOT / path)
    return {rel(p): dict(sha256=sha(p), bytes=p.stat().st_size) for p in sorted(files)}


def assert_protected(output):
    baseline = load(output / "protected_baseline.json")
    for name, info in baseline["files"].items():
        assert sha(ROOT / name) == info["sha256"], f"Protected file changed: {name}"
    return len(baseline["files"])


def prepare(profile):
    output = ROOT / profile["output"]
    source = ROOT / profile["source"]
    assert sha(ROOT / profile["base"]) == profile["base_sha256"], "Unexpected complete base"
    assert not output.exists(), f"Candidate already exists: {output}"
    before = native_records(source / "native_frames", profile["frames"])
    protection = protected_files(profile)
    output.mkdir(parents=True)
    for sub in ("native_frames", "parts", "clips"):
        shutil.copytree(source / sub, output / sub, copy_function=shutil.copy2)
    after = native_records(output / "native_frames", profile["frames"])
    assert before == after, "copy2 must preserve bytes and native mtimes"
    save(output / "protected_baseline.json", dict(created_at=stamp(), files=protection,
         note="Old native/source/complete NPK and all three buff previews are read-only."))
    save(output / "action_repair_prepare.json", dict(
        created_at=stamp(), profile=profile, native_baseline=before,
        original_patch_sha256=sha(ROOT / "design" / profile["ident"] / "patch.json"),
        original_selection_files={rel(p): sha(p) for p in sorted((source / "clips").glob("*/selection.json"))},
        status="copied_baseline_waiting_for_root_review", installed=False,
    ))
    print(json.dumps(dict(prepared=rel(output), protected=len(protection), native_frames=len(before))))


def clip_for_slot(profile, slot):
    clips = load(ROOT / "design" / profile["ident"] / "clips.json")["clips"]
    matches = [c for c in clips if c["start"] <= slot <= c["end"]]
    assert len(matches) == 1, slot
    clip = matches[0]
    return f"clip_{clip['start']:03d}_{clip['end']:03d}"


def apply(profile, args):
    output = ROOT / profile["output"]
    assert args.approved, "Only apply after root has reviewed the repair candidate"
    assert (output / "action_repair_prepare.json").is_file(), "prepare first"
    assert not (output / "action_repair_apply.json").exists(), "Already applied; do not overwrite a reviewed candidate"
    assert not (output / profile["name"]).exists(), "Published package is frozen"
    assert_protected(output)
    source = args.native_dir.resolve(strict=True)
    expected = {f"{slot:04d}.png" for slot in profile["slots"]}
    assert {p.name for p in source.glob("*.png")} == expected, "Provide exactly the authorized native slots"
    baseline = load(output / "action_repair_prepare.json")["native_baseline"]
    assert native_records(output / "native_frames", profile["frames"]) == baseline
    evidence = []
    for slot in profile["slots"]:
        png = source / f"{slot:04d}.png"
        with Image.open(png) as im:
            assert im.size == (500, 500), (png, im.size)
            assert im.convert("RGBA").getchannel("A").getbbox(), f"Empty body: {png}"
        shutil.copy2(png, output / "native_frames" / png.name)
        evidence.append(dict(slot=slot, input=str(png), sha256=sha(png)))
    hd_records = []
    if args.hd_root:
        for png in sorted(args.hd_root.resolve(strict=True).rglob("*.png")):
            if not png.stem.isdecimal() or int(png.stem) not in profile["slots"]:
                continue
            slot = int(png.stem)
            dest = output / "clips" / clip_for_slot(profile, slot) / "hd" / f"{slot:04d}.png"
            shutil.copy2(png, dest)
            hd_records.append(dict(slot=slot, input=str(png), output=rel(dest), sha256=sha(png)))
    selection_records = []
    if args.selection_root:
        for source_selection in sorted(args.selection_root.resolve(strict=True).rglob("selection.json")):
            incoming = load(source_selection)
            slots = {row["slot"] for row in incoming["frames"]}
            authorized = slots.intersection(profile["slots"])
            assert authorized, source_selection
            names = {clip_for_slot(profile, slot) for slot in authorized}
            assert len(names) == 1, source_selection
            dest = output / "clips" / names.pop() / "selection.json"
            data = load(dest)
            rows = {row["slot"]: row for row in incoming["frames"] if row["slot"] in authorized}
            data["frames"] = [rows.get(row["slot"], row) for row in data["frames"]]
            data["action_repair_source"] = dict(path=str(source_selection), sha256=sha(source_selection),
                                               native_is_authoritative=True,
                                               note="Do not rerun full final on this incremental candidate.")
            save(dest, data)
            selection_records.append(dict(source=str(source_selection), output=rel(dest), sha256=sha(dest)))
    manifest_record = None
    if args.repair_manifest:
        manifest = args.repair_manifest.resolve(strict=True)
        dest = output / "repair_source_manifest.json"
        shutil.copy2(manifest, dest)
        manifest_record = dict(source=str(manifest), copied=rel(dest), sha256=sha(manifest))
    records = native_records(output / "native_frames", profile["frames"])
    for name, old in baseline.items():
        if name not in expected:
            assert records[name] == old, f"Non-target bytes/mtime changed: {name}"
    count = assert_protected(output)
    save(output / "action_repair_apply.json", dict(
        applied_at=stamp(), root_review_selected=True, installed=False,
        authorized_slots=profile["slots"], inputs=evidence, hd_inputs=hd_records,
        selection_inputs=selection_records, repair_manifest=manifest_record,
        native_records=records, non_target_bytes_and_mtimes_preserved=profile["frames"]-len(expected),
        changed_native_slots=[int(name[:-4]) for name in records if records[name]["sha256"] != baseline[name]["sha256"]],
        protected_files_unchanged=count,
    ))
    print(json.dumps(dict(applied=rel(output), allowed_slots=len(expected), protected=count)))


def body_img(folder, count):
    """Same crop/link/write_v2 semantics as kit.release.body_img; no global P."""
    images, metadata, seen, frame_records = [], [], {}, []
    for slot in range(count):
        world = Image.open(folder / f"{slot:04d}.png").convert("RGBA")
        assert world.size == (500, 500)
        box = world.getbbox()
        assert box, f"Empty body at frame {slot}"
        crop = world.crop(box)
        key = box, hashlib.sha256(crop.tobytes()).hexdigest()
        images.append(crop)
        if key in seen:
            meta = {"link": seen[key]}
        else:
            seen[key] = slot
            meta = dict(x=box[0], y=box[1], canvas_width=500, canvas_height=500)
        metadata.append(meta)
        frame_records.append(dict(slot=slot, bbox=list(box), metadata=meta))
    return write_v2(images, metadata), len(seen), frame_records


def write_shared_npk(entries):
    """The existing release writer's payload deduplication, without config import."""
    unique, payloads = {}, []
    offset = 52 + 264 * len(entries)
    header = bytearray(NPK_MAGIC + struct.pack("<I", len(entries)))
    for name, payload in entries:
        if payload not in unique:
            unique[payload] = offset
            payloads.append(payload)
            offset += len(payload)
        encoded = name.encode("utf-8")
        assert len(encoded) < 256
        header.extend(struct.pack("<II", unique[payload], len(payload)))
        header.extend(bytes(a ^ b for a, b in zip(encoded.ljust(256, b"\0"), NAME_KEY)))
    checksum = hashlib.sha256(header[:len(header) // 17 * 17]).digest()
    return bytes(header) + checksum + b"".join(payloads)


def validate(profile, package_path):
    output = ROOT / profile["output"]
    applied = load(output / "action_repair_apply.json")
    records = native_records(output / "native_frames", profile["frames"])
    assert records == applied["native_records"], "Candidate native changed after reviewed apply"
    base_path = ROOT / profile["base"]
    assert sha(base_path) == profile["base_sha256"]
    original, actual = base_path.read_bytes(), package_path.read_bytes()
    old_rows, rows = read_npk(base_path), read_npk(package_path)
    assert len(old_rows) == len(rows) == profile["entries"]
    assert [r["path"] for r in old_rows] == [r["path"] for r in rows], "Path/order drift"
    assert len(set(r["path"] for r in rows)) == len(rows)
    skin_rows = [r for r in rows if r["path"].startswith(profile["skin_prefix"])]
    assert len(skin_rows) == profile["skin_count"]
    skin_payload = actual[skin_rows[0]["offset"]:skin_rows[0]["offset"]+skin_rows[0]["length"]]
    preserved = 0
    for old, row in zip(old_rows, rows, strict=True):
        payload = actual[row["offset"]:row["offset"]+row["length"]]
        if row["path"].startswith(profile["skin_prefix"]):
            assert row["frame_count"] == profile["frames"]
            assert payload == skin_payload
        else:
            assert payload == original[old["offset"]:old["offset"]+old["length"]], row["path"]
            preserved += 1
    decoded = ImgArchive(skin_payload)
    assert decoded.count == profile["frames"]
    rgba_deltas = []
    for slot in range(profile["frames"]):
        info = decoded.resolve(slot)
        assert (info["canvas_width"], info["canvas_height"]) == (500, 500)
        world = Image.new("RGBA", (500, 500))
        world.paste(decoded.image(slot), (info["x"], info["y"]))
        expected = np.asarray(Image.open(output / f"native_frames/{slot:04d}.png").convert("RGBA"))
        pixels = np.asarray(world)
        assert np.array_equal(pixels[..., 3], expected[..., 3]), f"Alpha delta at {slot}"
        visible = expected[..., 3] > 0
        assert np.array_equal(pixels[visible], expected[visible]), f"Visible RGBA delta at {slot}"
        rgba_deltas.append(int(np.abs(pixels.astype(np.int16)-expected.astype(np.int16)).max()))
    baseline = load(output / "action_repair_prepare.json")["native_baseline"]
    allowed = {f"{slot:04d}.png" for slot in profile["slots"]}
    for name, info in baseline.items():
        if name not in allowed:
            assert records[name] == info, f"Non-target native/mtime changed: {name}"
    count = assert_protected(output)
    return dict(
        checked_at=stamp(), package=rel(package_path), version=profile["version"],
        sha256=sha(package_path), bytes=package_path.stat().st_size, entries=len(rows),
        base_package=profile["base"], base_sha256=profile["base_sha256"],
        skin_paths_updated=len(skin_rows), unchanged_other_payloads=preserved,
        frames=profile["frames"], all_paths_and_order_preserved=True,
        decoded_alpha_and_visible_rgba_exact=True, full_rgba_max_delta=max(rgba_deltas),
        rgba_note="Alpha and visible RGBA are exact; transparent hidden RGB is nonvisual.",
        native_sha256={name: info["sha256"] for name, info in records.items()},
        non_target_native_bytes_and_mtimes_preserved=profile["frames"]-len(allowed),
        changed_native_slots=applied["changed_native_slots"], protected_files_unchanged=count,
        installed=False, game_runtime_validated=False, official_packages_changed=False,
        buff_changed=False, user_aesthetic_approved=False,
    )


def package(profile):
    output = ROOT / profile["output"]
    target = output / profile["name"]
    temporary = target.with_suffix(".NPK.building")
    assert not target.exists() and not temporary.exists(), "Refuse overwrite/retry of an existing package"
    applied = load(output / "action_repair_apply.json")
    assert applied["root_review_selected"]
    before = native_records(output / "native_frames", profile["frames"])
    assert before == applied["native_records"]
    assert_protected(output)
    base = ROOT / profile["base"]
    assert sha(base) == profile["base_sha256"]
    body, unique, frame_records = body_img(output / "native_frames", profile["frames"])
    original = base.read_bytes()
    rows = read_npk(base)
    assert len(rows) == profile["entries"]
    assert sum(r["path"].startswith(profile["skin_prefix"]) for r in rows) == profile["skin_count"]
    entries = [(row["path"], body if row["path"].startswith(profile["skin_prefix"]) else
                original[row["offset"]:row["offset"]+row["length"]]) for row in rows]
    temporary.write_bytes(write_shared_npk(entries))
    report = validate(profile, temporary)
    assert native_records(output / "native_frames", profile["frames"]) == before
    temporary.replace(target)
    report.update(package=rel(target), unique_character_frames=unique)
    save(output / "validation.json", report)
    (output / (target.name + ".sha256")).write_text(report["sha256"]+"  "+target.name+"\n", encoding="ascii")
    save(output / "character_frame_encoding.json", dict(frames=frame_records, skin_payload_sha256=hashlib.sha256(body).hexdigest()))
    frozen = output / "frozen_code"
    frozen.mkdir()
    shutil.copy2(Path(__file__), frozen / Path(__file__).name)
    save(output / "handoff.json", dict(
        status="local_candidate_packaged_waiting_for_user_review", profile=profile,
        validation="validation.json", character_encoding="character_frame_encoding.json",
        prepared_baseline="action_repair_prepare.json", applied_inputs="action_repair_apply.json",
        protected_baseline="protected_baseline.json", frozen_builder_sha256=sha(frozen / Path(__file__).name),
        sha256=report["sha256"], bytes=report["bytes"],
        note="Update existing design version/out separately, refresh its exact worker, then append fixed issue events. Never mark user verification here.",
        installed=False, game_runtime_validated=False, user_aesthetic_approved=False,
    ))
    print(json.dumps({k: v for k, v in report.items() if k != "native_sha256"}, ensure_ascii=False, indent=2))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "apply", "package", "verify"))
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("--approved", action="store_true", help="Root reviewed exact repair candidates")
    parser.add_argument("--native-dir", type=Path)
    parser.add_argument("--hd-root", type=Path)
    parser.add_argument("--selection-root", type=Path)
    parser.add_argument("--repair-manifest", type=Path)
    args = parser.parse_args()
    profile = PROFILES[args.profile]
    if args.action == "prepare":
        prepare(profile)
    elif args.action == "apply":
        assert args.native_dir, "--native-dir is required"
        apply(profile, args)
    elif args.action == "package":
        package(profile)
    else:
        report = validate(profile, ROOT / profile["output"] / profile["name"])
        assert report["sha256"] == load(ROOT / profile["output"] / "validation.json")["sha256"]
        print(json.dumps({k: v for k, v in report.items() if k != "native_sha256"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
