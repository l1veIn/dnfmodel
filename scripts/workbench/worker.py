"""Renders one design folder's frames for the review board. The main server starts one per design on demand; it exits after an idle hour.

    python scripts/workbench/worker.py <design id> <port>

Assets:
- character: the main rig, one unit per action (clips.json), via the patch kit. Needs PATCH_ID, which is why this is a separate process.
- one asset per category of the design's built NPK (categories.py): growtype, weapon, cut-in, awakening frames, effects, summons.
  One unit per IMG, compared with the official IMG of the same path (found through the resource library).
  design/<id>/workbench/assets.json only gives groups friendlier names.
Each unit is served as one atlas per side (render.py), cached on disk. Only reads the game folder, the project's output and the library.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import categories  # noqa: E402
import render  # noqa: E402

IDLE = 3600
last_request = [time.monotonic()]


# ---------------------------------------------------------------- character (the main rig)


class Character:
    kind = "character"

    def __init__(self, ident):
        os.environ["PATCH_ID"] = ident
        sys.path.insert(0, str(ROOT / ".claude/skills/dnf-character-patch/scripts"))
        from kit import review_page, source
        from kit.config import P
        self.ident, self.P, self.page, self.source = ident, P, review_page, source
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
            box = a["box"]
            out.append(dict(id=a["name"], label=a["name"], group="", box=box, frames=frames, meta=a["frames"], version=self.version_of(frames),
                            player="sprite", atlas=render.layout(box[2] - box[0], box[3] - box[1], len(frames))))
        self._units = {u["id"]: u for u in out}
        return out

    def unit(self, unit_id):
        if self._units is None:
            self.units()
        return self._units[unit_id]

    def _image(self, i, side, weapon):
        with render.lock:
            image = self.source.native_world(i) if side == "native" else self.page._new(i)
            if weapon and self.weapon:
                image = self.source.armed(image, i)
        return image

    def frame(self, unit_id, side, k, weapon):
        u = self.unit(unit_id)
        return render.webp(self._image(u["frames"][k], side, weapon).crop(tuple(u["box"])))

    def atlas(self, unit_id, side, weapon):
        u = self.unit(unit_id)
        native = [self.P.composites / f"{i:04d}.png" for i in u["frames"]]
        stamp = max(int(p.stat().st_mtime) for p in native) if side == "native" else u["version"]
        key = f"char|{self.ident}|{unit_id}|{side}|{int(bool(weapon))}|{stamp}|{u['box']}"
        return render.cached(key, lambda: render.atlas([self._image(i, side, weapon).crop(tuple(u["box"])) for i in u["frames"]], u["atlas"]))


# ---------------------------------------------------------------- one category of the built NPK


class ImgAsset:
    kind = "img"

    def __init__(self, key, npk, paths, names):
        """names maps a path to a friendlier group label from assets.json; other paths group by folder."""
        self.id, self.label = key, categories.LABEL[key]
        self.npk = str(npk)
        self.screen = categories.PLAYER[key] == "screen"
        self.paths = {p: names.get(p) or p.rsplit("/", 2)[-2] for p in sorted(paths, key=lambda p: (names.get(p) or p.rsplit("/", 2)[-2], p))}
        self.version = int(Path(self.npk).stat().st_mtime)
        self._units = None

    def units(self):
        out = []
        for path, group in self.paths.items():
            official = render.official_npk(path)
            box, count, _ = render.unit_box([self.npk, official], path, self.screen)
            out.append(dict(id=path, label=path.rsplit("/", 1)[1][:-4], group=group, box=box, frames=list(range(count)), meta=[{}] * count,
                            version=self.version, player="screen" if self.screen else "sprite", official=bool(official),
                            npk=Path(official).name if official else None, atlas=render.layout(box[2] - box[0], box[3] - box[1], count, self.screen)))
        self._units = {u["id"]: u for u in out}
        return out

    def unit(self, unit_id):
        if self._units is None:
            self.units()
        return self._units[unit_id]

    def _source(self, unit_id, side):
        return self.npk if side == "new" else render.official_npk(unit_id)

    def frame(self, unit_id, side, k, weapon):
        return render.webp(render.frame(self._source(unit_id, side), unit_id, k, tuple(self.unit(unit_id)["box"])))

    def atlas(self, unit_id, side, weapon):
        u = self.unit(unit_id)
        return render.img_atlas(self._source(unit_id, side), unit_id, tuple(u["box"]), len(u["frames"]), self.screen)


# ---------------------------------------------------------------- project and HTTP


def built_npk(ident):
    """The NPK this design is reviewed against: the project's newest build for its current design, otherwise the build its patch.json names."""
    import progress
    data = json.loads((ROOT / "design" / ident / "patch.json").read_text("utf-8"))
    own = f"{data['npk_stem']}_v{data['version']:02d}.NPK"
    for p in progress.registry():
        if ident in p["designs"]:
            built = progress.versions(p)
            pick = built[0] if p.get("current") == ident and built else next((v for v in built if v["name"] == own), None)
            return ROOT / pick["path"] if pick else None
    hits = list((ROOT / "output").glob(f"*/{own}"))
    return hits[0] if hits else None


def group_names(ident, paths):
    """Group labels from design/<id>/workbench/assets.json (optional): {"assets": [{"groups": [{"label", "match": [path tails or IMG stems]}]}]}."""
    spec_path = ROOT / "design" / ident / "workbench" / "assets.json"
    if not spec_path.exists():
        return {}
    names = {}
    for spec in json.loads(spec_path.read_text("utf-8")).get("assets", []):
        for group in spec.get("groups", []):
            match = [m.lower() for m in group["match"]]
            for p in paths:
                low = p.lower()
                stem = low.rsplit("/", 1)[1][:-4]
                if p not in names and any(low.endswith(f"/{m}.img") or stem == m for m in match):
                    names[p] = group.get("label", group["id"])
    return names


class Project:
    """The character asset, then one asset per category of the built NPK, in the same order for every project."""

    def __init__(self, ident):
        self.id = ident
        self.assets = {}
        if Character.available(ident):
            c = Character(ident)
            self.assets[c.id] = c
        npk = built_npk(ident)
        if npk and npk.exists():
            paths = list(render.npk_entries(str(npk)))
            by_key = {}
            for p in paths:
                by_key.setdefault(categories.classify(p), []).append(p)
            names = group_names(ident, paths)
            for key, _, _ in categories.CATEGORIES:
                if key != "avatar" and by_key.get(key):
                    self.assets[key] = ImgAsset(key, npk, by_key[key], names)
        self._listing = None

    def listing(self):
        if self._listing is None:
            self._listing = [dict(id=a.id, label=a.label, kind=a.kind, weapon=getattr(a, "weapon", None), units=a.units()) for a in self.assets.values()]
        return self._listing

    def refresh(self):
        """Frames may have been rewritten (final, a repair, a new build): drop what was computed from them."""
        self._listing = None
        render.reset()
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
                    asset._units = None
                    return self._json(dict(version=asset.unit(q["unit"])["version"]))
                if url.path in ("/frame", "/atlas"):
                    asset, side = project.assets[q["asset"]], q["side"]
                    if side not in ("native", "new"):
                        raise ValueError("side")
                    weapon = q.get("weapon") == "1"
                    body = asset.atlas(q["unit"], side, weapon) if url.path == "/atlas" else asset.frame(q["unit"], side, int(q["k"]), weapon)
                    return self._send(body, "image/webp")
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
