#!/usr/bin/env python3
"""Build a standalone WalkToMordorWidget.exe with the app icon baked in.

The exe shows our gold-ring icon on the taskbar (no more Python icon)
and runs without a console window.

Requires: pip install pyinstaller pywebview
Run from the repo root:  python tools/build_widget_exe.py
Output: dist/WalkToMordorWidget.exe
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ICON = REPO / "packs" / "lotr" / "art" / "icon.ico"


def main() -> None:
    if not ICON.exists():
        sys.exit(f"icon not found: {ICON}")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",          # no console window
        "--name", "WalkToMordorWidget",
        f"--icon={ICON}",
        # pywebview needs its WebView2 loader hooks; collect just in case
        "--collect-all", "webview",
        str(REPO / "ui" / "widget.py"),
    ]
    print("building…")
    subprocess.run(cmd, cwd=REPO, check=True)
    exe = REPO / "dist" / "WalkToMordorWidget.exe"
    print(f"done: {exe}")
    print("The daemon must still be running (http://127.0.0.1:8471/).")


if __name__ == "__main__":
    main()
