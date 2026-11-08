"""Review verdicts and issues of one patch project, as an append-only event log: design/<id>/workbench/issues.jsonl.

The current state is replayed from the events, so history is never lost. Frame numbers are tool numbers (from 0);
pages show them one higher, as the user counts.

    python scripts/workbench/issues.py <id> list [--all]          open, fixed-but-not-verified and reopened issues
    python scripts/workbench/issues.py <id> fixed <n> "what was done"
    python scripts/workbench/issues.py <id> note <n> "comment"
    python scripts/workbench/issues.py <id> import-review          one-time import of the old design/<id>/review.json
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "design"
LOCK = threading.RLock()  # re-entrant: the server holds it across numbering and appending a new issue
NOTE_LIMIT = 5000
MARK_LIMIT = 40
# Who may write which event. The page writes as the user; Claude writes through this module's command line.
USER_OPS = {"open", "reopen", "verify", "withdraw", "pass", "clear", "note"}
CLAUDE_OPS = {"fixed", "note"}
STATUS_TEXT = {"open": "待修", "fixed": "已修待复核", "verified": "已复核", "withdrawn": "已撤回"}


def log_path(ident):
    return DESIGN / ident / "workbench" / "issues.jsonl"


def read_events(ident):
    path = log_path(ident)
    if not path.exists():
        return []
    events = []
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def append(ident, event):
    """One line per event, flushed and fsynced, under a lock so two writers cannot interleave."""
    path = log_path(ident)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), **event}
    line = json.dumps(event, ensure_ascii=False)
    with LOCK:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return event


def replay(ident):
    """State from the events: per unit the verdict, per issue its status and history."""
    units, issues = {}, {}
    for e in read_events(ident):
        op = e["op"]
        if op in ("pass", "clear"):
            key = f"{e['asset']}/{e['unit']}"
            units[key] = dict(verdict="pass" if op == "pass" else "", version=e.get("frames_version"), t=e["t"])
        elif op == "open":
            issues[e["issue"]] = dict(issue=e["issue"], asset=e["asset"], unit=e["unit"], frames=e.get("frames", []), marks=e.get("marks", []),
                                      note=e.get("note", ""), status="open", opened=e["t"], history=[e])
        elif e.get("issue") in issues:
            item = issues[e["issue"]]
            item["history"].append(e)
            if op == "fixed":
                item.update(status="fixed", fixed_version=e.get("frames_version"))
            elif op == "reopen":
                item["status"] = "open"
            elif op == "verify":
                item["status"] = "verified"
            elif op == "withdraw":
                item["status"] = "withdrawn"
    return dict(units=units, issues=sorted(issues.values(), key=lambda i: i["issue"]))


def next_issue(ident):
    numbers = [e["issue"] for e in read_events(ident) if e["op"] == "open"]
    return max(numbers, default=0) + 1


def unit_summary(state, asset, unit, version=None):
    """What the list shows for a unit: needs-recheck beats pass, open issues beat everything."""
    mine = [i for i in state["issues"] if i["asset"] == asset and i["unit"] == unit]
    open_ = sum(1 for i in mine if i["status"] == "open")
    fixed = sum(1 for i in mine if i["status"] == "fixed")
    verdict = state["units"].get(f"{asset}/{unit}", {})
    status = ""
    if verdict.get("verdict") == "pass":
        status = "recheck" if version is not None and verdict.get("version") not in (None, version) else "pass"
    if fixed:
        status = "fixed"
    if open_:
        status = "open"
    return dict(status=status, open=open_, fixed=fixed, total=len(mine))


def validate(event, units, by="user"):
    """Check a page's event against the project's real units and frames, so a stray request cannot write anything odd. Returns the clean event."""
    op = event.get("op")
    if op not in (USER_OPS if by == "user" else CLAUDE_OPS):
        raise ValueError(f"op {op!r} not allowed")
    note = event.get("note", "")
    if not isinstance(note, str) or len(note) > NOTE_LIMIT:
        raise ValueError("bad note")
    clean = dict(op=op, by=by)
    if note:
        clean["note"] = note
    if op in ("open", "pass", "clear"):
        asset, unit = event.get("asset"), event.get("unit")
        found = units.get((asset, unit))
        if found is None:
            raise ValueError("unknown unit")
        clean.update(asset=asset, unit=unit, frames_version=found["version"])
        if op == "open":
            frames = event.get("frames", [])
            if not isinstance(frames, list) or not set(frames) <= set(found["frames"]):
                raise ValueError("frames outside the unit")
            marks = event.get("marks", [])
            if not isinstance(marks, list) or len(marks) > MARK_LIMIT:
                raise ValueError("bad marks")
            clean_marks = []
            for m in marks:
                if not isinstance(m, dict) or m.get("frame") not in found["frames"]:
                    raise ValueError("mark outside the unit")
                clean_marks.append({k: int(m[k]) for k in ("frame", "x", "y", "r") if isinstance(m.get(k), (int, float))})
            if not note.strip() and not frames and not clean_marks:
                raise ValueError("an issue needs a note, a frame or a mark")
            clean.update(frames=sorted(set(frames)), marks=clean_marks)
    else:
        if not isinstance(event.get("issue"), int):
            raise ValueError("issue number required")
        clean["issue"] = event["issue"]
        if "frames_version" in event and isinstance(event["frames_version"], (int, float, str)):
            clean["frames_version"] = event["frames_version"]
    return clean


# ---------------------------------------------------------------- command line (Claude's side)


def cmd_list(ident, show_all=False):
    state = replay(ident)
    rows = [i for i in state["issues"] if show_all or i["status"] in ("open", "fixed")]
    if not rows:
        print("no open issues" if not show_all else "no issues")
    for i in rows:
        # Character frames are sprite slots, shown as the user counts them; other assets number frames inside one IMG.
        label = (lambda f: f"{f}(第{f + 1}帧)") if i["asset"] == "character" else (lambda f: f"#{f}")
        frames = ", ".join(label(f) for f in i["frames"])
        marks = "; ".join(f"{label(m['frame'])} at ({m['x']},{m['y']}) r{m.get('r', 0)}" for m in i["marks"])
        reopened = sum(1 for h in i["history"] if h["op"] == "reopen")
        print(f"#{i['issue']} [{STATUS_TEXT[i['status']]}{'，退回 ' + str(reopened) + ' 次' if reopened else ''}] {i['asset']}/{i['unit']}"
              + (f"  frames {frames}" if frames else "") + (f"  marks {marks}" if marks else ""))
        for h in i["history"]:
            if h.get("note"):
                print(f"    {h['t']} {h['by']} {h['op']}: {h['note']}")
    verdicts = {k: v for k, v in state["units"].items() if v["verdict"] == "pass"}
    print(f"{len(verdicts)} units passed")


def _unit_version(ident, asset, unit):
    """Ask the running workbench for the unit's current frame version; without it the fix is recorded without one."""
    import urllib.parse
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{os.environ.get('WORKBENCH_PORT', 8800)}/api/p/{ident}/version?asset={urllib.parse.quote(asset)}&unit={urllib.parse.quote(unit)}", timeout=60) as r:
            return json.loads(r.read())["version"]
    except Exception:
        return None


def cmd_fixed(ident, number, note):
    state = replay(ident)
    item = next((i for i in state["issues"] if i["issue"] == number), None)
    if item is None:
        raise SystemExit(f"no issue #{number}")
    event = dict(op="fixed", by="claude", issue=number, note=note)
    version = _unit_version(ident, item["asset"], item["unit"])
    if version is not None:
        event["frames_version"] = version
    print(append(ident, event))


def cmd_note(ident, number, note):
    if not any(i["issue"] == number for i in replay(ident)["issues"]):
        raise SystemExit(f"no issue #{number}")
    print(append(ident, dict(op="note", by="claude", issue=number, note=note)))


def import_review(ident):
    """The old page kept one verdict per action in review.json. Each becomes events here; the file itself is left alone."""
    source = DESIGN / ident / "review.json"
    if not source.exists():
        raise SystemExit(f"{source} not found")
    if any(e["op"] == "import" for e in read_events(ident)):
        raise SystemExit("already imported")
    reviews = json.loads(source.read_text("utf-8"))
    number = next_issue(ident)
    count = 0
    for action, r in reviews.items():
        base = dict(asset="character", unit=action, by="user", t=r.get("updated", ""), imported=True)
        if r.get("status") == "pass":
            append(ident, dict(base, op="pass", frames_version=None))
        elif r.get("note") or r.get("frames"):
            append(ident, dict(base, op="open", issue=number, frames=r.get("frames", []), marks=[], note=r.get("note", "")))
            number += 1
            count += 1
    append(ident, dict(op="import", by="claude", source=str(source.relative_to(ROOT)), actions=len(reviews)))
    print(f"imported {len(reviews)} actions, {count} issues")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        raise SystemExit(__doc__)
    ident, cmd = args[0], args[1]
    if not (DESIGN / ident / "patch.json").exists():
        raise SystemExit(f"no project design/{ident}")
    if cmd == "list":
        return cmd_list(ident, "--all" in sys.argv)
    if cmd == "fixed":
        return cmd_fixed(ident, int(args[2]), args[3])
    if cmd == "note":
        return cmd_note(ident, int(args[2]), args[3])
    if cmd == "import-review":
        return import_review(ident)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
