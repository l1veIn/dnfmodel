"""DNF patch workbench: one local page for every patch project. Design: docs/workbench_design.md.

    python scripts/workbench/server.py [--port=8800]

Files stay the source of truth: projects are design/<id>/patch.json, verdicts and issues are design/<id>/workbench/issues.jsonl.
Frames come from one worker process per project (scripts/workbench/worker.py), started on first use.
Bound to 127.0.0.1 only. Never writes to the game folder.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import issues  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
DESIGN = ROOT / "design"
LIMIT = 200_000
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
workers, workers_lock = {}, threading.Lock()
units_cache = {}


def projects():
    out = []
    for path in sorted(DESIGN.glob("*/patch.json")):
        ident = path.parent.name
        data = json.loads(path.read_text("utf-8"))
        state = issues.replay(ident)
        extra = path.parent / "workbench" / "assets.json"
        assets = ["character"] + ([a["id"] for a in json.loads(extra.read_text("utf-8"))["assets"]] if extra.exists() else [])
        out.append(dict(id=ident, title=data.get("title", ident), version=data.get("version"), npk_stem=data.get("npk_stem"), assets=assets,
                        open=sum(1 for i in state["issues"] if i["status"] == "open"), fixed=sum(1 for i in state["issues"] if i["status"] == "fixed"),
                        passed=sum(1 for u in state["units"].values() if u["verdict"] == "pass"), events=bool(issues.read_events(ident))))
    return out


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def worker(ident):
    """The project's worker, started if needed. A worker that went idle and exited is started again."""
    if not (DESIGN / ident / "patch.json").exists():
        raise KeyError(ident)
    with workers_lock:
        w = workers.get(ident)
        if w and w["process"].poll() is None:
            return w["port"]
        port = free_port()
        log = (DESIGN / ident / "workbench")
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


def project_state(ident, refresh=False):
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


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, body, kind="application/json; charset=utf-8", code=200, cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, code=200):
        self._send(json.dumps(value, ensure_ascii=False).encode("utf-8"), code=code)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        parts = [p for p in url.path.split("/") if p]
        try:
            if not parts:
                return self._send((STATIC / "index.html").read_bytes(), TYPES[".html"])
            if parts[0] == "static" and len(parts) == 2 and (STATIC / parts[1]).suffix in TYPES and (STATIC / parts[1]).exists():
                return self._send((STATIC / parts[1]).read_bytes(), TYPES[(STATIC / parts[1]).suffix])
            if parts == ["api", "projects"]:
                return self._json(projects())
            if len(parts) >= 4 and parts[:2] == ["api", "p"]:
                ident, what = parts[2], parts[3]
                if what == "state":
                    return self._json(project_state(ident, refresh=q.get("refresh") == "1"))
                if what == "frame":
                    body, kind = ask(ident, "/frame", asset=q["asset"], unit=q["unit"], side=q["side"], k=q["k"], weapon=q.get("weapon", "0"))
                    return self._send(body, kind or "image/png", cache="max-age=3600")  # the page adds the unit version to the URL
                if what == "version":
                    body, _ = ask(ident, "/version", asset=q["asset"], unit=q["unit"])
                    units_cache.pop(ident, None)
                    return self._send(body)
        except KeyError as error:
            return self._json(dict(error=f"unknown {error}"), 404)
        except (RuntimeError, urllib.error.URLError) as error:
            return self._json(dict(error=str(error)), 502)
        return self._json(dict(error="not found"), 404)

    def do_POST(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        length = int(self.headers.get("Content-Length") or 0)
        if len(parts) != 4 or parts[:2] != ["api", "p"] or parts[3] != "event" or length > LIMIT:
            return self._json(dict(error="not found"), 404)
        # A page on another site cannot post here: browsers send Origin on cross-site POSTs.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            return self._json(dict(error="cross-site request refused"), 403)
        try:
            event = post_event(parts[2], json.loads(self.rfile.read(length)))
            return self._json(dict(event=event, state=project_state(parts[2])))
        except (ValueError, TypeError, KeyError) as error:
            return self._json(dict(error=str(error)), 400)

    def log_message(self, *args):
        pass


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    port = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--port=")), 8800))
    print(f"workbench http://127.0.0.1:{port}/", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    finally:
        for w in workers.values():
            w["process"].terminate()


if __name__ == "__main__":
    main()
