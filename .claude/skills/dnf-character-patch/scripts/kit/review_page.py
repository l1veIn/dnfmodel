"""A local page for the user to review a finished patch one action at a time: source and new play in step, and verdicts land in design/<id>/review.json.

An action is a clip's "action" field, or its name. Sheets often split one action into several clips, and the user thinks in actions.
Frames are read fresh when final has rewritten them, so the page stays open across fixes: reload it to see them.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from .config import P
from .source import armed, native_world

PAGE = Path(__file__).resolve().parents[2] / "assets/review_page.html"
REVIEW = P.run / "review.json"
FRAMES = P.out / "native_frames"
PAD = 6
STATUSES = ("", "pass", "fix")
LIMIT = 1_000_000
render_lock = threading.Lock()
frame_cache = {}
data_cache = {}
version_seen = [-10.0, 0]


def _new(i):
    return Image.open(FRAMES / f"{i:04d}.png").convert("RGBA")


def _version():
    """Changes whenever final or a repair rewrites a frame. Scanning the folder for every frame request would be slow, so it is held for a second."""
    now = time.monotonic()
    if now - version_seen[0] > 1:
        version_seen[:] = [now, int(max((p.stat().st_mtime for p in FRAMES.glob("*.png")), default=0))]
    return version_seen[1]


def _reviews():
    return json.loads(REVIEW.read_text("utf-8")) if REVIEW.exists() else {}


def _frame_notes():
    """Height against the sprite, hand fit and source cell for each frame, so a verdict can name the cause."""
    notes = {}
    for clip in P.clips():
        path = P.out / "clips" / clip["id"] / "selection.json"
        if not path.exists():
            continue
        for row in json.loads(path.read_text("utf-8"))["frames"]:
            hands = row.get("hands") or []
            notes[row["slot"]] = dict(source=str(row.get("video_frame", "")), hand=hands[0].get("state") if hands else None, gap=hands[0].get("gap") if hands else None)
    reuse = P.run / "reuse.json"
    if reuse.exists():
        for target, origin in json.loads(reuse.read_text("utf-8")).items():
            notes[int(target)] = dict(source=f"复用第 {origin + 1} 帧", **{k: notes.get(origin, {}).get(k) for k in ("hand", "gap")})
    return notes


def _actions():
    version = _version()
    if data_cache.get("version") == version:
        return data_cache["actions"]
    notes = _frame_notes()
    groups = {}
    for clip in sorted(P.clips(), key=lambda c: c["start"]):
        groups.setdefault(clip.get("action", clip["name"]), []).extend(range(clip["start"], clip["end"] + 1))
    actions = []
    for name, frames in groups.items():
        box = None
        rows = []
        for i in frames:
            native, new = native_world(i), _new(i)
            old_box, new_box = native.getbbox(), new.getbbox()
            for image in (armed(native, i), armed(new, i)):
                b = image.getbbox()
                box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
            rows.append(dict(i=i, ratio=round((new_box[3] - new_box[1]) / (old_box[3] - old_box[1]), 2), **notes.get(i, {})))
        box = (max(0, box[0] - PAD), max(0, box[1] - PAD), min(P.canvas, box[2] + PAD), min(P.canvas, box[3] + PAD))
        actions.append(dict(name=name, frames=rows, box=box))
    data_cache.update(version=version, actions=actions)
    return actions


def _frame_png(kind, weapon, i):
    key = (kind, weapon, i, _version())
    if key not in frame_cache:
        with render_lock:
            image = native_world(i) if kind == "native" else _new(i)
            if weapon:
                image = armed(image, i)
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            if len(frame_cache) > 2000:
                frame_cache.clear()
            frame_cache[key] = buffer.getvalue()
    return frame_cache[key]


def _save(payload):
    """One action's verdict. Everything is checked against the known actions, so a stray request cannot write anything else."""
    actions = {a["name"]: a for a in _actions()}
    name = payload.get("action")
    if name not in actions:
        raise ValueError("unknown action")
    status, note, flags = payload.get("status", ""), payload.get("note", ""), payload.get("frames", [])
    allowed = {row["i"] for row in actions[name]["frames"]}
    if status not in STATUSES or not isinstance(note, str) or len(note) > 5000 or not isinstance(flags, list) or not set(flags) <= allowed:
        raise ValueError("bad verdict")
    reviews = _reviews()
    reviews[name] = dict(status=status, note=note, frames=sorted(flags), first_frame_user=actions[name]["frames"][0]["i"] + 1, updated=time.strftime("%Y-%m-%d %H:%M:%S"))
    temporary = REVIEW.with_suffix(".tmp")
    temporary.write_text(json.dumps(reviews, ensure_ascii=False, indent=1), "utf-8")
    os.replace(temporary, REVIEW)
    return reviews[name]


class Handler(BaseHTTPRequestHandler):
    # Keep connections open. A page on "localhost" tries IPv6 first on Windows, which costs about 0.3s for each new connection, and an action loads dozens of frames.
    protocol_version = "HTTP/1.1"

    def _send(self, body, kind="application/json; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, code=200):
        self._send(json.dumps(value, ensure_ascii=False).encode("utf-8"), code=code)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/data":
            weapon = P.weapon["label"] if P.weapon else None
            return self._json(dict(title=P.title, version=_version(), weapon=weapon, actions=_actions(), reviews=_reviews()))
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "frame" and parts[1] in ("native", "new") and parts[2] in ("0", "1") and parts[3].endswith(".png"):
            stem = parts[3][:-4]
            if stem.isdigit() and int(stem) < P.frames:
                return self._send(_frame_png(parts[1], parts[2] == "1", int(stem)), "image/png")
        return self._json(dict(error="not found"), 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if urlparse(self.path).path != "/api/review" or length > LIMIT:
            return self._json(dict(error="not found"), 404)
        try:
            return self._json(_save(json.loads(self.rfile.read(length))))
        except (ValueError, TypeError) as error:
            return self._json(dict(error=str(error)), 400)

    def log_message(self, *args):
        pass


def _warm():
    """Render everything once, so changing action never shows an empty picture."""
    for weapon in (True, False):
        for i in range(P.frames):
            for kind in ("native", "new"):
                _frame_png(kind, weapon, i)


def serve(port=8798):
    """Bound to this computer only."""
    print(f"http://127.0.0.1:{port}/  verdicts go to {REVIEW}", flush=True)
    threading.Thread(target=_warm, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
