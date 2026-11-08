"""Bounded orchestration around the user's existing 65535 skill CLI.

Each request is submitted at most once. No credentials are copied or logged.
Resume/collection of known jobs does not POST replacement tasks.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "design/fatfish/action_samples_v01"
SKILL = Path(r"C:\Users\A\Desktop\fatfish_game\.agents\skills\65535\scripts\s65535.py")
LOCK = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def load_relay():
    spec = importlib.util.spec_from_file_location("s65535", SKILL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observed_cost(relay):
    response = relay.http("GET", "/v1/usage")
    usage = response.get("usage", {}).get("total", {})
    amount = usage.get("actual_cost", usage.get("cost"))
    if not isinstance(amount, (int, float)):
        raise RuntimeError("Cannot read usage amount for the batch spending check")
    return float(amount), response.get("unit")


def save_journal(journal):
    with LOCK:
        temporary = BATCH / "journal.tmp.json"
        temporary.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(BATCH / "journal.json")


def run_one(request, journal):
    name = request["name"]
    record = journal["jobs"][name]
    with LOCK:
        if record["state"] != "prepared":
            raise RuntimeError(f"Refusing to resubmit {name}")
        record.update(state="launching", started_at=now())
        save_journal(journal)
    inp = request["input"]
    command = [sys.executable, str(SKILL), "image", "--model", request["model"],
               "--prompt", inp["prompt"], "--n", "1", "--size", inp["size"],
               "--resolution", inp["resolution"], "--background", inp["background"],
               "--quality", inp["quality"], "--out", request["output_directory"],
               "--name", name, "--timeout", "900"]
    for image in request["local_reference_paths"]:
        command += ["--image", image]
    stdout_path = BATCH / "logs" / f"{name}.stdout.txt"
    stderr_path = BATCH / "logs" / f"{name}.stderr.txt"
    with stdout_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with stderr_path.open("w", encoding="utf-8") as error_log:
            for line in process.stderr:
                error_log.write(line)
                error_log.flush()
                match = re.search(r"任务已提交：\s*(\S+)", line)
                if match:
                    with LOCK:
                        record.update(task_id=match.group(1), state="submitted", submitted_at=now())
                        save_journal(journal)
                    print(json.dumps({"sample":name, "event":"submitted", "task_id":match.group(1)}), flush=True)
        code = process.wait()
    paths = sorted(str(path) for path in (BATCH / "raw").glob(name + "_*") if path.is_file())
    with LOCK:
        record.update(exit_code=code, finished_at=now(), files=paths,
                      stdout=str(stdout_path.relative_to(ROOT)), stderr=str(stderr_path.relative_to(ROOT)))
        if code == 0 and paths:
            record["state"] = "downloaded"
        elif record.get("task_id"):
            record["state"] = "needs_collection_or_failed"
        else:
            record["state"] = "submission_outcome_uncertain"
        save_journal(journal)
    print(json.dumps({"sample":name, "event":record["state"], "files":paths},ensure_ascii=False),flush=True)
    return record


def submit(args):
    manifest = json.loads((BATCH / "requests.json").read_text(encoding="utf-8"))
    if len(manifest["requests"]) != 12 or manifest["count"] != 12:
        raise RuntimeError("This approved batch must contain exactly 12 requests")
    if args.budget_usd != 20:
        raise RuntimeError("This run is approved for a 20 USD ceiling; update authorization before changing it")
    if (BATCH / "journal.json").exists():
        raise RuntimeError("A journal already exists. Use collect; never repeat the approved batch POSTs")
    for request in manifest["requests"]:
        if request["model"] != "gpt-image-2.5" or request["input"]["n"] != 1:
            raise RuntimeError("Model/count differs from user authorization")
        for path in request["local_reference_paths"]:
            if not Path(path).is_file():
                raise FileNotFoundError(path)
    for directory in ("raw", "logs", "qa"):
        (BATCH / directory).mkdir(parents=True, exist_ok=True)
    relay = load_relay()
    cost, unit = observed_cost(relay)
    journal = dict(provider="65535", model="gpt-image-2.5", created_at=now(),
                   budget_usd=args.budget_usd, authorized_count=12, concurrency=4,
                   usage_unit=unit, baseline_usage_cost=cost, observed_cost_delta=0,
                   spending_note="Observed account usage checked before and after each four-job wave; API exposes no per-request billing cap. Other concurrent account activity can contribute to observed deltas.",
                   jobs={r["name"]:dict(state="prepared",source_frame=r["source_frame"],category=r["category"]) for r in manifest["requests"]})
    manifest["spend_ceiling_usd"] = args.budget_usd
    manifest["status"] = "authorized_and_submitting"
    (BATCH / "requests.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    save_journal(journal)
    requests = manifest["requests"]
    for start in range(0, 12, 4):
        current, _ = observed_cost(relay)
        journal["observed_cost_delta"] = max(0, current - cost)
        if journal["observed_cost_delta"] >= args.budget_usd:
            journal["status"] = "budget_threshold_reached"
            save_journal(journal)
            break
        print(json.dumps({"event":"wave_started", "wave":start//4+1, "count":4}),flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda r: run_one(r, journal), requests[start:start+4]))
        current, _ = observed_cost(relay)
        journal["observed_cost_delta"] = max(0, current - cost)
        save_journal(journal)
        if any(r["state"] != "downloaded" for r in results):
            journal["status"] = "wave_needs_attention_no_replacement_submissions"
            save_journal(journal)
            break
    else:
        journal["status"] = "all_12_downloaded"
        journal["finished_at"] = now()
        save_journal(journal)
    print(json.dumps({"status":journal.get("status"), "observed_cost_delta":round(journal["observed_cost_delta"],6),
                      "downloaded":sum(r["state"]=="downloaded" for r in journal["jobs"].values())}),flush=True)


def collect():
    relay = load_relay()
    journal = json.loads((BATCH / "journal.json").read_text(encoding="utf-8"))
    for name, record in journal["jobs"].items():
        if record["state"] == "downloaded" or not record.get("task_id"):
            continue
        task = relay.unwrap(relay.http("GET", "/v1/tasks/" + record["task_id"]))
        record["provider_status"] = task.get("status")
        if task.get("status") == "failed":
            record.update(state="failed",error_code=task.get("error_code"),error_message=task.get("error_message"))
        elif task.get("status") == "done":
            import base64
            saved = []
            for i, url in enumerate(task.get("result_urls") or []):
                target = BATCH / "raw" / f"{name}_{i}.png"
                if not target.exists():
                    relay.download(url,target)
                saved.append(str(target))
            for i, item in enumerate((task.get("result") or {}).get("data", [])):
                if item.get("b64_json"):
                    target = BATCH / "raw" / f"{name}_b64_{i}.png"
                    if not target.exists():
                        target.write_bytes(base64.b64decode(item["b64_json"]))
                    saved.append(str(target))
            record.update(state="downloaded" if saved else "missing_output",files=saved,finished_at=now())
        save_journal(journal)
        print(json.dumps({"sample":name,"state":record["state"],"task_id":record["task_id"]}),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["submit","collect"])
    parser.add_argument("--budget-usd",type=float)
    arguments=parser.parse_args()
    if arguments.mode == "submit":
        submit(arguments)
    else:
        collect()
