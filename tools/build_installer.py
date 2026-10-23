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
Output: dist/WalkToMordorSetup-<version>.exe
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bridge.version import __version__  # noqa: E402
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


def _set_version(version: str) -> None:
    """Make version.py and the .iss agree with the requested version."""
    vpath = REPO / "bridge" / "version.py"
    text = vpath.read_text(encoding="utf-8")
    text, n = re.subn(r'__version__ = "[^"]*"',
                      f'__version__ = "{version}"', text)
    if n:
        vpath.write_text(text, encoding="utf-8")
    iss_path = REPO / "installer" / "walk-to-mordor.iss"
    text = iss_path.read_text(encoding="utf-8")
    text, n = re.subn(r'#define MyAppVersion "[^"]*"',
                      f'#define MyAppVersion "{version}"', text)
    if n:
        iss_path.write_text(text, encoding="utf-8")
    else:
        print("warning: could not patch version in .iss")


def main() -> None:
    if sys.platform != "win32":
        sys.exit("the installer must be built on Windows")
    # version.py is the source of truth; --version can override it.
    version = __version__
    if "--version" in sys.argv:
        i = sys.argv.index("--version")
        if i + 1 < len(sys.argv):
            version = sys.argv[i + 1]
    _set_version(version)
    print(f"version: {version}")
    print("=== building daemon exe ===")
    subprocess.run([sys.executable, "tools/build_daemon_exe.py"],
                   cwd=REPO, check=True)
    print("=== building widget exe ===")
    subprocess.run([sys.executable, "tools/build_widget_exe.py"],
                   cwd=REPO, check=True)
    print("=== building nudge exe ===")
    subprocess.run([sys.executable, "tools/build_nudge_exe.py"],
                   cwd=REPO, check=True)
    iscc = find_iscc()
    print(f"=== building installer with {iscc} ===")
    iss_path = REPO / "installer" / "walk-to-mordor.iss"
    subprocess.run([str(iscc), str(iss_path)], cwd=REPO, check=True)
    setups = sorted((REPO / "dist").glob("WalkToMordorSetup-*.exe"))
    if setups:
        print(f"done: {setups[-1]}")
    else:
        print("done (installer exe not found in dist/ — check ISCC output)")


if __name__ == "__main__":
    main()
