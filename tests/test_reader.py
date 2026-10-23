"""Tests for BLE pad discovery."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import treadmill.reader as reader  # noqa: E402


class FakeScanner:
    devices = []

    def __init__(self, callback):
        self.callback = callback

    async def __aenter__(self):
        for device, adv in self.devices:
            self.callback(device, adv)
        return self

    async def __aexit__(self, *_exc):
        return False


def device(name, address="AA:BB"):
    return SimpleNamespace(name=name, address=address)


def adv(uuids=(), name=None):
    return SimpleNamespace(service_uuids=list(uuids), local_name=name)


class TestFindPad(unittest.TestCase):
    def _find(self, devices, hint="URTM"):
        FakeScanner.devices = devices
        with patch.object(reader, "BleakScanner", FakeScanner), \
                patch.object(reader.asyncio, "sleep", new=AsyncMock()):
            return asyncio.run(reader.find_pad(hint, quiet=True))

    def test_finds_named_pad(self):
        found = self._find([(device("URTM-123"), adv())])
        self.assertIsNotNone(found)
        self.assertEqual(found[1], "URTM-123")

    def test_does_not_fall_back_to_another_ftms_treadmill(self):
        found = self._find([(device("GenericTreadmill"),
                             adv([reader.FTMS_UUID]))])
        self.assertIsNone(found)

    def test_empty_hint_allows_any_device(self):
        found = self._find([(device("GenericTreadmill"),
                             adv([reader.FTMS_UUID]))], hint="")
        self.assertIsNotNone(found)


if __name__ == "__main__":
    unittest.main()
