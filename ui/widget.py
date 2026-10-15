#!/usr/bin/env python3
"""Floating always-on-top widget for Walk to Mordor.

Borderless always-on-top window showing the dashboard's widget view
(zoomable minimap + Start/Stop/speed controls). Opens bottom-right.
Drag by the top strip, close with the × button (or Alt+F4).
The daemon must be running (http://127.0.0.1:8471/).

Requires: pip install pywebview
(On Windows this uses the built-in WebView2/Edge engine.)
"""

import sys
from pathlib import Path

URL = "http://127.0.0.1:8471/?widget=1"
TITLE = "Walk to Mordor"
WIDTH, HEIGHT = 320, 300

# Drag strip + close button injected into the page (frameless windows
# have no title bar to drag or close with).
DRAG_JS = """
(function() {
  if (window.__wtmWidget) return; window.__wtmWidget = true;
  var bar = document.createElement('div');
  bar.style.cssText = 'position:fixed;top:0;left:0;right:0;height:16px;z-index:9999;'
    + 'cursor:move;background:transparent;';
  var x = document.createElement('div');
  x.textContent = '\\u00d7';
  x.title = 'Close widget';
  x.style.cssText = 'position:fixed;top:3px;right:5px;z-index:10000;cursor:pointer;'
    + 'color:#f3e9d2;background:rgba(0,0,0,.5);border-radius:9px;width:18px;height:18px;'
    + 'font-size:13px;line-height:18px;text-align:center;font-family:sans-serif;';
  x.onclick = function() { window.pywebview.api.close(); };
  var sx, sy;
  bar.addEventListener('mousedown', function(e) {
    sx = e.screenX; sy = e.screenY; window.pywebview.api.dragstart(sx, sy);
  });
  window.addEventListener('mousemove', function(e) {
    if (sx !== undefined) window.pywebview.api.dragmove(e.screenX, e.screenY);
  });
  window.addEventListener('mouseup', function() {
    sx = undefined; window.pywebview.api.dragend();
  });
  document.body.appendChild(bar);
  document.body.appendChild(x);
})();
"""


class Api:
    """JS bridge: window dragging + close for the frameless window.

    Window position goes through raw Win32 (FindWindow/GetWindowRect/
    SetWindowPos) — pywebview's own x/y/move properties recurse on
    frameless windows.
    """

    def __init__(self):
        self.win = None
        self._drag = None
        self._hwnd = None

    def _hwnd_(self):
        import ctypes

        if not self._hwnd:
            self._hwnd = ctypes.windll.user32.FindWindowW(None, TITLE)
        return self._hwnd

    def _pos(self):
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(self._hwnd_(),
                                          ctypes.byref(rect))
        return rect.left, rect.top

    def dragstart(self, sx, sy):
        try:
            wx, wy = self._pos()
            self._drag = (sx, sy, wx, wy)
        except Exception:
            self._drag = None

    def dragmove(self, sx, sy):
        if not self._drag:
            return
        try:
            import ctypes

            x0, y0, wx, wy = self._drag
            nx, ny = wx + int(sx - x0), wy + int(sy - y0)
            # SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(self._hwnd_(), 0,
                                              nx, ny, 0, 0, 0x0015)
        except Exception:
            pass

    def dragend(self):
        self._drag = None

    def close(self):
        if self.win:
            self.win.destroy()


def _launch_xy():
    """Bottom-right of the work area (screen minus taskbar)."""
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        # SPI_GETWORKAREA = 0x0030
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0,
                                                   ctypes.byref(rect), 0)
        return (rect.right - WIDTH - 12, rect.bottom - HEIGHT - 12)
    except Exception:
        return (None, None)


def _set_window_icon():
    """Best-effort: give the frameless window our icon on Windows."""
    try:
        import ctypes
        icon = Path(__file__).resolve().parent.parent / "packs" / "lotr" / "art" / "icon.ico"
        if not icon.exists():
            return
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW(None, TITLE)
        if not hwnd:
            return
        # IMAGE_ICON=1, LR_LOADFROMFILE=0x10
        hicon = u32.LoadImageW(None, str(icon), 1, 0, 0, 0x10)
        if hicon:
            u32.SendMessageW(hwnd, 0x0080, 1, hicon)  # WM_SETICON ICON_BIG
            u32.SendMessageW(hwnd, 0x0080, 0, hicon)  # WM_SETICON ICON_SMALL
    except Exception:
        pass


def main() -> None:
    try:
        import webview
    except ImportError:
        sys.exit("pywebview is not installed. Run:  pip install pywebview")
    api = Api()
    x, y = _launch_xy()
    kwargs = dict(width=WIDTH, height=HEIGHT, min_size=(240, 200),
                  frameless=True, on_top=True, js_api=api)
    if x is not None:
        kwargs["x"], kwargs["y"] = x, y
    win = webview.create_window(TITLE, URL, **kwargs)
    api.win = win

    def on_loaded():
        try:
            win.evaluate_js(DRAG_JS)
        except Exception:
            pass
        _set_window_icon()

    win.events.loaded += on_loaded
    try:
        webview.start()
    except Exception as e:
        sys.exit(f"widget failed to start: {e}")


if __name__ == "__main__":
    main()
