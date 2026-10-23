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

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bridge.version import __version__  # noqa: E402
def _iscc_candidates() -> list[Path]:
    out = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        # Per-user install (PrivilegesRequired=lowest works with this too).
        out.append(Path(local) / "Programs" / "Inno Setup 6" / "ISCC.exe")
    return out


def find_iscc() -> Path:
    for p in _iscc_candidates():
        if p.exists():
            return p
    found = shutil.which("ISCC.exe") or shutil.which("iscc")
    if found:
        return Path(found)
    sys.exit(
        "Inno Setup 6 not found. Install it with:\n"
        "  winget install --id JRSoftware.InnoSetup -e\n"
        "or from https://jrsoftware.org/isinfo.php, then re-run this script."
    )


def _set_version(version: str) -> None:
    """Make version.py and the .iss agree with the requested version."""
    for path, pattern, label in (
        (REPO / "bridge" / "version.py", r'__version__ = "[^"]*"',
         "bridge/version.py"),
        (REPO / "installer" / "walk-to-mordor.iss",
         r'#define MyAppVersion "[^"]*"', "installer/walk-to-mordor.iss"),
    ):
        original = path.read_text(encoding="utf-8")
        text, n = re.subn(pattern, pattern.replace('"[^"]*"', f'"{version}"'),
                          original)
        if not n:
            sys.exit(f"could not patch version in {label}")
        if text != original:
            path.write_text(text, encoding="utf-8")


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
    installer_only = "--installer-only" in sys.argv
    if installer_only:
        missing = [name for name in (
            "WalkToMordorDaemon.exe", "WalkToMordorWidget.exe",
            "WalkToMordorNudge.exe") if not (REPO / "dist" / name).exists()]
        if missing:
            sys.exit("--installer-only needs these in dist first: "
                     + ", ".join(missing))
        print("=== using existing exes ===")
    else:
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
    expected = REPO / "dist" / f"WalkToMordorSetup-{version}.exe"
    if expected.exists():
        print(f"done: {expected}")
    else:
        print(f"done (expected {expected} — check ISCC output)")


if __name__ == "__main__":
    main()
