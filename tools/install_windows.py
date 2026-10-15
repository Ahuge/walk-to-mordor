#!/usr/bin/env python3
"""Install (or remove) the Walk to Mordor daemon as a Windows logon task.

The task runs at every logon under pythonw (no console window) and keeps
the BLE bridge alive in the background.

Usage:
    python tools/install_windows.py              # install / refresh daemon
    python tools/install_windows.py --minimap    # also auto-start the minimap
    python tools/install_windows.py --uninstall  # remove
"""

import subprocess
import sys
from pathlib import Path

TASK_NAME = "WalkToMordor"
MINIMAP_TASK_NAME = "WalkToMordorMinimap"


def _create_task(name: str, target: Path) -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        sys.exit(f"pythonw.exe not found next to {sys.executable}")
    task_run = f'"{pythonw}" "{target}"'
    subprocess.run(
        ["schtasks", "/create", "/tn", name,
         "/tr", task_run, "/sc", "onlogon", "/rl", "limited", "/f"],
        check=True,
    )
    print(f"installed: logon task '{name}'")
    print(f"  runs: {task_run}")


def main() -> None:
    if "--uninstall" in sys.argv:
        for name in (TASK_NAME, MINIMAP_TASK_NAME):
            subprocess.run(
                ["schtasks", "/delete", "/tn", name, "/f"], check=False)
        print("tasks removed (if they existed)")
        return
    if sys.platform != "win32":
        sys.exit("this installer is for Windows only")
    repo = Path(__file__).resolve().parent.parent
    daemon = repo / "bridge" / "daemon.py"
    if not daemon.exists():
        sys.exit(f"daemon not found: {daemon}")
    _create_task(TASK_NAME, daemon)
    print("  data: %LOCALAPPDATA%\\walk-to-mordor\\walks.db")
    if "--minimap" in sys.argv:
        minimap = repo / "ui" / "minimap.py"
        if not minimap.exists():
            sys.exit(f"minimap not found: {minimap}")
        _create_task(MINIMAP_TASK_NAME, minimap)
    print("Take effect on next logon, or start now with:")
    print(f'  schtasks /run /tn "{TASK_NAME}"')


if __name__ == "__main__":
    main()
