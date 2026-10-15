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
import tempfile
from pathlib import Path

URL = "http://127.0.0.1:8471/?widget=1"
TITLE = "Walk to Mordor"
WIDTH, HEIGHT = 320, 300

# Debug log for drag diagnosis.
_DBG = Path(tempfile.gettempdir()) / "wtm_widget_debug.log"
def _dbg(msg):
    try:
        with open(_DBG, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

# Drag handle + close button + resize grip injected into the page
# (frameless windows have no title bar). The hand is a press-and-drag
# handle: hold it and drag to move the window. Otherwise the map pans.
DRAG_JS = """
(function() {
  if (window.__wtmWidget) return; window.__wtmWidget = true;
  window.__wtmWidgetVer = 'press-drag-v2';
  var sx, sy, rx, ry, dragging = false;
  function btn(right) {
    var b = document.createElement('div');
    b.style.cssText = 'position:fixed;top:3px;right:' + right + 'px;z-index:10000;'
      + 'color:#f3e9d2;background:rgba(0,0,0,.5);border-radius:9px;'
      + 'width:18px;height:18px;font-size:12px;line-height:18px;text-align:center;'
      + 'font-family:sans-serif;display:flex;align-items:center;justify-content:center;';
    document.body.appendChild(b);
    return b;
  }
  var hand = btn(28);
  hand.title = 'Drag to move window';
  hand.style.cursor = 'move';
  hand.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none"'
    + ' stroke="#f3e9d2" stroke-width="2.4" stroke-linecap="round">'
    + '<path d="M12 3v18M3 12h18M12 3L9 6m3-3l3 3M12 21l-3-3m3 3l3-3'
    + 'M3 12l3-3m-3 3l3 3M21 12l-3-3m3 3l-3 3"/></svg>';
  var x = btn(5);
  x.title = 'Close widget';
  x.style.cursor = 'pointer';
  x.textContent = '\\u00d7';
  x.onclick = function() { window.pywebview.api.close(); };
  // Open full dashboard in the default browser.
  var www = btn(51);
  www.title = 'Open in browser';
  www.style.cursor = 'pointer';
  www.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none"'
    + ' stroke="#f3e9d2" stroke-width="2.4" stroke-linecap="round">'
    + '<path d="M14 4h6v6M20 4l-9 9M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/></svg>';
  www.onclick = function() { window.pywebview.api.open_browser(); };
  // Resize grip, bottom-right.
  var grip = document.createElement('div');
  grip.title = 'Resize';
  grip.style.cssText = 'position:fixed;bottom:0;right:0;width:18px;height:18px;'
    + 'z-index:10000;cursor:nwse-resize;';
  grip.innerHTML = '<svg width="18" height="18" viewBox="0 0 18 18">'
    + '<path d="M18 0 L0 18 L18 18 Z" fill="rgba(243,233,210,.30)"/></svg>';
  document.body.appendChild(grip);
  // Press-and-drag on the hand moves the window (no toggle state).
  hand.addEventListener('mousedown', function(e) {
    dragging = true;
    sx = e.screenX; sy = e.screenY;
    try { window.pywebview.api.jslog('hand mousedown target=' +
      (e.target.tagName || '?')); } catch (err) {}
    window.pywebview.api.dragstart(sx, sy);
    hand.style.background = 'rgba(176,141,43,.9)';
    e.preventDefault(); e.stopPropagation();
  }, true);
  grip.addEventListener('mousedown', function(e) {
    rx = e.screenX; ry = e.screenY;
    window.pywebview.api.resizestart(rx, ry);
    e.preventDefault(); e.stopPropagation();
  }, true);
  window.addEventListener('mousemove', function(e) {
    // If no button is pressed, any drag state is stale — reset it.
    if (e.buttons === 0) {
      rx = undefined; sx = undefined; dragging = false;
      hand.style.background = 'rgba(0,0,0,.5)';
      return;
    }
    if (rx !== undefined) window.pywebview.api.resizemove(e.screenX, e.screenY);
    else if (dragging && sx !== undefined)
      window.pywebview.api.dragmove(e.screenX, e.screenY);
  });
  window.addEventListener('mouseup', function() {
    rx = undefined; window.pywebview.api.resizeend();
    sx = undefined; dragging = false;
    window.pywebview.api.dragend();
    hand.style.background = 'rgba(0,0,0,.5)';
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

    def jslog(self, msg):
        _dbg(f"js: {msg}")

    def open_browser(self):
        import webbrowser
        try:
            webbrowser.open("http://127.0.0.1:8471/")
        except Exception as e:
            _dbg(f"open_browser failed: {e}")

    def _pos(self):
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(self._hwnd_(),
                                          ctypes.byref(rect))
        return rect.left, rect.top

    def dragstart(self, sx, sy):
        _dbg(f"dragstart sx={sx} sy={sy}")
        try:
            wx, wy = self._pos()
            self._drag = (sx, sy, wx, wy)
        except Exception as e:
            _dbg(f"dragstart failed: {e}")
            self._drag = None

    def dragmove(self, sx, sy):
        if not self._drag:
            return
        _dbg(f"dragmove sx={sx} sy={sy} drag={self._drag}")
        try:
            import ctypes

            x0, y0, wx, wy = self._drag
            nx, ny = wx + int(sx - x0), wy + int(sy - y0)
            # SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(self._hwnd_(), 0,
                                              nx, ny, 0, 0, 0x0015)
        except Exception as e:
            _dbg(f"dragmove failed: {e}")
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


def _make_borderless():
    """Strip the title bar / thick frame via Win32 for a borderless look.

    We do this instead of pywebview's frameless=True because pywebview
    6.x's frameless mode moves the window on any drag (bug).
    """
    try:
        import ctypes

        hwnd = _widget_hwnd()
        if not hwnd:
            return
        u32 = ctypes.windll.user32
        GWL_STYLE = -16
        WS_CAPTION = 0x00C00000
        WS_THICKFRAME = 0x00040000
        style = u32.GetWindowLongW(hwnd, GWL_STYLE)
        style &= ~(WS_CAPTION | WS_THICKFRAME)
        u32.SetWindowLongW(hwnd, GWL_STYLE, style)
        # SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED
        u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        _dbg("made borderless via Win32")
    except Exception as e:
        _dbg(f"borderless failed: {e}")


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
            # Prefer the visible window; keep hidden ones as fallback.
            if u32.IsWindowVisible(hwnd):
                found.insert(0, hwnd)
            else:
                found.append(hwnd)
        return True

    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def _set_window_icon():
    """Best-effort: give the widget window our icon on Windows.

    Skipped for frozen (PyInstaller) builds — the icon is baked into
    the exe itself.
    """
    if getattr(sys, "frozen", False):
        return
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
    # Clear the debug log on startup so it's fresh.
    try:
        _DBG.unlink(missing_ok=True)
    except Exception:
        pass
    _dbg("widget.py starting (press-drag-v2 + jslog)")
    framed = "--framed" in sys.argv
    api = Api()
    # NOTE: frameless=False — pywebview 6.x's frameless mode drags the
    # window on any mouse drag (bug). We strip the chrome via Win32
    # instead (_make_borderless) for a borderless look without the bug.
    win = webview.create_window(
        TITLE,
        URL,
        width=WIDTH,
        height=HEIGHT,
        min_size=(240, 200),
        frameless=False,
        on_top=True,
        js_api=api,
    )

    def on_loaded():
        _move_bottom_right()
        if not framed:
            _make_borderless()
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
