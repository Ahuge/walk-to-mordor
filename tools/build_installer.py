#!/usr/bin/env python3
"""Build the full Walk to Mordor installer.

Steps:
  1. Build WalkToMordorDaemon.exe (PyInstaller)
  2. Build WalkToMordorWidget.exe (PyInstaller)
  3. Build WalkToMordorSetup.exe (Inno Setup)

Requires on Windows:
  pip install pyinstaller pywebview
  Inno Setup 6 (https://jrsoftware.org/isinfo.php)

Run from the repo root:  python tools/build_installer.py
Output: dist/WalkToMordorSetup-1.0.0.exe
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ISCC_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]


def find_iscc() -> Path:
    for p in ISCC_CANDIDATES:
        if p.exists():
            return p
    found = shutil.which("ISCC.exe") or shutil.which("iscc")
    if found:
        return Path(found)
    sys.exit(
        "Inno Setup 6 not found. Install it from https://jrsoftware.org/isinfo.php\n"
        "then re-run this script."
    )


def main() -> None:
    if sys.platform != "win32":
        sys.exit("the installer must be built on Windows")
    print("=== building daemon exe ===")
    subprocess.run([sys.executable, "tools/build_daemon_exe.py"],
                   cwd=REPO, check=True)
    print("=== building widget exe ===")
    subprocess.run([sys.executable, "tools/build_widget_exe.py"],
                   cwd=REPO, check=True)
    iscc = find_iscc()
    print(f"=== building installer with {iscc} ===")
    subprocess.run([str(iscc), str(REPO / "installer" / "walk-to-mordor.iss")],
                   cwd=REPO, check=True)
    setups = sorted((REPO / "dist").glob("WalkToMordorSetup-*.exe"))
    if setups:
        print(f"done: {setups[-1]}")
    else:
        print("done (installer exe not found in dist/ — check ISCC output)")


if __name__ == "__main__":
    main()
