"""
Apple HomePod backend, using AirPlay via pyatv.

Known limitation (documented in the plan): pyatv's stream-to-HomePod
support is less mature than its Apple TV support (see upstream issues
postlund/pyatv#2812 and #2364). We isolate every call behind the shared
retry/timeout wrapper so a flaky HomePod session degrades to a logged
failure, never a crash - and the admin UI's per-device health check
surfaces this clearly so Sherif can fall back to the documented
HomeKit/Homebridge-automation route if AirPlay streaming proves unreliable
on his specific HomePod/OS version.

Pairing is a one-time step (AirPlay devices require it) done through the
admin UI's device setup wizard: begin_pairing() -> HomePod shows a PIN ->
finish_pairing(pin) -> credentials are saved to disk and reused forever
after (no PIN needed on subsequent starts/stops, including after a
container restart, as long as the credentials file volume persists).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pyatv
from pyatv.const import Protocol
from pyatv.storage.file_storage import FileStorage

from .base import BackendResult, PlayerBackend

logger = logging.getLogger("azan.backends.homepod_airplay")

CREDENTIALS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "airplay_credentials"


def _storage_path_for(target: str) -> str:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() else "_" for c in target)
    return str(CREDENTIALS_DIR / f"{safe_name}.json")


async def _find_config(target: str, storage: FileStorage):
    loop = asyncio.get_event_loop()
    configs = await pyatv.scan(loop, identifier=None, protocol=Protocol.AirPlay, storage=storage)
    for cfg in configs:
        if cfg.name.strip().lower() == target.strip().lower() or cfg.identifier == target:
            return cfg
    return None


async def begin_pairing(target: str):
    """
    Step 1 of the one-time pairing wizard. Returns the live PairingHandler
    so the web UI can hold onto it (in memory, keyed by a wizard session)
    while the user reads the PIN off the HomePod and submits it.
    """
    loop = asyncio.get_event_loop()
    storage = FileStorage(_storage_path_for(target), loop)
    await storage.load()
    config = await _find_config(target, storage)
    if config is None:
        raise RuntimeError(f"No AirPlay device named '{target}' found on the network")
    handler = await pyatv.pair(config, Protocol.AirPlay, loop, storage=storage)
    await handler.begin()
    return handler, storage


async def finish_pairing(handler, storage: FileStorage, pin: str) -> None:
    handler.pin(pin)
    await handler.finish()
    await storage.save()
    await handler.close()


async def _connect(target: str):
    loop = asyncio.get_event_loop()
    storage = FileStorage(_storage_path_for(target), loop)
    await storage.load()
    config = await _find_config(target, storage)
    if config is None:
        raise RuntimeError(f"No AirPlay device named '{target}' found on the network")
    atv = await pyatv.connect(config, loop, protocol=Protocol.AirPlay, storage=storage)
    return atv


async def _start_async(target: str, stream_url: str) -> BackendResult:
    atv = await _connect(target)
    try:
        await atv.stream.play_url(stream_url)
        return BackendResult(ok=True, message=f"Streaming to '{target}' via AirPlay")
    finally:
        atv.close()


async def _stop_async(target: str) -> BackendResult:
    atv = await _connect(target)
    try:
        await atv.remote_control.stop()
        return BackendResult(ok=True, message=f"Stopped '{target}'")
    finally:
        atv.close()


async def _health_async(target: str) -> BackendResult:
    loop = asyncio.get_event_loop()
    storage = FileStorage(_storage_path_for(target), loop)
    await storage.load()
    config = await _find_config(target, storage)
    if config is None:
        return BackendResult(ok=False, message=f"'{target}' not discoverable on the network")
    if not Path(_storage_path_for(target)).exists():
        return BackendResult(ok=False, message=f"'{target}' found but not paired yet")
    return BackendResult(ok=True, message=f"'{target}' is reachable and paired")


class HomePodAirPlayBackend(PlayerBackend):
    name = "homepod_airplay"

    async def start(
        self, target: str, stream_url: str, content_type: str, station_name: str
    ) -> BackendResult:
        return await _start_async(target, stream_url)

    async def stop(self, target: str) -> BackendResult:
        return await _stop_async(target)

    async def health(self, target: str) -> BackendResult:
        return await _health_async(target)


async def list_available_devices(timeout: float = 5.0) -> list[str]:
    """Used by the admin UI's device-setup page to show a pick-list."""
    loop = asyncio.get_event_loop()
    configs = await pyatv.scan(loop, timeout=timeout, protocol=Protocol.AirPlay)
    return sorted({cfg.name for cfg in configs})
