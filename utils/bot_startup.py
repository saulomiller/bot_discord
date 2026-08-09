"""Resilient startup helpers for the Discord client."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")


async def run_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    fatal_exceptions: tuple[type[BaseException], ...] = (),
    initial_delay: float = 5.0,
    max_delay: float = 300.0,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> T:
    """Run an async operation, retrying transient failures indefinitely."""
    if initial_delay <= 0:
        raise ValueError("initial_delay must be greater than zero")
    if max_delay < initial_delay:
        raise ValueError("max_delay must be greater than or equal to initial_delay")

    attempt = 0
    delay = initial_delay
    while True:
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except fatal_exceptions:
            raise
        except Exception as exc:
            attempt += 1
            logging.warning(
                "Falha temporaria ao conectar ao Discord (%s). "
                "Nova tentativa em %.0fs (tentativa %d).",
                exc,
                delay,
                attempt,
            )
            await sleep(delay)
            delay = min(delay * 2, max_delay)
