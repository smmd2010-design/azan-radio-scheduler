"""
Sony BRAVIA (Android TV with Google Cast built in) backend.

Audio delivery reuses the exact same Google Cast mechanism as
google_cast.py - casting to a Chromecast-enabled Android TV wakes it from
standby and switches input automatically, the same way it does for a Nest
Hub. What a TV needs on top of that (and a speaker doesn't) is to actually
be powered back OFF afterwards: quitting the Cast receiver app only
returns it to the Android TV home screen, it stays powered on indefinitely
otherwise. Casting itself has no "power off" concept - it's a media
protocol, not a device power API - so this talks to Sony's own local
"IP Control" REST API (https://pro-bravia.sony.net) for that one extra
step, using a Pre-Shared Key you set up once on the TV
(Settings -> Network & Internet -> Local network setup -> IP control).

Each device's PSK/IP are stored in the `devices.extra_config` JSON column
(see db.get_device_extra_config/set_device_extra_config), not the global
`settings` table, since this is per-TV, not a single shared account like
Home Assistant is for Alexa.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from .. import db
from .base import BackendResult, PlayerBackend
from .google_cast import _health_sync, _start_sync, _stop_sync, _verify_playing_sync

logger = logging.getLogger("azan.backends.sony_tv")

HTTP_TIMEOUT = 8.0


def _get_tv_config(target: str) -> tuple[str | None, str | None]:
    """Looks up this device's row by its Cast target name to read tv_ip/tv_psk."""
    for device in db.list_devices():
        if device["backend"] == "sony_tv" and device["target"] == target:
            cfg = db.get_device_extra_config(device)
            return cfg.get("tv_ip"), cfg.get("tv_psk")
    return None, None


async def _power_off(tv_ip: str, psk: str) -> BackendResult:
    url = f"http://{tv_ip}/sony/system"
    payload = {
        "method": "setPowerStatus",
        "id": 55,
        "params": [{"status": False}],
        "version": "1.0",
    }
    headers = {"Content-Type": "application/json", "X-Auth-PSK": psk}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 401:
            return BackendResult(
                ok=False,
                message=(
                    "TV rejected the Pre-Shared Key - check Settings > Network & "
                    "Internet > Local network setup > IP control"
                ),
            )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            return BackendResult(ok=False, message=f"TV rejected power-off: {body['error']}")
        return BackendResult(ok=True, message="Powered the TV off")
    except httpx.HTTPError as exc:
        return BackendResult(ok=False, message=f"Couldn't reach the TV's IP Control API: {exc}")


class SonyTVBackend(PlayerBackend):
    name = "sony_tv"

    async def start(self, target: str, stream_url: str, content_type: str, station_name: str) -> BackendResult:
        return await asyncio.to_thread(_start_sync, target, stream_url, content_type)

    async def stop(self, target: str) -> BackendResult:
        cast_result = await asyncio.to_thread(_stop_sync, target)

        tv_ip, psk = _get_tv_config(target)
        if not tv_ip or not psk:
            # Power control not set up yet for this TV - behaves exactly
            # like a plain Google Cast device (home screen only) until it is.
            return cast_result

        power_result = await _power_off(tv_ip, psk)
        if power_result.ok:
            return BackendResult(ok=cast_result.ok, message=f"{cast_result.message} | {power_result.message}")
        # Audio already stopped either way - a failed power-off is a
        # separate, lower-severity problem, logged but not turned into an
        # overall failure (which would trigger pointless stop-retries).
        logger.warning("TV power-off failed for %s: %s", target, power_result.message)
        return BackendResult(ok=cast_result.ok, message=f"{cast_result.message} | power-off failed: {power_result.message}")

    async def health(self, target: str) -> BackendResult:
        return await asyncio.to_thread(_health_sync, target)

    async def verify_playing(self, target: str) -> BackendResult:
        return await asyncio.to_thread(_verify_playing_sync, target)
