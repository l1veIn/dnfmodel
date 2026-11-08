"""Switch the installed Fatfish costume: python switch_fatfish.py big|luxe|normal|final

All versions cover the same paths, so only one may be installed. Refuses while the game
runs. Only touches this project's own A_Fatfish_FMage_* packages; every package removed
from the game folder must already have an identical copy in the workspace.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
VERSIONS = {"big": ROOT / "output/Fatfish_Doll_v03/A_Fatfish_FMage_NativeDoll_v03.NPK",
            "luxe": ROOT / "output/Fatfish_Luxe_v04/A_Fatfish_FMage_LuxeBigHead_v04.NPK",
            "normal": ROOT / "output/Fatfish_Normal_v05/A_Fatfish_FMage_Normal_v05.NPK",
            "final": ROOT / "output/Fatfish_Final_v06/A_Fatfish_FMage_Final_v06.NPK"}
KNOWN = {ROOT / "output/Fatfish_AllAvatar_v02/A_Fatfish_FMage_AllAvatar_NoGrowtype_v02.NPK", *VERSIONS.values()}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in VERSIONS:
        raise SystemExit("usage: switch_fatfish.py big|luxe|normal|final")
    running = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout.lower()
    if "dnf.exe" in running:
        raise SystemExit("Game is running; exit it first")
    source = VERSIONS[sys.argv[1]]
    copies = {digest(p) for p in KNOWN if p.exists()}
    for path in GAME.glob("A_Fatfish_FMage_*.NPK"):
        if digest(path) not in copies:
            raise SystemExit(f"{path.name} has no identical workspace copy; move it out by hand")
    for path in GAME.glob("A_Fatfish_FMage_*.NPK"):
        path.unlink()
    target = GAME / source.name
    shutil.copy2(source, target)
    assert digest(target) == digest(source)
    print("installed", target.name)


if __name__ == "__main__":
    main()
