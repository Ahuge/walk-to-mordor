#!/usr/bin/env python3
"""Daily walk nudge: shows a Windows notification if no walk yet today.

Run via scheduled task (e.g. daily at 11am). Checks the walks DB; if
there are no marches today with distance > 0, shows a toast reminder.

Usage:
    python tools/nudge.py              # check and notify if needed
    python tools/nudge.py --force      # always show the notification
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo or as a frozen exe.
if getattr(sys, "frozen", False):
    REPO = Path(sys.executable).resolve().parent
else:
    REPO = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(REPO))


def walked_today() -> bool:
    from bridge.store import open_db, march_stats
    db = open_db()
    try:
        today_m, _, _, _, _ = march_stats(db)
        return today_m > 50  # at least 50m counts as a walk
    finally:
        db.close()


def notify() -> None:
    title = "Walk to Mordor"
    msg = "No walk yet today — time to hit the road to Mordor! 🚶"
    try:
        from plyer import notification
        notification.notify(title=title, message=msg, app_name=title,
                            timeout=30)
        return
    except Exception:
        pass
    # Fallback: PowerShell toast.
    try:
        import subprocess
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager, "
            "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
            "$t = [Windows.UI.Notifications.ToastNotificationManager]::"
            "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            f"$t.GetElementsByTagName('text')[0].AppendChild($t.CreateTextNode('{title}')) > $null; "
            f"$t.GetElementsByTagName('text')[1].AppendChild($t.CreateTextNode('{msg}')) > $null; "
            "[Windows.UI.Notifications.ToastNotificationManager]::"
            "CreateToastNotifier('WalkToMordor').Show($t);"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=15)
    except Exception as e:
        print(f"nudge failed: {e}", file=sys.stderr)


def main() -> None:
    if "--force" in sys.argv:
        notify()
        return
    # Don't nudge before 10am local — give the morning a chance.
    if datetime.now().hour < 10:
        return
    try:
        if not walked_today():
            notify()
    except Exception as e:
        print(f"nudge check failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
