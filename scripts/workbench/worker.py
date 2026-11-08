"""Renders one patch project's frames for the workbench. The main server starts one per project on demand; it exits after ten idle minutes.

    python scripts/workbench/worker.py <id> <port>

Two kinds of assets:
- character: the main rig, one unit per action (clips.json), via the patch kit. Needs PATCH_ID, which is why this is a separate process.
- img: any IMG in a built NPK that is not costume or weapon (skill props, robots, awakening frames, cut-ins, recolored glow), one unit per IMG,
  compared with the official IMG of the same path, found through the resource library (kb/kb.sqlite).
Assets other than character are listed in design/<id>/workbench/assets.json.
Only reads the game folder, the project's output and the resource library.
"""
from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from PIL import Image  # noqa: E402

IDLE = 600
PAD = 6
GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
COSTUME = re.compile(r"^sprite/character/[^/]+/[^/]+/(avatar|weapon)/")
last_request = [time.monotonic()]
render_lock = threading.Lock()


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------- character (the main rig)


class Character:
    kind = "character"

    def __init__(self, ident):
        os.environ["PATCH_ID"] = ident
        sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
        from kit import review_page, source
        from kit.config import P
        self.P, self.page, self.source = P, review_page, source
        self.id, self.label = "character", "人物动作"
        self.weapon = P.weapon["label"] if P.weapon else None
        self._units = None

    @staticmethod
    def available(ident):
        data = json.loads((ROOT / "design" / ident / "patch.json").read_text("utf-8"))
        out = ROOT / "output" / data.get("out", f"{ident}_v{data['version']}")
        return (out / "native_frames").is_dir() and (ROOT / "design" / ident / "clips.json").exists()

    def version_of(self, frames):
        return int(max((self.page.FRAMES / f"{i:04d}.png").stat().st_mtime for i in frames))

    def units(self):
        out = []
        for a in self.page._actions():
            frames = [r["i"] for r in a["frames"]]
            out.append(dict(id=a["name"], label=a["name"], group="", box=a["box"], frames=frames,
                            labels=[f"第 {i + 1} 帧" for i in frames], meta=a["frames"], version=self.version_of(frames), player="sprite"))
        self._units = {u["id"]: u for u in out}
        return out

    def unit(self, unit_id):
        if self._units is None:
            self.units()
        return self._units[unit_id]

    def frame(self, unit_id, side, k, weapon):
        u = self.unit(unit_id)
        i = u["frames"][k]
        with render_lock:
            image = self.source.native_world(i) if side == "native" else self.page._new(i)
            if weapon and self.weapon:
                image = self.source.armed(image, i)
        return png(image.crop(tuple(u["box"])))


# ---------------------------------------------------------------- img (skill props, robots, cut-ins, glow)


@lru_cache(maxsize=None)
def npk_entries(path_text):
    from dnf_resources import read_npk
    return {e["path"]: e for e in read_npk(Path(path_text))}


@lru_cache(maxsize=64)
def load_img(path_text, img_path):
    from survey_gunner_effects import reader
    entry = npk_entries(path_text)[img_path]
    with open(path_text, "rb") as stream:
        stream.seek(entry["offset"])
        return reader(stream.read(entry["length"]), entry["version"])


def official_npk(img_path):
    db = sqlite3.connect(f"file:{ROOT / 'kb/kb.sqlite'}?mode=ro", uri=True)
    row = db.execute("select n.name from img i join npk n on n.id=i.npk where i.path=? and lower(n.name) like 'sprite%' limit 1", (img_path,)).fetchone()
    db.close()
    return str(GAME / row[0]) if row else None


def geometry(img):
    """(x, y, w, h, canvas w, canvas h) of each frame from the headers, without decoding pixels."""
    out = []
    for k in range(len(img.frames)):
        f = img.resolve(k)
        w, h = f.get("w", f.get("width", 0)), f.get("h", f.get("height", 0))
        out.append((f.get("x", 0), f.get("y", 0), w, h, f.get("cw", f.get("canvas_width")), f.get("ch", f.get("canvas_height"))))
    return out


class ImgAsset:
    kind = "img"

    def __init__(self, spec, claimed):
        self.id, self.label = spec["id"], spec.get("label", spec["id"])
        self.npk = str(ROOT / spec["npk"])
        self.player = spec.get("player", "sprite")
        paths = [p for p in npk_entries(self.npk) if not COSTUME.match(p) and p not in claimed]
        self.paths = {}
        for group in spec.get("groups", []):
            for p in paths:
                stem = p.rsplit("/", 1)[1][:-4].lower()
                if any(p.lower().endswith(f"/{m.lower()}.img") or stem == m.lower() for m in group["match"]):
                    self.paths.setdefault(p, group.get("label", group["id"]))
        if spec.get("rest"):
            for p in paths:
                if p not in self.paths and p not in claimed:
                    self.paths[p] = p.rsplit("/", 2)[-2]
        claimed.update(self.paths)
        self.version = int(Path(self.npk).stat().st_mtime)
        self._units = None

    def units(self):
        out = []
        for path, group in self.paths.items():
            new = load_img(self.npk, path)
            old_npk = official_npk(path)
            old = load_img(old_npk, path) if old_npk else None
            count = max(len(new.frames), len(old.frames) if old else 0)
            boxes = []
            canvas = None
            for img in (new, old):
                if img is None:
                    continue
                for x, y, w, h, cw, ch in geometry(img):
                    if w > 1 and h > 1:
                        boxes.append((x, y, x + w, y + h))
                    canvas = canvas or ((cw, ch) if cw and ch else None)
            if self.player == "screen" and canvas:
                box = (0, 0, canvas[0], canvas[1])
            elif boxes:
                box = (min(b[0] for b in boxes) - PAD, min(b[1] for b in boxes) - PAD, max(b[2] for b in boxes) + PAD, max(b[3] for b in boxes) + PAD)
            else:
                box = (0, 0, 8, 8)
            name = path.rsplit("/", 1)[1][:-4]
            out.append(dict(id=path, label=name, group=group, box=box, frames=list(range(count)), labels=[f"#{k}" for k in range(count)],
                            meta=[{}] * count, version=self.version, player=self.player, official=bool(old_npk), npk=Path(old_npk).name if old_npk else None))
        self._units = {u["id"]: u for u in out}
        return out

    def unit(self, unit_id):
        if self._units is None:
            self.units()
        return self._units[unit_id]

    def frame(self, unit_id, side, k, weapon):
        u = self.unit(unit_id)
        x0, y0, x1, y1 = u["box"]
        canvas = Image.new("RGBA", (x1 - x0, y1 - y0))
        source = self.npk if side == "new" else official_npk(unit_id)
        if source:
            img = load_img(source, unit_id)
            if k < len(img.frames):
                with render_lock:
                    f = img.resolve(k)
                    pic = img.image(k)
                if pic is not None:
                    pic = pic.convert("RGBA")
                    canvas.paste(pic, (f.get("x", 0) - x0, f.get("y", 0) - y0), pic)  # paste, unlike alpha_composite, accepts offsets outside the box
        return png(canvas)


# ---------------------------------------------------------------- project and HTTP


class Project:
    def __init__(self, ident):
        self.id = ident
        self.assets = {}
        if Character.available(ident):
            c = Character(ident)
            self.assets[c.id] = c
        spec_path = ROOT / "design" / ident / "workbench" / "assets.json"
        if spec_path.exists():
            claimed = set()
            for spec in json.loads(spec_path.read_text("utf-8"))["assets"]:
                if spec.get("kind") == "img" and (ROOT / spec["npk"]).exists():
                    self.assets[spec["id"]] = ImgAsset(spec, claimed)
        self._listing = None

    def listing(self):
        if self._listing is None:
            self._listing = [dict(id=a.id, label=a.label, kind=a.kind, weapon=getattr(a, "weapon", None), units=a.units()) for a in self.assets.values()]
        return self._listing

    def refresh(self):
        """Frames may have been rewritten (final, a repair, a new build): drop what was computed from them."""
        self._listing = None
        npk_entries.cache_clear()
        load_img.cache_clear()
        for a in self.assets.values():
            a._units = None


def make_handler(project):
    class Handler(BaseHTTPRequestHandler):
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
            last_request[0] = time.monotonic()
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/ping":
                    return self._json(dict(id=project.id, assets=list(project.assets)))
                if url.path == "/units":
                    if q.get("refresh"):
                        project.refresh()
                    return self._json(project.listing())
                if url.path == "/version":
                    asset = project.assets[q["asset"]]
                    if q.get("refresh", "1") == "1":
                        asset._units = None
                    return self._json(dict(version=asset.unit(q["unit"])["version"]))
                if url.path == "/frame":
                    asset = project.assets[q["asset"]]
                    side = q["side"]
                    if side not in ("native", "new"):
                        raise ValueError("side")
                    return self._send(asset.frame(q["unit"], side, int(q["k"]), q.get("weapon") == "1"), "image/png")
            except (KeyError, IndexError, ValueError) as error:
                return self._json(dict(error=f"{type(error).__name__}: {error}"), 404)
            return self._json(dict(error="not found"), 404)

        def log_message(self, *args):
            pass

    return Handler


def idle_watch():
    while True:
        time.sleep(30)
        if time.monotonic() - last_request[0] > IDLE:
            os._exit(0)


def main():
    ident, port = sys.argv[1], int(sys.argv[2])
    project = Project(ident)
    threading.Thread(target=idle_watch, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(project))
    print(f"worker {ident} on {port}: {list(project.assets)}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
