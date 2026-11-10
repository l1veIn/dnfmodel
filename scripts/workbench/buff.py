"""Registered project buff portraits, served by the workbench without game writes.

Registrations live in design/<design>/workbench/buff.json. A registration names
one manifest under output/, never a directory to scan or a browser-supplied path.
Encoding and in-game verification are separate states.
"""
from __future__ import annotations

import json
import hashlib
from functools import lru_cache
import math
from pathlib import Path
import re
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output"
DESIGN = ROOT / "design"
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,59}\Z")
SOURCE_FILES = {"animation": "preview.webp", "sheet": "sheet.png", "contact": "contact.jpg", "mov": "portrait_rgba.mov", "source": "source.png"}
MAX_JSON_BYTES = 2_000_000


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("bad buff identifier")
    return value


def _json(path):
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("buff metadata is too large")
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("bad buff metadata")
    return value


def _inside(base, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("bad buff file")
    rel = Path(relative)
    if rel.is_absolute() or any(part in ("..", ".") for part in rel.parts):
        raise ValueError("bad buff file")
    result = (base / rel).resolve()
    if base.resolve() not in result.parents:
        raise ValueError("buff file is outside its registered output")
    return result


def _registrations(project):
    records, seen = [], set()
    designs = list(dict.fromkeys(([project["current"]] if project.get("current") else []) + project.get("designs", [])))
    for design in designs:
        path = DESIGN / _identifier(design) / "workbench" / "buff.json"
        if not path.exists():
            continue
        entries = _json(path).get("assets", [])
        if not isinstance(entries, list) or len(entries) > 32:
            raise ValueError("bad buff registration")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("bad buff registration")
            ident = _identifier(entry.get("id"))
            if ident not in seen:
                seen.add(ident)
                records.append(dict(entry, design=design))
    return records


def count(project):
    """Cheap dashboard count; no output scan or frame/encoding inspection."""
    return len(_registrations(project))


def _record(project, ident):
    _identifier(ident)
    entry = next((e for e in _registrations(project) if e["id"] == ident), None)
    if entry is None:
        raise KeyError("buff asset")
    return entry


def _manifest(entry):
    path = _inside(ROOT, entry.get("manifest"))
    if OUTPUT.resolve() not in path.parents or path.name != "manifest.json":
        raise ValueError("buff manifest must be registered under output")
    if not path.is_file():
        raise KeyError("buff manifest")
    return path, _json(path)


def _dimensions(manifest):
    frames, size, fps = manifest.get("frames"), manifest.get("size"), manifest.get("fps")
    if type(frames) is not int or not 1 <= frames <= 1000:
        raise ValueError("bad buff frame count")
    if not isinstance(size, list) or len(size) != 2 or any(type(n) is not int or not 1 <= n <= 4096 for n in size):
        raise ValueError("bad buff dimensions")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 0 < fps <= 120:
        raise ValueError("bad buff frame rate")
    return frames, size[0], size[1], fps


@lru_cache(maxsize=128)
def _hash(path_text, size, modified_ns):
    with Path(path_text).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _matches_hash(path, expected):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        return False
    try:
        stat = path.stat()
        return _hash(str(path), stat.st_size, stat.st_mtime_ns) == expected
    except OSError:
        return False


def _encoding(entry, folder, manifest):
    report_path = _inside(ROOT, entry.get("encoding_report", str((folder / "encoding_report.json").relative_to(ROOT)).replace("\\", "/")))
    if report_path.parent != folder or report_path.name != "encoding_report.json":
        raise ValueError("encoding report must be beside its registered manifest")
    if not report_path.exists():
        return report_path, None, None, False, []
    report = _json(report_path)
    warnings, candidate = [], None
    if report.get("file"):
        candidate = _inside(folder, report["file"])
        if candidate.suffix.lower() not in (".bik", ".bk2"):
            raise ValueError("bad encoded buff file extension")
    frames, width, height, fps = _dimensions(manifest)
    matches = (report.get("status") == "encoded" and report.get("verified") is True
               and report.get("alpha", report.get("has_alpha")) is True and report.get("codec") == "binkvideo"
               and report.get("frames") == frames and report.get("width") == width and report.get("height") == height
               and report.get("fps") == fps and report.get("audio_streams", 0) == 0
               and candidate is not None and candidate.is_file())
    if matches:
        # A file rename is not encoding. Check the codec signature as well as
        # the explicit decode-verification report, without loading the movie.
        with candidate.open("rb") as stream:
            matches = stream.read(4) in (b"BIKb", b"BIKd", b"BIKf", b"BIKg", b"BIKh", b"BIKi")
        if report.get("sha256") is not None:
            matches = matches and _matches_hash(candidate, report["sha256"])
        if report.get("source_manifest_sha256") is not None:
            matches = matches and _matches_hash(folder / "manifest.json", report["source_manifest_sha256"])
        if report.get("source_frames_sha256") is not None:
            matches = matches and report["source_frames_sha256"] == manifest.get("frame_sha256")
        # The native player reads PNGs. If one is edited after encoding, a
        # still-valid movie report must not claim it represents that new look.
        source_hashes = manifest.get("frame_sha256")
        if source_hashes is not None:
            matches = matches and isinstance(source_hashes, list) and len(source_hashes) == frames
            if matches:
                matches = all(_matches_hash(_inside(folder, f"frames/frame_{k:04d}.png"), expected)
                              for k, expected in enumerate(source_hashes))
    if not matches:
        warnings.append("编码报告或源素材尚未通过完整核对，不能标为已编码。")
    return report_path, report, candidate, matches, warnings


def _file_url(project, ident, kind, stamp, **extra):
    query = urlencode(dict(kind=kind, v=stamp, **extra))
    return f"/api/projects/{quote(project['id'], safe='')}/buff/{quote(ident, safe='')}/file?{query}"


def _video_root():
    # Share the game browser's configured root, but keep registration counts
    # cheap and independent of game-resource imports.
    from render import GAME
    return (GAME.parent / "Video" / "Character").resolve()


def _installation(folder, manifest, bink, encoded):
    """Read a separate install receipt; frozen encoding inputs remain untouched."""
    receipt_path = folder.parent / "installation.json"
    result = dict(installed=False, status="not_installed", targets=0, matching_targets=0)
    if not receipt_path.is_file():
        return result, []
    try:
        receipt = _json(receipt_path)
        if receipt.get("installed") is not True:
            return dict(result, status="not_installed"), []
        expected = receipt.get("sha256")
        source = Path(receipt["source"]).resolve()
        if not encoded or bink is None or source != bink.resolve() or not _matches_hash(source, expected):
            return dict(result, status="stale"), ["安装记录对应的成片已变化，安装状态待重新核对。"]
        target_records = manifest.get("targets")
        targets = ([t if isinstance(t, str) else t.get("relative_to_video_character") if isinstance(t, dict) else None
                    for t in target_records] if isinstance(target_records, list) else None)
        rows = receipt.get("files")
        if (not isinstance(targets, list) or not targets or any(not isinstance(t, str) for t in targets)
                or len(set(targets)) != len(targets) or not isinstance(rows, list)
                or len(rows) != len(targets) or any(not isinstance(r, dict) for r in rows)):
            raise ValueError("安装目标清单不完整")
        by_relative = {row.get("relative"): row for row in rows}
        if len(by_relative) != len(rows) or set(by_relative) != set(targets):
            raise ValueError("安装目标与已登记素材不一致")
        root = _video_root()
        if Path(receipt["game_root"]).resolve() != root:
            raise ValueError("安装目录与当前游戏目录不一致")
        matching = 0
        for relative in targets:
            target = _inside(root, relative)
            row = by_relative[relative]
            if Path(row["target"]).resolve() != target or row.get("after_sha256") != expected:
                raise ValueError("安装目标或版本记录不一致")
            matching += int(_matches_hash(target, expected))
        installed = matching == len(targets)
        result.update(installed=installed, status="installed" if installed else "partial",
                      targets=len(targets), matching_targets=matching, installed_at=receipt.get("installed_at"))
        warnings = [] if installed else [f"安装文件核对：{matching}/{len(targets)} 符合此版本。"]
        return result, warnings
    except (OSError, ValueError, TypeError, KeyError) as error:
        return dict(result, status="invalid"), [f"安装记录无法核对：{error}"]


def _summary(project, entry):
    result = dict(id=entry["id"], name=entry.get("name", "buff 立绘"), version=entry.get("version", ""),
                  purpose=entry.get("purpose", "加 buff 立绘"), profession=project.get("profession"),
                  title=entry.get("name", "buff 立绘"), frames=0, width=0, height=0, fps=0, duration_seconds=0,
                  status="unavailable", status_label="素材未就绪", encoding_status_label="未编码",
                  installed=False, ingame_verified=False, warnings=[], targets=[], files={}, frame_url=None,
                  encoded_frame_url=None, stamp="missing")
    try:
        manifest_path, manifest = _manifest(entry)
        folder = manifest_path.parent
        frames, width, height, fps = _dimensions(manifest)
        report_path, report, bink, verified, warnings = _encoding(entry, folder, manifest)
        paths = {kind: _inside(folder, name) for kind, name in SOURCE_FILES.items()}
        paths.update(manifest=manifest_path, encoding_report=report_path)
        if verified:
            paths["bink"] = bink
        if report and verified:
            if report.get("decoded_preview"):
                paths["encoded_animation"] = _inside(folder, report["decoded_preview"])
        source_frames = [_inside(folder, f"frames/frame_{k:04d}.png") for k in range(frames)]
        decoded_dir = _inside(folder, report["decoded_frames"]) if verified and report.get("decoded_frames") else None
        files_for_stamp = [p for p in paths.values() if p and p.exists()]
        files_for_stamp.extend(p for p in source_frames if p.is_file())
        if decoded_dir and decoded_dir.is_dir():
            files_for_stamp.extend(p for k in range(frames) if (p := _inside(decoded_dir, f"frame_{k:04d}.png")).is_file())
        token = [(str(p.relative_to(folder)), p.stat().st_size, p.stat().st_mtime_ns) for p in files_for_stamp]
        stamp = hashlib.sha256(json.dumps(token).encode("utf-8")).hexdigest()[:20]
        missing = [k for k, path in enumerate(source_frames) if not path.is_file()]
        if missing:
            warnings.append(f"缺少 {len(missing)} 帧源 PNG。")
        source_warnings = manifest.get("warnings", [])
        if isinstance(source_warnings, list):
            warnings = [w for w in source_warnings[:50] if isinstance(w, str)] + warnings
        source_ready = not missing and paths["animation"].is_file()
        status = "encoded" if verified and source_ready else "prepared" if source_ready else "unavailable"
        installation, install_warnings = _installation(folder, manifest, bink, verified)
        warnings += install_warnings
        result.update(title=manifest.get("title", result["name"]), frames=frames, width=width, height=height, fps=fps,
                      duration_seconds=frames / fps, status=status, status_label={"encoded": "已编码 · 待实机", "prepared": "已准备 · 待编码", "unavailable": "素材未就绪"}[status],
                      encoding_status_label="编码回读通过" if verified else "未编码" if report is None else "编码待核对",
                      warnings=warnings, targets=manifest.get("targets", []), stamp=stamp,
                      installed=installation["installed"], installation=installation,
                      license_note=manifest.get("license_note", ""), available_frames=frames - len(missing),
                      frame_url=_file_url(project, entry["id"], "frame", stamp, k="{k}"),
                      files={kind: _file_url(project, entry["id"], kind, stamp) if path.is_file() else None for kind, path in paths.items()})
        # Keep the placeholder legible to clients instead of percent-encoding it.
        result["frame_url"] = result["frame_url"].replace("%7Bk%7D", "{k}")
        for kind in ("bink", "encoded_animation"):
            result["files"].setdefault(kind, None)
        if decoded_dir:
            if decoded_dir.is_dir():
                result["encoded_frame_url"] = _file_url(project, entry["id"], "encoded_frame", stamp, k="{k}").replace("%7Bk%7D", "{k}")
    except (OSError, ValueError, TypeError, KeyError) as error:
        result["warnings"] = [f"素材信息无法读取：{error}"]
    return result


def assets(project):
    return [_summary(project, entry) for entry in _registrations(project)]


def detail(project, ident):
    return _summary(project, _record(project, ident))


def file(project, ident, kind, frame=None):
    """Resolve only a registered asset's known files; never accept a path query."""
    entry = _record(project, ident)
    manifest_path, manifest = _manifest(entry)
    folder = manifest_path.parent
    frames, _, _, _ = _dimensions(manifest)
    report_path, report, bink, verified, _ = _encoding(entry, folder, manifest)
    if kind in ("frame", "encoded_frame"):
        if type(frame) is not int or not 0 <= frame < frames:
            raise ValueError("buff frame is out of range")
        relative = f"frames/frame_{frame:04d}.png"
        if kind == "encoded_frame":
            if not verified or not report.get("decoded_frames"):
                raise KeyError("decoded buff frames")
            relative = f"{report['decoded_frames']}/frame_{frame:04d}.png"
        path = _inside(folder, relative)
    elif kind in SOURCE_FILES:
        path = _inside(folder, SOURCE_FILES[kind])
    elif kind == "manifest":
        path = manifest_path
    elif kind == "encoding_report":
        path = report_path
    elif kind == "bink" and verified:
        path = bink
    elif kind == "encoded_animation" and verified and report.get("decoded_preview"):
        path = _inside(folder, report["decoded_preview"])
    else:
        raise KeyError("buff file kind")
    if not path.is_file():
        raise KeyError("buff file")
    return path
