#!/usr/bin/env python3
"""Install (or remove) the Walk to Mordor daemon as a Windows logon task.

The task runs at every logon under pythonw (no console window) and keeps
the BLE bridge alive in the background.

Usage:
    python tools/install_windows.py              # install / refresh
    python tools/install_windows.py --uninstall  # remove
"""

import subprocess
import sys
from pathlib import Path

TASK_NAME = "WalkToMordor"


def main() -> None:
    if "--uninstall" in sys.argv:
        subprocess.run(
            ["schtasks", "/delete", "/tn", TASK_NAME, "/f"], check=False)
        print(f"task '{TASK_NAME}' removed (if it existed)")
        return
    if sys.platform != "win32":
        sys.exit("this installer is for Windows only")
    repo = Path(__file__).resolve().parent.parent
    daemon = repo / "bridge" / "daemon.py"
    if not daemon.exists():
        sys.exit(f"daemon not found: {daemon}")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        sys.exit(f"pythonw.exe not found next to {sys.executable}")
    task_run = f'"{pythonw}" "{daemon}"'
    subprocess.run(
        ["schtasks", "/create", "/tn", TASK_NAME,
         "/tr", task_run, "/sc", "onlogon", "/rl", "limited", "/f"],
        check=True,
    )
    print(f"installed: logon task '{TASK_NAME}'")
    print(f"  runs: {task_run}")
    print("  data: %LOCALAPPDATA%\\walk-to-mordor\\walks.db")
    print("Take effect on next logon, or start it now with:")
    print(f'  schtasks /run /tn "{TASK_NAME}"')


if __name__ == "__main__":
    main()
