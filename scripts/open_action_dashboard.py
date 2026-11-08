"""Open the user's local panel, starting a hidden server only when needed."""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
URL='http://127.0.0.1:8791/'


def ready():
    try:
        with urllib.request.urlopen(URL+'api/health',timeout=1) as r:
            return json.load(r).get('app')=='fatfish-action-dashboard'
    except (OSError,ValueError):return False


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--no-open',action='store_true');args=ap.parse_args()
    if not ready():
        logs=ROOT/'design/fatfish/action_catalog';logs.mkdir(parents=True,exist_ok=True)
        with (logs/'server_stdout.log').open('ab') as stdout,(logs/'server_stderr.log').open('ab') as stderr:
            subprocess.Popen([sys.executable,str(ROOT/'scripts/serve_action_dashboard.py'),'--port','8791'],cwd=str(ROOT),
                stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
        for _ in range(30):
            time.sleep(.2)
            if ready():break
        else:raise SystemExit('Panel could not start; inspect design/fatfish/action_catalog/server_stderr.log')
    if not args.no_open:webbrowser.open(URL)
    print(URL)


if __name__=='__main__':main()
