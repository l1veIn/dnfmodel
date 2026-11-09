"""DNF patch workbench: a dashboard of every patch project, each project's progress and versions, and a review board. Design: docs/workbench_design.md.

    python scripts/workbench/server.py [--port=8800]

Files stay the source of truth: projects are listed in design/projects.json, their state is read from design/ and output/,
verdicts and issues are design/<design>/workbench/issues.jsonl. Frames come from one worker process per design folder
(scripts/workbench/worker.py), started on first use.
Bound to 127.0.0.1 only. Never writes to the game folder.
"""
from __future__ import annotations

import io
import json
import mimetypes
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import game  # noqa: E402
import issues  # noqa: E402
import progress  # noqa: E402
import studio  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
DESIGN = ROOT / "design"
OUTPUT = ROOT / "output"
LIMIT = 200_000
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
workers, workers_lock = {}, threading.Lock()
units_cache, cover_cache = {}, {}


# ---------------------------------------------------------------- design folders (review board)


def designs():
    owner = {d: p["id"] for p in progress.registry() for d in p["designs"]}
    out = []
    for path in sorted(DESIGN.glob("*/patch.json")):
        ident = path.parent.name
        data = json.loads(path.read_text("utf-8"))
        state = issues.replay(ident)
        out.append(dict(id=ident, title=data.get("title", ident), version=data.get("version"), project=owner.get(ident),
                        open=sum(1 for i in state["issues"] if i["status"] == "open"), fixed=sum(1 for i in state["issues"] if i["status"] == "fixed"),
                        events=bool(issues.read_events(ident))))
    return out


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def worker(ident):
    """The design's worker, started if needed. A worker that went idle and exited is started again."""
    if not (DESIGN / ident / "patch.json").exists():
        raise KeyError(ident)
    with workers_lock:
        w = workers.get(ident)
        if w and w["process"].poll() is None:
            return w["port"]
        port = free_port()
        log = DESIGN / ident / "workbench"
        log.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / "worker.py"), ident, str(port)], cwd=ROOT,
                                   stdout=open(log / "worker.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
        workers[ident] = dict(process=process, port=port)
        units_cache.pop(ident, None)
    for _ in range(240):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=1).read()
            return port
        except (urllib.error.URLError, OSError):
            if process.poll() is not None:
                raise RuntimeError(f"worker for {ident} exited; see design/{ident}/workbench/worker.log")
            time.sleep(0.5)
    raise RuntimeError(f"worker for {ident} did not start")


def ask(ident, path, **query):
    port = worker(ident)
    url = f"http://127.0.0.1:{port}{path}" + (f"?{urlencode(query)}" if query else "")
    with urllib.request.urlopen(url, timeout=600) as r:
        return r.read(), r.headers.get("Content-Type")


def units(ident, refresh=False):
    if refresh or ident not in units_cache:
        body, _ = ask(ident, "/units", **({"refresh": 1} if refresh else {}))
        units_cache[ident] = json.loads(body)
    return units_cache[ident]


def unit_index(ident):
    return {(a["id"], u["id"]): u for a in units(ident) for u in a["units"]}


def design_state(ident, refresh=False):
    listing = units(ident, refresh)
    state = issues.replay(ident)
    for a in listing:
        for u in a["units"]:
            u["review"] = issues.unit_summary(state, a["id"], u["id"], u["version"])
    return dict(assets=listing, issues=state["issues"], units=state["units"])


def post_event(ident, payload):
    index = unit_index(ident)
    event = issues.validate(payload, index, by="user")
    if event["op"] in ("reopen", "verify", "withdraw", "note") and not any(i["issue"] == event["issue"] for i in issues.replay(ident)["issues"]):
        raise ValueError("unknown issue")
    with issues.LOCK:
        if event["op"] == "open":
            event["issue"] = issues.next_issue(ident)
        return issues.append(ident, event)


# ---------------------------------------------------------------- projects (dashboard)


def dashboard():
    projects = [progress.summary(p) for p in progress.registry()]
    known = {v["name"] for p in progress.registry() for v in progress.versions(p)}
    stems = [s.lower() for p in progress.registry() for s in p["npk"]]
    others = [n for n in progress.game_patches() if n not in known and not any(n.lower().startswith(s) for s in stems)]
    return dict(projects=projects, game=progress.game_patches(), others=others)


def version_file(pid, name, kind):
    """A built NPK or its release zip, only if it belongs to the project (the name comes from the page)."""
    v = next((v for v in progress.versions(progress.project(pid)) if v["name"] == name), None)
    if v is None:
        raise KeyError(name)
    rel = v["path"] if kind == "npk" else v["zip"]
    if not rel:
        raise KeyError(f"{name} has no {kind}")
    return ROOT / rel


def cover_png(pid):
    path = progress.cover(progress.project(pid))
    if path is None:
        raise KeyError("cover")
    key = (str(path), path.stat().st_mtime)
    if cover_cache.get(pid, (None,))[0] != key:
        from PIL import Image
        image = Image.open(path).convert("RGBA")
        box = image.getbbox() or (0, 0, image.width, image.height)
        image = image.crop(box)
        image.thumbnail((360, 360), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        cover_cache[pid] = (key, buffer.getvalue())
    return cover_cache[pid][1]


def add_gate(pid, payload):
    p = progress.project(pid)
    if not p.get("current"):
        raise ValueError("archived project")
    names = {v["name"] for v in progress.versions(p)}
    if payload.get("version") not in names or payload.get("gate") not in ("ingame", "ingame_failed"):
        raise ValueError("bad gate")
    note = payload.get("note", "")
    if not isinstance(note, str) or len(note) > issues.NOTE_LIMIT:
        raise ValueError("bad note")
    event = dict(t=time.strftime("%Y-%m-%d %H:%M:%S"), gate=payload["gate"], version=payload["version"], note=note, by="user")
    path = DESIGN / p["current"] / "workbench" / "gates.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with issues.LOCK, path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def reveal(pid, payload):
    """Open Explorer with the file selected. The path is resolved from the project's own versions, never taken from the page."""
    target = version_file(pid, payload.get("name"), payload.get("kind", "npk"))
    subprocess.Popen(["explorer", "/select,", str(target)])
    return dict(opened=str(target.relative_to(ROOT)))


def static_output(rel):
    """Comparison pages under output/<build>/preview/ only."""
    path = (OUTPUT / rel).resolve()
    if OUTPUT.resolve() not in path.parents or "preview" not in path.relative_to(OUTPUT.resolve()).parts or not path.is_file():
        raise KeyError(rel)
    return path


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, body, kind="application/json; charset=utf-8", code=200, cache="no-store", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, code=200):
        self._send(json.dumps(value, ensure_ascii=False).encode("utf-8"), code=code)

    def _file(self, path, download=False):
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(size))
        if download:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(path.name)}")
        self.end_headers()
        with path.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                self.wfile.write(chunk)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        parts = [unquote(p) for p in url.path.split("/") if p]
        try:
            if not parts:
                return self._send((STATIC / "index.html").read_bytes(), TYPES[".html"])
            if parts == ["review"]:
                return self._send((STATIC / "review.html").read_bytes(), TYPES[".html"])
            if parts[0] == "static" and len(parts) == 2 and (STATIC / parts[1]).suffix in TYPES and (STATIC / parts[1]).exists():
                return self._send((STATIC / parts[1]).read_bytes(), TYPES[(STATIC / parts[1]).suffix])
            if parts[0] == "output":
                return self._file(static_output("/".join(parts[1:])))
            if parts == ["api", "dashboard"]:
                return self._json(dashboard())
            if parts[:2] == ["api", "projects"] and len(parts) >= 3:
                pid = parts[2]
                if len(parts) == 3:
                    return self._json(progress.detail(progress.project(pid)))
                if parts[3] == "cover.png":
                    return self._send(cover_png(pid), "image/png", cache="max-age=60")
                if parts[3] == "download":
                    return self._file(version_file(pid, q["name"], q.get("kind", "npk")), download=True)
                if parts[3] == "doc":
                    name = q["name"]
                    if "/" in name or "\\" in name or not name.endswith(".md") or not (ROOT / "docs" / name).is_file():
                        raise KeyError(name)
                    return self._send((ROOT / "docs" / name).read_bytes(), "text/plain; charset=utf-8")
            if parts[:2] == ["api", "studio"] and len(parts) == 3:
                what = parts[2]
                if what == "roles":
                    return self._json(studio.roles())
                if what == "role":
                    r = q["role"]
                    return self._json(dict(role=studio.role(r), default=studio.default_outfit(r), overlays=studio.overlays(r), actions=studio.actions(r)))
                if what == "items":
                    return self._json(studio.items(q["role"], q["slot"], q.get("q", ""), int(q.get("offset", 0))))
                if what == "sets":
                    return self._json(studio.sets(q["role"], q.get("q", "")))
                if what == "wardrobe":
                    return self._json(studio.wardrobe())
                if what == "exports":
                    return self._json(studio.exports())
                if what == "export_file":
                    path = studio.export_file(q["folder"], q.get("kind", "npk"))
                    return self._file(path, download=q.get("kind", "npk") == "npk")
                if what == "atlas":
                    outfit = json.loads(q["outfit"])
                    if not isinstance(outfit, dict) or len(outfit) > 12:
                        raise KeyError("outfit")
                    return self._send(studio.atlas(q["role"], outfit, q.get("overlay", "")), "image/webp", cache="max-age=86400")
            if parts[:2] == ["api", "game"] and len(parts) == 3:
                if parts[2] == "classes":
                    return self._json(game.classes())
                if parts[2] == "skills":
                    return self._json(game.skills(q["cls"]))
                if parts[2] == "skill":
                    return self._json(game.skill(q["cls"], q["folder"]))
                if parts[2] == "videos":
                    return self._json(game.videos(q.get("cls")))
                if parts[2] == "frame":
                    return self._send(game.frame(q["path"], q["src"], int(q["k"])), "image/webp", cache="max-age=86400")
                if parts[2] == "atlas":
                    return self._send(game.atlas(q["path"], q["src"]), "image/webp", cache="max-age=86400")  # the page versions the URL
            if parts == ["api", "designs"]:
                return self._json(designs())
            if len(parts) >= 4 and parts[:2] == ["api", "p"]:
                ident, what = parts[2], parts[3]
                if what == "state":
                    return self._json(design_state(ident, refresh=q.get("refresh") == "1"))
                if what == "frame":
                    body, kind = ask(ident, "/frame", asset=q["asset"], unit=q["unit"], side=q["side"], k=q["k"], weapon=q.get("weapon", "0"))
                    return self._send(body, kind or "image/webp", cache="max-age=86400")  # the page puts the unit version in the URL
                if what == "atlas":
                    body, kind = ask(ident, "/atlas", asset=q["asset"], unit=q["unit"], side=q["side"], weapon=q.get("weapon", "0"))
                    return self._send(body, kind or "image/webp", cache="max-age=86400")
                if what == "version":
                    body, _ = ask(ident, "/version", asset=q["asset"], unit=q["unit"])
                    units_cache.pop(ident, None)
                    return self._send(body)
        except KeyError as error:
            return self._json(dict(error=f"unknown {error}"), 404)
        except (RuntimeError, urllib.error.URLError) as error:
            return self._json(dict(error=str(error)), 502)
        except (ConnectionError, BrokenPipeError):
            return None
        return self._json(dict(error="not found"), 404)

    def do_POST(self):
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.split("/") if p]
        length = int(self.headers.get("Content-Length") or 0)
        if length > LIMIT:
            return self._json(dict(error="too large"), 413)
        # A page on another site cannot post here: browsers send Origin on cross-site POSTs.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            return self._json(dict(error="cross-site request refused"), 403)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            if len(parts) == 4 and parts[:2] == ["api", "p"] and parts[3] == "event":
                event = post_event(parts[2], payload)
                return self._json(dict(event=event, state=design_state(parts[2])))
            if parts == ["api", "studio", "compose"]:
                outfit = payload.get("outfit", {})
                if not isinstance(outfit, dict) or len(outfit) > 12:
                    raise ValueError("bad outfit")
                plan = studio.compose(payload["role"], outfit, payload.get("overlay", ""))
                plan.pop("name_key", None)
                return self._json(plan)
            if parts == ["api", "studio", "current"]:
                return self._json(studio.set_current(payload))
            if parts == ["api", "studio", "export"]:
                if not isinstance(payload.get("name", ""), str) or not isinstance(payload.get("overlay", ""), str):
                    raise ValueError("bad export")
                return self._json(studio.export_outfit(payload))
            if parts == ["api", "studio", "reveal"]:
                path = studio.export_file(payload.get("folder", ""), "npk")
                subprocess.Popen(["explorer", "/select,", str(path)])
                return self._json(dict(opened=path.name))
            if parts == ["api", "studio", "wardrobe", "save"]:
                return self._json(studio.save_outfit(payload))
            if parts == ["api", "studio", "wardrobe", "delete"]:
                return self._json(studio.delete_outfit(payload))
            if parts == ["api", "game", "name"]:
                return self._json(game.save_name(payload))
            if len(parts) == 4 and parts[:2] == ["api", "projects"]:
                if parts[3] == "gate":
                    return self._json(dict(event=add_gate(parts[2], payload), project=progress.detail(progress.project(parts[2]))))
                if parts[3] == "reveal":
                    return self._json(reveal(parts[2], payload))
        except (ValueError, TypeError, KeyError) as error:
            return self._json(dict(error=str(error)), 400)
        return self._json(dict(error="not found"), 404)

    def log_message(self, *args):
        pass


def warm():
    """Start every live project's current design worker and list its units now, so the first visit to the review board is quick."""
    for p in progress.registry():
        if p.get("current") and not p.get("archived"):
            try:
                units(p["current"])
            except Exception as error:  # a broken design must not stop the others; the page will show the error when opened
                print(f"warm {p['current']}: {error}", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    port = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--port=")), 8800))
    print(f"workbench http://127.0.0.1:{port}/", flush=True)
    threading.Thread(target=warm, daemon=True).start()
    try:
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    finally:
        for w in workers.values():
            w["process"].terminate()


if __name__ == "__main__":
    main()
