"""Tests for the WSL-side daemon HTTP client."""

import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bridge.client as client  # noqa: E402


class TestClient(unittest.TestCase):
    def setUp(self):
        client._reset_token()
        self.addCleanup(client._reset_token)

    def test_401_refreshes_token_once(self):
        seen = []

        def fake_urlopen(req, timeout=None):
            seen.append(req)
            if len(seen) == 1:
                raise urllib.error.HTTPError(
                    req.full_url, 401, "unauthorized", {}, None)
            return io.BytesIO(b'{"ok": true}')

        with patch.object(client, "_api_bases", return_value=["http://test"]), \
                patch.object(client, "_token", side_effect=["old", "new"]), \
                patch("bridge.client.urllib.request.urlopen",
                      side_effect=fake_urlopen):
            self.assertEqual(client.api_get("/api/stats"), {"ok": True})

        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer old")
        self.assertEqual(seen[1].get_header("Authorization"), "Bearer new")


if __name__ == "__main__":
    unittest.main()
