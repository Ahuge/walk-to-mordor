#!/usr/bin/env python3
"""Install (or remove) Walk to Mordor as Windows logon tasks.

The daemon task runs at every logon under pythonw (no console window)
and keeps the BLE bridge alive in the background. The optional widget
task launches the floating map widget after the daemon is up. The
optional nudge task shows a daily reminder if no walk yet.

Usage:
    python tools/install_windows.py              # install / refresh daemon
    python tools/install_windows.py --widget     # also auto-start the widget
    python tools/install_windows.py --nudge      # also daily walk reminder
    python tools/install_windows.py --minimap    # also auto-start the minimap
    python tools/install_windows.py --uninstall  # remove
"""

import subprocess
import sys
from pathlib import Path

TASK_NAME = "WalkToMordor"
WIDGET_TASK_NAME = "WalkToMordorWidget"
NUDGE_TASK_NAME = "WalkToMordorNudge"
MINIMAP_TASK_NAME = "WalkToMordorMinimap"


def _create_daily_task(name: str, target: Path, time: str) -> None:
    """Daily task at HH:MM (24h)."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        sys.exit(f"pythonw.exe not found next to {sys.executable}")
    task_run = f'"{pythonw}" "{target}"'
    subprocess.run(
        ["schtasks", "/create", "/tn", name, "/tr", task_run,
         "/sc", "daily", "/st", time, "/rl", "limited", "/f"],
        check=True,
    )
    print(f"installed: daily task '{name}' at {time}")
    print(f"  runs: {task_run}")


def _create_task(name: str, target: Path, delay_s: int = 0) -> None:
    if target.suffix.lower() == ".exe":
        task_run = f'"{target}"'
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not pythonw.exists():
            sys.exit(f"pythonw.exe not found next to {sys.executable}")
        task_run = f'"{pythonw}" "{target}"'
    cmd = ["schtasks", "/create", "/tn", name,
           "/tr", task_run, "/sc", "onlogon", "/rl", "limited", "/f"]
    if delay_s:
        cmd += ["/delay", f"0000:{delay_s:02d}"]
    subprocess.run(cmd, check=True)
    print(f"installed: logon task '{name}'")
    print(f"  runs: {task_run}" + (f" (delay {delay_s}s)" if delay_s else ""))


def _stop_daemon(repo: Path) -> None:
    """Stop any running daemon before replacing tasks (and their exes)."""
    script = repo / "installer" / "stop_daemon.ps1"
    if not script.exists():
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script)],
        check=False,
    )


def _harden_tasks(repo: Path) -> None:
    """Add restart/battery/runtime settings that schtasks cannot express."""
    script = repo / "installer" / "harden_tasks.ps1"
    if not script.exists():
        return
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script)],
        check=False,
    )
    if result.returncode != 0:
        print("warning: could not harden scheduled tasks; rerun manually:")
        print(f'  powershell -ExecutionPolicy Bypass -File "{script}"')


def _ensure_widget_exe(repo: Path) -> Path:
    exe = repo / "dist" / "WalkToMordorWidget.exe"
    if exe.exists():
        return exe
    print("widget exe not found, building…")
    subprocess.run([sys.executable, "tools/build_widget_exe.py"],
                   cwd=repo, check=True)
    if not exe.exists():
        sys.exit("widget build did not produce the exe")
    return exe


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    if "--uninstall" in sys.argv:
        if sys.platform == "win32":
            _stop_daemon(repo)
        for name in (TASK_NAME, WIDGET_TASK_NAME, NUDGE_TASK_NAME,
                     MINIMAP_TASK_NAME):
            subprocess.run(
                ["schtasks", "/delete", "/tn", name, "/f"], check=False)
        print("tasks removed (if they existed)")
        return
    if sys.platform != "win32":
        sys.exit("this installer is for Windows only")
    daemon = repo / "bridge" / "daemon.py"
    if not daemon.exists():
        sys.exit(f"daemon not found: {daemon}")
    _stop_daemon(repo)
    _create_task(TASK_NAME, daemon)
    print("  data: %LOCALAPPDATA%\\walk-to-mordor\\walks.db")
    if "--widget" in sys.argv:
        exe = _ensure_widget_exe(repo)
        _create_task(WIDGET_TASK_NAME, exe, delay_s=30)
    if "--nudge" in sys.argv:
        nudge = repo / "tools" / "nudge.py"
        if not nudge.exists():
            sys.exit(f"nudge not found: {nudge}")
        _create_daily_task(NUDGE_TASK_NAME, nudge, "11:00")
    if "--minimap" in sys.argv:
        minimap = repo / "ui" / "minimap.py"
        if not minimap.exists():
            sys.exit(f"minimap not found: {minimap}")
        _create_task(MINIMAP_TASK_NAME, minimap)
    _harden_tasks(repo)
    print("Take effect on next logon, or start now with:")
    print(f'  schtasks /run /tn "{TASK_NAME}"')
    if "--widget" in sys.argv:
        print(f'  schtasks /run /tn "{WIDGET_TASK_NAME}"')


if __name__ == "__main__":
    main()
