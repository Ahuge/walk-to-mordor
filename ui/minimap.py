#!/usr/bin/env python3
"""minimap.py — tiny always-on-top Walk to Mordor overlay (tkinter).

Reads walks.db every 2 s: current route leg + progress, today's distance,
lifetime total, streak, live belt status. Buttons queue belt commands for
the daemon (same path as treadmill/control.py).

Usage:
    python ui/minimap.py     # console window (testing)
    pythonw ui/minimap.py    # no console
Close the window to hide it; run again to show it.
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.stats import (  # noqa: E402
    live_status,
    load_route,
    march_stats,
    open_db,
    route_position,
)
from treadmill.control import queue_command  # noqa: E402

REFRESH_MS = 2000


class Minimap(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Walk to Mordor")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        try:
            self.attributes("-toolwindow", True)  # slim title bar, no taskbar btn
        except tk.TclError:
            pass
        self.route = load_route()

        self.leg_var = tk.StringVar(value="…")
        self.dist_var = tk.StringVar(value="…")
        self.streak_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="…")
        self.progress = tk.DoubleVar(value=0.0)

        pad = {"padx": 8, "pady": 2}
        tk.Label(self, textvariable=self.leg_var,
                 font=("Segoe UI", 10, "bold")).pack(**pad)
        ttk.Progressbar(self, variable=self.progress,
                        maximum=100, length=220).pack(padx=8, pady=4)
        tk.Label(self, textvariable=self.dist_var,
                 font=("Segoe UI", 9)).pack(**pad)
        tk.Label(self, textvariable=self.streak_var,
                 font=("Segoe UI", 9)).pack(**pad)
        tk.Label(self, textvariable=self.status_var,
                 font=("Segoe UI", 9, "italic")).pack(**pad)

        btns = tk.Frame(self)
        btns.pack(padx=8, pady=(4, 8))
        tk.Button(btns, text="Start", width=7,
                  command=self.on_start).pack(side="left", padx=2)
        tk.Button(btns, text="Stop", width=7,
                  command=self.on_stop).pack(side="left", padx=2)
        tk.Button(btns, text="−", width=4,
                  command=lambda: self.bump_speed(-0.5)).pack(side="left", padx=2)
        tk.Button(btns, text="+", width=4,
                  command=lambda: self.bump_speed(0.5)).pack(side="left", padx=2)

        self.refresh()

    def on_start(self):
        if messagebox.askokcancel(
                "Start belt",
                "Belt will start shortly.\nMake sure the area is clear and the safety key is in."):
            queue_command("start", {})

    def on_stop(self):
        queue_command("stop", {})

    def bump_speed(self, delta: float):
        db = open_db()
        try:
            _text, _walking, speed = live_status(db)
        finally:
            db.close()
        base = speed if speed > 0.05 else 2.0
        queue_command("set_speed", {"kmh": round(base + delta, 1)})

    def refresh(self):
        try:
            db = open_db()
            try:
                today_m, total_m, streak = march_stats(db)
                status, _walking, _speed = live_status(db)
            finally:
                db.close()
            i, leg, frac = route_position(self.route, total_m)
            self.leg_var.set(
                f"Leg {i + 1}/{len(self.route['legs'])} — {leg['name']}")
            self.progress.set(frac * 100)
            self.dist_var.set(
                f"Today {today_m / 1000:.1f} km · Total {total_m / 1000:.1f} km")
            self.streak_var.set(f"🔥 {streak}-day streak" if streak else "")
            self.status_var.set(status)
        except Exception as e:  # noqa: BLE001
            self.status_var.set(f"db error: {e}")
        self.after(REFRESH_MS, self.refresh)


if __name__ == "__main__":
    Minimap().mainloop()
