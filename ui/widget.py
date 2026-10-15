#!/usr/bin/env python3
"""Floating always-on-top widget for Walk to Mordor.

Opens the dashboard's widget view (zoomable minimap + Start/Stop/speed
controls) in a small always-on-top window. The daemon must be running
(http://127.0.0.1:8471/).

Requires: pip install pywebview
(On Windows this uses the built-in WebView2/Edge engine — no extra
browser needed.)
"""

import sys

URL = "http://127.0.0.1:8471/?widget=1"


def main() -> None:
    try:
        import webview
    except ImportError:
        sys.exit("pywebview is not installed. Run:  pip install pywebview")
    webview.create_window(
        "Walk to Mordor",
        URL,
        width=320,
        height=300,
        min_size=(240, 200),
        on_top=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
