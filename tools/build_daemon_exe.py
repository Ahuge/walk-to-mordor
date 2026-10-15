#!/usr/bin/env python3
"""Build a standalone WalkToMordor daemon exe via PyInstaller.

Bundles the daemon plus the web UI assets (dashboard.html, Leaflet,
map art). The exe reads/writes the SQLite DB at
%LOCALAPPDATA%\\walk-to-mordor\\walks.db like the source version.

Requires: pip install pyinstaller
Run from the repo root:  python tools/build_daemon_exe.py
Output: dist/WalkToMordorDaemon.exe
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    data = [
        # (source, dest in bundle)
        ("ui/dashboard.html", "ui"),
        ("ui/vendor", "ui/vendor"),
        ("packs/lotr/art/map.webp", "packs/lotr/art"),
        ("packs/lotr/art/markers.json", "packs/lotr/art"),
        ("packs/lotr/art/paths.json", "packs/lotr/art"),
        ("packs/lotr/art/journey.json", "packs/lotr/art"),
        ("packs/lotr/art/icon.png", "packs/lotr/art"),
        ("packs/lotr/route.json", "packs/lotr"),
    ]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",  # keep console for the log; task runs it hidden anyway
        "--name", "WalkToMordorDaemon",
        "--collect-all", "bleak",
    ]
    for src, dest in data:
        src_path = REPO / src
        if not src_path.exists():
            print(f"warning: missing {src}, skipping")
            continue
        cmd += ["--add-data", f"{src_path};{dest}"]
    cmd.append(str(REPO / "bridge" / "daemon.py"))
    print("building daemon…")
    subprocess.run(cmd, cwd=REPO, check=True)
    exe = REPO / "dist" / "WalkToMordorDaemon.exe"
    print(f"done: {exe}")


if __name__ == "__main__":
    main()
