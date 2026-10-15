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

# Drag handle + close button injected into the page (frameless windows
# have no title bar). The hand button toggles "move mode": when on,
# dragging moves the window; when off, the map pans normally.
DRAG_JS = """
(function() {
  if (window.__wtmWidget) return; window.__wtmWidget = true;
  var moveMode = false, sx, sy;
  function btn(right) {
    var b = document.createElement('div');
    b.style.cssText = 'position:fixed;top:3px;right:' + right + 'px;z-index:10000;'
      + 'cursor:pointer;color:#f3e9d2;background:rgba(0,0,0,.5);border-radius:9px;'
      + 'width:18px;height:18px;font-size:12px;line-height:18px;text-align:center;'
      + 'font-family:sans-serif;display:flex;align-items:center;justify-content:center;';
    document.body.appendChild(b);
    return b;
  }
  var hand = btn(28);
  hand.title = 'Move window (click to toggle, Esc to stop)';
  hand.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none"'
    + ' stroke="#f3e9d2" stroke-width="2.4" stroke-linecap="round">'
    + '<path d="M12 3v18M3 12h18M12 3L9 6m3-3l3 3M12 21l-3-3m3 3l3-3'
    + 'M3 12l3-3m-3 3l3 3M21 12l-3-3m3 3l-3 3"/></svg>';
  var x = btn(5);
  x.title = 'Close widget';
  x.textContent = '\\u00d7';
  x.onclick = function() { window.pywebview.api.close(); };
  // Resize grip, bottom-right.
  var grip = document.createElement('div');
  grip.title = 'Resize';
  grip.style.cssText = 'position:fixed;bottom:0;right:0;width:18px;height:18px;'
    + 'z-index:10000;cursor:nwse-resize;';
  grip.innerHTML = '<svg width="18" height="18" viewBox="0 0 18 18">'
    + '<path d="M18 0 L0 18 L18 18 Z" fill="rgba(243,233,210,.30)"/></svg>';
  document.body.appendChild(grip);
  var rx, ry;
  grip.addEventListener('mousedown', function(e) {
    rx = e.screenX; ry = e.screenY;
    window.pywebview.api.resizestart(rx, ry);
    e.preventDefault(); e.stopPropagation();
  }, true);
  hand.onclick = function() {
    moveMode = !moveMode;
    hand.style.background = moveMode ? 'rgba(176,141,43,.9)' : 'rgba(0,0,0,.5)';
    document.body.style.cursor = moveMode ? 'move' : '';
  };
  window.addEventListener('mousedown', function(e) {
    if (!moveMode) return;
    if (hand.contains(e.target) || x.contains(e.target)
        || grip.contains(e.target)) return;
    sx = e.screenX; sy = e.screenY;
    window.pywebview.api.dragstart(sx, sy);
    e.preventDefault(); e.stopPropagation();
  }, true);
  window.addEventListener('mousemove', function(e) {
    if (rx !== undefined) window.pywebview.api.resizemove(e.screenX, e.screenY);
    else if (moveMode && sx !== undefined)
      window.pywebview.api.dragmove(e.screenX, e.screenY);
  });
  window.addEventListener('mouseup', function() {
    rx = undefined; window.pywebview.api.resizeend();
    sx = undefined; window.pywebview.api.dragend();
  });
  window.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && moveMode) hand.onclick();
  });
})();
"""


class Api:
    """JS bridge: window dragging + close for the frameless window.

    Window position goes through raw Win32 (FindWindow/GetWindowRect/
    SetWindowPos) — pywebview's own x/y/move properties recurse on
    frameless windows. The bridge holds no Window reference at all.
    """

    def __init__(self):
        self._drag = None
        self._hwnd = None

    def _hwnd_(self):
        if not self._hwnd:
            self._hwnd = _widget_hwnd()
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

    def _size(self):
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(self._hwnd_(),
                                          ctypes.byref(rect))
        return rect.right - rect.left, rect.bottom - rect.top

    def resizestart(self, sx, sy):
        try:
            w, h = self._size()
            self._rsz = (sx, sy, w, h)
        except Exception:
            self._rsz = None

    def resizemove(self, sx, sy):
        if not getattr(self, "_rsz", None):
            return
        try:
            import ctypes

            x0, y0, w0, h0 = self._rsz
            nw = max(200, w0 + int(sx - x0))
            nh = max(160, h0 + int(sy - y0))
            # SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(self._hwnd_(), 0,
                                              0, 0, nw, nh, 0x0016)
        except Exception:
            pass

    def resizeend(self):
        self._rsz = None

    def close(self):
        try:
            import ctypes

            hwnd = self._hwnd_()
            if hwnd:
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        except Exception:
            pass


def _move_bottom_right():
    """Position bottom-right of the work area (screen minus taskbar)."""
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        # SPI_GETWORKAREA = 0x0030
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0,
                                                   ctypes.byref(rect), 0)
        x, y = rect.right - WIDTH - 12, rect.bottom - HEIGHT - 12
        hwnd = _widget_hwnd()
        if hwnd:
            # SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0015)
    except Exception:
        pass


def _widget_hwnd():
    """HWND of our widget window: same process + exact title.

    (FindWindowW by title alone can grab the browser tab showing the
    dashboard instead.)
    """
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    target_pid = k32.GetCurrentProcessId()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != target_pid:
            return True
        n = u32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value == TITLE:
            found.append(hwnd)
        return True

    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def _set_window_icon():
    """Best-effort: give the widget window our icon on Windows."""
    try:
        import ctypes
        icon = Path(__file__).resolve().parent.parent / "packs" / "lotr" / "art" / "icon.ico"
        if not icon.exists():
            print(f"icon: missing {icon}")
            return
        u32 = ctypes.windll.user32
        hwnd = _widget_hwnd()
        if not hwnd:
            print("icon: widget window not found")
            return
        # IMAGE_ICON=1, LR_LOADFROMFILE=0x10
        hicon = u32.LoadImageW(None, str(icon), 1, 0, 0, 0x10)
        if not hicon:
            print(f"icon: LoadImageW failed for {icon}")
            return
        u32.SendMessageW(hwnd, 0x0080, 1, hicon)  # WM_SETICON ICON_BIG
        u32.SendMessageW(hwnd, 0x0080, 0, hicon)  # WM_SETICON ICON_SMALL
        # Class icons too, so the taskbar picks it up.
        set_cls = getattr(u32, "SetClassLongPtrW", None)
        if set_cls:
            set_cls(hwnd, -14, hicon)  # GCLP_HICON
            set_cls(hwnd, -34, hicon)  # GCLP_HICONSM
        print(f"icon: set on hwnd={hwnd}")
    except Exception as e:
        print(f"icon: failed: {e}")


def main() -> None:
    try:
        import webview
        try:
            from importlib.metadata import version
            print("pywebview", version("pywebview"))
        except Exception:
            pass
    except ImportError:
        sys.exit("pywebview is not installed. Run:  pip install pywebview")
    framed = "--framed" in sys.argv
    api = Api()
    # Keep create_window minimal: frameless windows are quirky in
    # pywebview's WinForms backend, so positioning is done via Win32
    # after load, not through pywebview's own x/y properties.
    win = webview.create_window(
        TITLE,
        URL,
        width=WIDTH,
        height=HEIGHT,
        min_size=(240, 200),
        frameless=not framed,
        on_top=True,
        js_api=api,
    )

    def on_loaded():
        _move_bottom_right()
        try:
            win.evaluate_js(DRAG_JS)
        except Exception:
            pass
        _set_window_icon()
        # Re-apply shortly after: WebView2 can reset the icon on navigate.
        try:
            import threading
            threading.Timer(2.0, _set_window_icon).start()
        except Exception:
            pass

    win.events.loaded += on_loaded
    try:
        webview.start()
    except Exception as e:
        sys.exit(f"widget failed to start: {e}\n"
                 f"try: python ui/widget.py --framed")


if __name__ == "__main__":
    main()
