"""
Google Home / Nest speaker backend, using the official Cast protocol via
pychromecast. This is the most reliable of the three backends: no account
login, no unofficial API, just local-network discovery + the same Cast
protocol the Google Home app itself uses.

`target` is the Chromecast device's friendly name as configured in the
Google Home app (e.g. "Kitchen speaker"). Discovery is by name because
DHCP-assigned IPs are unstable; discovery is fast (~a few seconds) on a
typical home LAN.
"""

from __future__ import annotations

import asyncio
import logging

import pychromecast

from .base import BackendResult, PlayerBackend

logger = logging.getLogger("azan.backends.google_cast")


def _discover_by_name(name: str, timeout: float = 10.0):
    chromecasts, browser = pychromecast.get_chromecasts(timeout=timeout)
    try:
        for cc in chromecasts:
            if cc.name.strip().lower() == name.strip().lower():
                return cc
        return None
    finally:
        pychromecast.discovery.stop_discovery(browser)


def _start_sync(name: str, stream_url: str, content_type: str) -> BackendResult:
    cast = _discover_by_name(name)
    if cast is None:
        return BackendResult(ok=False, message=f"No Chromecast device named '{name}' found on the network")
    cast.wait(timeout=10)
    mc = cast.media_controller
    mc.play_media(
        stream_url,
        content_type,
        title="Azan - Warna 94.2FM",
        stream_type="LIVE",
        autoplay=True,
    )
    mc.block_until_active(timeout=10)
    return BackendResult(ok=True, message=f"Casting to '{name}'")


def _stop_sync(name: str) -> BackendResult:
    cast = _discover_by_name(name)
    if cast is None:
        # Already off the network / already stopped - not an error for our purposes.
        return BackendResult(ok=True, message=f"'{name}' not found (assumed already stopped)")
    cast.wait(timeout=10)
    cast.media_controller.stop()
    return BackendResult(ok=True, message=f"Stopped '{name}'")


def _health_sync(name: str) -> BackendResult:
    cast = _discover_by_name(name, timeout=6.0)
    if cast is None:
        return BackendResult(ok=False, message=f"'{name}' not discoverable on the network")
    return BackendResult(ok=True, message=f"'{name}' is reachable")


class GoogleCastBackend(PlayerBackend):
    name = "google_cast"

    async def start(
        self, target: str, stream_url: str, content_type: str, station_name: str
    ) -> BackendResult:
        return await asyncio.to_thread(_start_sync, target, stream_url, content_type)

    async def stop(self, target: str) -> BackendResult:
        return await asyncio.to_thread(_stop_sync, target)

    async def health(self, target: str) -> BackendResult:
        return await asyncio.to_thread(_health_sync, target)


def list_available_devices(timeout: float = 10.0) -> list[str]:
    """Used by the admin UI's device-setup page to show a pick-list."""
    chromecasts, browser = pychromecast.get_chromecasts(timeout=timeout)
    try:
        return sorted({cc.name for cc in chromecasts})
    finally:
        pychromecast.discovery.stop_discovery(browser)
