"""
Common interface every speaker backend implements, plus the shared
resilience wrapper (timeout + retry + never-raise) used by the scheduler.

This is the single most important file for the "solid build, not easy to
crash" requirement: the scheduler never calls a backend directly - it
always goes through `run_with_resilience`, so a bug or a flaky device in
one backend can never take down the process or block the other backends.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger("azan.backends")


@dataclass
class BackendResult:
    ok: bool
    message: str


class PlayerBackend:
    """Subclasses implement start/stop/health for one speaker ecosystem."""

    name: str = "base"

    async def start(
        self, target: str, stream_url: str, content_type: str, station_name: str
    ) -> BackendResult:
        """
        `stream_url`/`content_type` are used by backends that can cast an
        arbitrary URL (Google Cast, HomePod/AirPlay). `station_name` is
        used by backends that can only emulate a voice search-and-play
        command (Alexa has no "cast this URL" capability at all).
        Backends ignore whichever parameter doesn't apply to them.
        """
        raise NotImplementedError

    async def stop(self, target: str) -> BackendResult:
        raise NotImplementedError

    async def health(self, target: str) -> BackendResult:
        raise NotImplementedError


async def run_with_resilience(
    coro_factory,
    *,
    label: str,
    timeout: float = 30.0,
    retries: int = 2,
    backoff_seconds: float = 3.0,
) -> BackendResult:
    """
    Run an async backend call with a timeout and a couple of retries.
    Guaranteed to return a BackendResult and never raise - any exception
    (including a timeout) is converted into BackendResult(ok=False, ...).
    """
    last_error = "unknown error"
    for attempt in range(1, retries + 2):  # e.g. retries=2 -> 3 total attempts
        try:
            result = await asyncio.wait_for(coro_factory(), timeout=timeout)
            if isinstance(result, BackendResult):
                if result.ok:
                    return result
                last_error = result.message
            else:
                return BackendResult(ok=True, message=str(result))
        except asyncio.TimeoutError:
            last_error = f"timed out after {timeout}s"
        except Exception as exc:  # noqa: BLE001 - deliberately broad: never let a backend crash us
            last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("%s attempt %d/%d raised", label, attempt, retries + 1)

        if attempt <= retries:
            logger.warning(
                "%s attempt %d/%d failed (%s), retrying in %.1fs",
                label, attempt, retries + 1, last_error, backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)

    return BackendResult(ok=False, message=f"{label} failed after {retries + 1} attempts: {last_error}")
