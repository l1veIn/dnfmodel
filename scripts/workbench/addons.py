"""Explicit shared resource packs, separate from the character-version history.

Only published manifests registered locally can supply preview or download
paths. Registration does not imply installation, visual approval or game QA.
Entries with missing local build files are omitted until those files exist.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import threading

import categories

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "design" / "workbench_addons.json"
GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
_cache = {}
_lock = threading.RLock()


def _token(path):
    stat = path.stat()
    return str(path), stat.st_size, stat.st_mtime_ns


def _output(value, suffix):
    if not isinstance(value, str) or "\\" in value or not value:
        raise ValueError("Addon paths must be workspace-relative POSIX paths")
    relative = Path(value)
    if relative.anchor or any(p in (".", "..") for p in relative.parts):
        raise ValueError("Addon paths must stay inside workspace output")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to((ROOT / "output").resolve()) or path.suffix.lower() != suffix:
        raise ValueError("Addon paths must stay inside workspace output")
    return path


def _json(path):
    if path.stat().st_size > 2_000_000:
        raise ValueError("Addon manifest is unexpectedly large")
    return json.loads(path.read_text("utf-8"))


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _package(manifest_path, ident):
    try:
        manifest = _json(manifest_path)
    except FileNotFoundError:
        return None
    if (not isinstance(manifest, dict) or manifest.get("schema") != 1
            or manifest.get("status") not in ("packaged_local_candidate", "user_approved")):
        raise ValueError("Only a packaged addon manifest can be registered")
    if manifest.get("id") != ident:
        raise ValueError("Addon ID differs from its published manifest")
    package = _output(manifest.get("npk"), ".npk")
    if not re.fullmatch(r"A_[A-Za-z0-9_.-]+\.NPK", package.name):
        raise ValueError("Addon package must have an A_*.NPK name")
    digest = manifest.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Addon manifest must declare a SHA-256 for its package")
    try:
        key = ("package", _token(manifest_path), _token(package))
    except FileNotFoundError:
        return None
    hit = _cache.get(key)
    if hit is not None:
        return hit
    if _sha(package) != digest:
        raise ValueError("Addon package hash differs from its published manifest")
    sys.path.insert(0, str(ROOT / "scripts"))
    from dnf_resources import read_npk
    entries = read_npk(package)
    by_path = {entry["path"]: entry for entry in entries}
    if len(entries) != len(by_path):
        raise ValueError("Addon contains duplicate IMG paths")
    edits = {entry["path"]: entry for entry in manifest.get("edits", [])}
    if set(edits) != set(by_path):
        raise ValueError("Addon manifest must describe every actual NPK entry")
    with package.open("rb") as stream:
        for name, edit in edits.items():
            if categories.classify(name) != "portrait" or not edit.get("changed_frames"):
                raise ValueError("Shared portrait addons need real, scoped portrait edits")
            entry = by_path[name]
            count = entry.get("frame_count")
            changed = edit["changed_frames"]
            if count != edit.get("frame_count") or not count or any(type(k) is not int or not 0 <= k < count for k in changed):
                raise ValueError("Addon frame metadata differs from the actual IMG")
            stream.seek(entry["offset"])
            raw = stream.read(entry["length"])
            if hashlib.sha256(raw).hexdigest() != edit.get("payload_sha256"):
                raise ValueError("Addon IMG differs from its published manifest")
            if edit.get("payload_sha256") == edit.get("source_payload_sha256"):
                raise ValueError("Unchanged official IMG cannot count as an addon edit")
    result = manifest, package, edits
    _cache[key] = result
    return result


def _registered():
    if not REGISTRY.exists():
        return []
    registry = _json(REGISTRY)
    if registry.get("schema") != 1 or not isinstance(registry.get("addons"), list) or len(registry["addons"]) > 32:
        raise ValueError("Invalid addon registry")
    result = []
    seen = set()
    for row in registry["addons"]:
        if not row.get("enabled", True):
            continue
        ident = row.get("id", "")
        if not re.fullmatch(r"[a-z0-9_]{1,80}", ident) or ident in seen:
            raise ValueError("Addon IDs must be unique safe identifiers")
        seen.add(ident)
        manifest_path = _output(row.get("manifest"), ".json")
        loaded = _package(manifest_path, ident)
        if loaded is None:
            continue
        manifest, package, edits = loaded
        result.append((ident, manifest_path, manifest, package, edits))
    return result


def for_project(project):
    """Published addon files and actual edited paths relevant to one project."""
    with _lock:
        allowed = set(categories.portrait_paths([project.get("profession")]))
        result = []
        used = set()
        for ident, manifest_path, manifest, package, edits in _registered():
            targets = manifest.get("projects", {}).get(project["id"], {})
            if not isinstance(targets, dict):
                raise ValueError("Addon project targets must be explicit path/frame maps")
            paths = []
            for path, indices in targets.items():
                if path not in allowed or path not in edits or not isinstance(indices, list):
                    raise ValueError("Addon project targets contain an unrelated portrait")
                if not indices or any(type(k) is not int or k < 0 for k in indices):
                    raise ValueError("Addon target frame indices are invalid")
                if (set(indices) != set(edits[path].get("project_targets", {}).get(project["id"], []))
                        or any(k >= edits[path]["frame_count"] for k in indices)):
                    raise ValueError("Addon project targets differ from the signed edit scope")
                changed = set(edits[path]["changed_frames"])
                if not changed.intersection(indices):
                    raise ValueError("Addon project has no changed target frames for this path")
                paths.append(path)
            if not paths:
                continue
            if used.intersection(paths):
                raise ValueError("Two enabled addons overlap the same project's portrait path")
            used.update(paths)
            game_file = GAME / package.name
            installed = None
            if game_file.exists():
                key = ("installed", _token(game_file))
                if key not in _cache:
                    _cache[key] = _sha(game_file)
                installed = "same" if _cache[key] == manifest["sha256"] else "different"
            status = "本地候选 · 未安装" if installed is None else "已安装 · 待实机验证" if installed == "same" else "游戏同名文件与本地不同"
            result.append(dict(id=ident, label=manifest.get("label", "共享界面立绘"),
                               name=package.name, path=package.relative_to(ROOT).as_posix(), npk=str(package),
                               manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=manifest["sha256"],
                               size=package.stat().st_size, paths=sorted(paths), targets=targets,
                               labels={path: edits[path].get("frame_labels", {}) for path in paths},
                               installed=installed, status=status, ingame_verified=False))
        return result


def file_for_project(project, ident):
    """A download must resolve through this project's registered whitelist."""
    if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9_]{1,80}", ident):
        raise KeyError(ident)
    row = next((row for row in for_project(project) if row["id"] == ident), None)
    if row is None:
        raise KeyError(ident)
    return Path(row["npk"])


def cache_token():
    """Changes to registry/manifest/package must invalidate game-browser mods."""
    with _lock:
        if not REGISTRY.exists():
            return None
        return (_token(REGISTRY), tuple((_token(path), _token(package)) for _, path, _, package, _ in _registered()))


def reset():
    with _lock:
        _cache.clear()
