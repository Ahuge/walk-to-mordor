#!/usr/bin/env python3
"""Build the WalkToMordor nudge exe via PyInstaller.

Usage:
    python tools/build_nudge_exe.py
Output: dist/WalkToMordorNudge.exe
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "WalkToMordorNudge",
        str(REPO / "tools" / "nudge.py"),
    ]
    print("building nudge…")
    subprocess.run(cmd, cwd=REPO, check=True)
    print(f"done: {REPO / 'dist' / 'WalkToMordorNudge.exe'}")


if __name__ == "__main__":
    main()
