"""The project's scripts folder holds the shared NPK reader and the H3 runner helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "scripts"))
