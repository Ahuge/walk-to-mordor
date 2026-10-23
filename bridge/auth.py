"""Local API authentication.

The daemon binds 0.0.0.0 so WSL2 can reach it, which also exposes the
belt-control API to the LAN. This module issues a random bearer token in
the data directory and checks it for remote callers. Loopback callers
(the Windows dashboard) stay password-free, so the UI needs no login.

Set WALK_TO_MORDOR_TOKEN to override the file (useful for tests).
"""

import hmac
import ipaddress
import os
import secrets
from pathlib import Path
from typing import Mapping, Optional

from bridge.store import data_dir

TOKEN_ENV = "WALK_TO_MORDOR_TOKEN"
TOKEN_NAME = "api.token"


def token_path() -> Path:
    return data_dir() / TOKEN_NAME


def ensure_token() -> Optional[str]:
    """Create the token file if needed and return the token."""
    token = current_token()
    if token:
        return token
    token = secrets.token_urlsafe(32)
    path = token_path()
    try:
        path.write_text(token + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows ACLs are inherited; read access is already local
    except OSError:
        return None
    return token


def current_token() -> Optional[str]:
    env = os.environ.get(TOKEN_ENV, "").strip()
    if env:
        return env
    try:
        token = token_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def is_loopback(address: Optional[str]) -> bool:
    if not address:
        return False
    try:
        return ipaddress.ip_address(address.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def authorized(headers: Mapping[str, str], client_ip: Optional[str]) -> bool:
    """True when the caller may use the API.

    Remote callers fail closed: if the daemon could not create/read its
    token, they are rejected rather than silently allowed to drive the
    belt.
    """
    if is_loopback(client_ip):
        return True
    expected = current_token()
    if not expected:
        return False
    supplied = headers.get("Authorization", "")
    scheme, _, value = supplied.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        candidate = value.strip()
    else:
        candidate = (headers.get("X-WTM-Token") or "").strip()
    return bool(candidate) and hmac.compare_digest(candidate, expected)
