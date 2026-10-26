"""Minimal HTTP client for the daemon's localhost API.

Every call returns None when the daemon isn't reachable, so callers can
fall back to direct database access.
"""

import json
import os
import urllib.error
import urllib.request

API_PORT = 8471
_TIMEOUT = 3
_TOKEN = None


def _token():
    """Bearer token for remote daemon calls; loopback ignores it."""
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    token = os.environ.get("WALK_TO_MORDOR_TOKEN", "").strip()
    if not token:
        try:
            from bridge.auth import current_token
            token = current_token() or ""
        except Exception:  # noqa: BLE001
            token = ""
    # Cache only a real token: the daemon may create the file after the
    # first request, and a long-running --watch process must pick it up.
    if token:
        _TOKEN = token
    return token


def _reset_token():
    global _TOKEN
    _TOKEN = None


def _wsl_host_ip():
    """Windows host IP as seen from WSL2 (the resolv.conf nameserver)."""
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver":
                    ip = parts[1]
                    if not ip.startswith("127."):
                        return ip
    except OSError:
        pass
    return None


def _api_bases():
    bases = [f"http://127.0.0.1:{API_PORT}"]
    host_ip = _wsl_host_ip()
    if host_ip:
        bases.append(f"http://{host_ip}:{API_PORT}")
    return bases


def _request(method: str, path: str, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last_error = None
    token = _token()
    for base in _api_bases():
        for attempt in (0, 1):
            req = urllib.request.Request(base + path, data=data, method=method)
            if data:
                req.add_header("Content-Type", "application/json")
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            try:
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    return json.loads(resp.read() or b"{}")
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 0:
                    _reset_token()
                    token = _token()
                    continue
                last_error = e
                break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_error = e
                break
    return None


def api_get(path: str):
    return _request("GET", path)


def api_post(path: str, payload: dict):
    return _request("POST", path, payload)


def api_delete(path: str):
    return _request("DELETE", path)
