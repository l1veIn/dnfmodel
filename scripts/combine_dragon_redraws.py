"""Stage two independently reviewed dragon redraws without altering their sources."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = set(range(13)) | set(range(123, 132)) | set(range(232, 236))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path):
    return path.resolve().relative_to(ROOT).as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--breath-freeze", required=True, type=Path)
    parser.add_argument("--motion-freeze", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = args.out.resolve()
    assert output.is_relative_to(ROOT / "output")
    assert not output.exists(), "Never overwrite staged or reviewed art"
    sources = []
    slots = set()
    for frozen_path in (args.breath_freeze, args.motion_freeze):
        frozen_path = frozen_path.resolve(strict=True)
        frozen = json.loads(frozen_path.read_text(encoding="utf-8-sig"))
        for name, digest in frozen["files_sha256"].items():
            assert sha(ROOT / name) == digest, f"Frozen source changed: {name}"
        native = ROOT / frozen["native_dir"]
        hd = ROOT / frozen["hd_root"]
        selection = ROOT / frozen["selection_root"]
        incoming = {int(p.stem) for p in native.glob("*.png")}
        assert incoming == set(frozen["slots"])
        assert not slots.intersection(incoming), "Overlapping producers"
        slots.update(incoming)
        sources.append((frozen_path, frozen, native, hd, selection))
    assert slots == EXPECTED
    assert sha(sources[0][2] / "0000.png") == sha(sources[1][2] / "0004.png"), "Idle/nod canonical mismatch"
    (output / "native_frames").mkdir(parents=True)
    source_records = []
    for frozen_path, frozen, native, hd, selection in sources:
        for png in sorted(native.glob("*.png")):
            shutil.copy2(png, output / "native_frames" / png.name)
        for png in sorted(hd.rglob("*.png")):
            assert png.stem.isdecimal() and int(png.stem) in EXPECTED, png
            target = output / "clips" / png.relative_to(hd)
            assert not target.exists(), target
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, target)
        for selected in sorted(selection.rglob("selection.json")):
            target = output / "clips" / selected.relative_to(selection)
            assert not target.exists(), target
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(selected, target)
        source_records.append(dict(path=rel(frozen_path), sha256=sha(frozen_path), slots=frozen["slots"]))
    files = {rel(p): sha(p) for p in sorted(output.rglob("*")) if p.is_file()}
    files[rel(Path(__file__))] = sha(Path(__file__))
    record = dict(
        status="root_reviewed_staging_pending_user_review",
        frozen_at=datetime.now().astimezone().isoformat(),
        producer_freezes=source_records,
        native_dir=rel(output / "native_frames"), hd_root=rel(output / "clips"),
        selection_root=rel(output / "clips"), slots=sorted(EXPECTED), frame_count=len(EXPECTED),
        idle_nod_first_native_exact=True, installed=False, new_65535_calls=0,
        files_sha256=files,
    )
    (output / "frozen.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(staged=rel(output), frames=len(EXPECTED), files=len(files))))


if __name__ == "__main__":
    main()
