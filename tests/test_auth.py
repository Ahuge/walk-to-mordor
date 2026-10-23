"""Tests for local API token authentication."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bridge.auth as auth  # noqa: E402


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        patcher = patch.object(auth, "data_dir", return_value=self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(auth.TOKEN_ENV, None)
        self.addCleanup(lambda: os.environ.pop(auth.TOKEN_ENV, None))

    def test_ensure_token_round_trip(self):
        token = auth.ensure_token()
        self.assertTrue(token)
        self.assertEqual(auth.current_token(), token)
        self.assertEqual((self.dir / auth.TOKEN_NAME).read_text().strip(),
                         token)

    def test_loopback_is_exempt(self):
        auth.ensure_token()
        self.assertTrue(auth.authorized({}, "127.0.0.1"))
        self.assertTrue(auth.authorized({}, "127.0.0.42"))
        self.assertTrue(auth.authorized({}, "::1"))

    def test_remote_requires_bearer_token(self):
        token = auth.ensure_token()
        self.assertFalse(auth.authorized({}, "192.168.1.10"))
        self.assertFalse(auth.authorized(
            {"Authorization": "Bearer wrong"}, "192.168.1.10"))
        self.assertTrue(auth.authorized(
            {"Authorization": f"Bearer {token}"}, "192.168.1.10"))
        self.assertTrue(auth.authorized(
            {"X-WTM-Token": token}, "192.168.1.10"))

    def test_env_override(self):
        os.environ[auth.TOKEN_ENV] = "env-token"
        self.assertEqual(auth.current_token(), "env-token")
        self.assertTrue(auth.authorized(
            {"Authorization": "Bearer env-token"}, "10.0.0.2"))


if __name__ == "__main__":
    unittest.main()
