"""Tests for resilient Discord startup behavior."""

import asyncio
import unittest

from utils.bot_startup import run_with_retry


class FatalStartupError(Exception):
    """Represents a non-retryable authentication/configuration failure."""


class BotStartupRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_transient_failure_then_succeeds(self):
        attempts = 0
        delays = []

        async def operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise OSError("temporary DNS failure")
            return "connected"

        async def fake_sleep(delay):
            delays.append(delay)

        result = await run_with_retry(
            operation,
            initial_delay=2,
            max_delay=10,
            sleep=fake_sleep,
        )

        self.assertEqual(result, "connected")
        self.assertEqual(attempts, 3)
        self.assertEqual(delays, [2, 4])

    async def test_caps_exponential_backoff(self):
        attempts = 0
        delays = []

        async def operation():
            nonlocal attempts
            attempts += 1
            if attempts < 5:
                raise ConnectionError("offline")
            return None

        async def fake_sleep(delay):
            delays.append(delay)

        await run_with_retry(
            operation,
            initial_delay=3,
            max_delay=8,
            sleep=fake_sleep,
        )

        self.assertEqual(delays, [3, 6, 8, 8])

    async def test_does_not_retry_fatal_error(self):
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            raise FatalStartupError("invalid token")

        with self.assertRaises(FatalStartupError):
            await run_with_retry(
                operation,
                fatal_exceptions=(FatalStartupError,),
                sleep=lambda _: asyncio.sleep(0),
            )

        self.assertEqual(attempts, 1)

    async def test_propagates_cancellation(self):
        async def operation():
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await run_with_retry(operation)


if __name__ == "__main__":
    unittest.main()
