"""Tests for the FTMS control-point driver."""

import asyncio
import logging
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import treadmill.control as control  # noqa: E402
from treadmill.control import INCLINE_RANGE_UUID, SPEED_RANGE_UUID  # noqa: E402

log = logging.getLogger("test-control")


class FakeClient:
    def __init__(self, speed_range=b"\x00\x00\x90\x01",
                 incline_range=b"\x00\x00\x5a\x00"):
        self.ranges = {SPEED_RANGE_UUID: speed_range,
                       INCLINE_RANGE_UUID: incline_range}

    async def start_notify(self, _uuid, _callback):
        pass

    async def read_gatt_char(self, uuid):
        return self.ranges[uuid]


class TestController(unittest.TestCase):
    def test_setup_reads_min_and_max_ranges(self):
        async def scenario():
            c = control.TreadmillController(FakeClient(), lambda: 0.0, log)
            await c.setup()
            return c
        c = asyncio.run(scenario())
        self.assertEqual(c.min_speed, 0.0)
        self.assertEqual(c.max_speed, 4.0)
        self.assertEqual(c.min_incline, 0.0)
        self.assertEqual(c.max_incline, 9.0)

    def test_speed_and_incline_clamp_to_pad_limits(self):
        c = control.TreadmillController(FakeClient(), lambda: 0.0, log)
        c.min_speed, c.max_speed = 0.3, 4.0
        c.min_incline, c.max_incline = -2.0, 8.0
        self.assertTrue(asyncio.run(c.set_speed(99)))
        self.assertEqual(c.pending_speed, 4.0)
        self.assertTrue(asyncio.run(c.set_speed(0.1)))
        self.assertEqual(c.pending_speed, 0.5)
        self.assertTrue(asyncio.run(c.set_incline(99)))
        self.assertEqual(c.pending_incline, 8.0)
        self.assertTrue(asyncio.run(c.set_incline(-5)))
        self.assertEqual(c.pending_incline, -2.0)

    def test_indication_from_worker_thread_reaches_loop(self):
        async def scenario():
            c = control.TreadmillController(FakeClient(), lambda: 0.0, log)
            c._loop = asyncio.get_running_loop()
            t = threading.Thread(
                target=c._on_indication,
                args=(None, bytearray(b"\x80\x02\x01")),
            )
            t.start()
            t.join()
            return await asyncio.wait_for(c._responses.get(), 1)

        self.assertEqual(asyncio.run(scenario()), b"\x80\x02\x01")

    def test_start_waits_for_motion_before_applying_targets(self):
        async def scenario():
            speeds = iter([0.0, 0.0, 1.0, 1.0])
            c = control.TreadmillController(
                FakeClient(), lambda: next(speeds, 1.0), log)

            async def ok(_payload, _op):
                return True

            applied = []

            async def apply_pending():
                applied.append(c.get_speed())

            c._command = ok
            c._apply_pending = apply_pending
            with mock.patch.object(control, "SPINUP_POLL_S", 0.001):
                result = await c.start()
            return result, applied

        result, applied = asyncio.run(scenario())
        self.assertTrue(result)
        self.assertTrue(applied and applied[0] > 0)

    def test_start_fails_if_belt_never_moves(self):
        async def scenario():
            c = control.TreadmillController(FakeClient(), lambda: 0.0, log)

            async def ok(_payload, _op):
                return True

            c._command = ok
            with mock.patch.object(control, "SPINUP_POLL_S", 0.001), \
                    mock.patch.object(control, "SPINUP_TIMEOUT_S", 0.01):
                return await c.start()

        self.assertFalse(asyncio.run(scenario()))

    def test_start_does_not_wait_when_start_is_rejected(self):
        async def scenario():
            c = control.TreadmillController(FakeClient(), lambda: 0.0, log)

            async def rejected(_payload, _op):
                return False

            c._command = rejected
            return await c.start()

        self.assertFalse(asyncio.run(scenario()))


if __name__ == "__main__":
    unittest.main()
