"""Minimal HTTP client for the daemon's localhost API.

Every call returns None when the daemon isn't reachable, so callers can
fall back to direct database access.
"""

import json
import urllib.error
import urllib.request

API_BASE = "http://127.0.0.1:8471"
_TIMEOUT = 3


def _request(method: str, path: str, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(API_BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read() or b"{}")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def api_get(path: str):
    return _request("GET", path)


def api_post(path: str, payload: dict):
    return _request("POST", path, payload)
