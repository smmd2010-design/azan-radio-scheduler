"""
Unified local-network device discovery for the Devices page's single
"Scan network" button.

Two of this app's three backends are genuinely discoverable on the LAN
using protocols already wired up elsewhere in the codebase:

- Cast (google_cast / sony_tv backends): any Chromecast-built-in device -
  Google/Nest speakers and Chromecast dongles, but also Android/Google TVs
  with Cast built in (e.g. Sherif's Sony BRAVIA) - all answer the same
  Cast discovery pychromecast already uses in google_cast.py. A device
  whose model/name looks like a Sony TV is flagged as a suggested "TV" add
  (backend=sony_tv) rather than a plain speaker, since that's the only way
  it gets the post-azan power-off behaviour by default instead of someone
  only noticing it's missing later.
- AirPlay (homepod_airplay backend): HomePods and AirPlay receivers,
  discovered via the same pyatv scan homepod_airplay.py uses. These still
  require a one-time PIN pairing before they can be added - that flow
  already exists in the "Add an Apple HomePod" card, so scan results just
  point there rather than duplicating pairing UI here.

Alexa devices are deliberately NOT part of this scan: they aren't found on
the local network at all - this app controls them through your Amazon
account via Home Assistant's Alexa Media Player integration (see
backends/alexa.py), so "scanning" for them is meaningless. The Devices
page already has its own Alexa-specific "Discover" (queries Home
Assistant, not the network) for that.

Like every backend call in this app, a failed protocol here never raises -
it just contributes zero results and gets logged, so one flaky protocol
can't break the scan for the other.
"""

from __future__ import annotations

import asyncio
import logging

import pyatv
import pychromecast
from pyatv.const import Protocol

logger = logging.getLogger("azan.discovery")

SCAN_TIMEOUT_SECONDS = 8.0

# Substrings (matched case-insensitively against the Cast device's model
# name and friendly name together) that mean "this is a TV, not a plain
# speaker/display" - kept loose and additive rather than exhaustive; worst
# case a TV gets suggested as a plain speaker and can still be re-added as
# backend=sony_tv manually, the way Sherif's first one was.
_TV_HINTS = ("sony", "bravia", "android tv", "google tv")


def _suggest_cast_backend(model_name: str, friendly_name: str) -> str:
    text = f"{model_name} {friendly_name}".lower()
    if any(hint in text for hint in _TV_HINTS):
        return "sony_tv"
    return "google_cast"


def _scan_cast_sync() -> list[dict]:
    try:
        chromecasts, browser = pychromecast.get_chromecasts(timeout=SCAN_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - discovery must never crash the page
        logger.exception("Cast discovery failed")
        return []
    try:
        results = []
        for cc in chromecasts:
            model = cc.model_name or ""
            results.append(
                {
                    "protocol": "cast",
                    "name": cc.name,
                    "model": model,
                    "suggested_backend": _suggest_cast_backend(model, cc.name or ""),
                }
            )
        return results
    finally:
        pychromecast.discovery.stop_discovery(browser)


async def _scan_airplay() -> list[dict]:
    try:
        loop = asyncio.get_event_loop()
        configs = await pyatv.scan(loop, timeout=SCAN_TIMEOUT_SECONDS, protocol=Protocol.AirPlay)
    except Exception:  # noqa: BLE001 - discovery must never crash the page
        logger.exception("AirPlay discovery failed")
        return []
    return [
        {"protocol": "airplay", "name": cfg.name, "model": "", "suggested_backend": "homepod_airplay"}
        for cfg in configs
    ]


async def scan_network() -> list[dict]:
    """
    Runs Cast + AirPlay discovery concurrently (each already has its own
    multi-second timeout, so doing them one after another would roughly
    double the wait for no reason). Returns a combined, name-deduplicated
    list, sorted for a stable UI - never raises.
    """
    cast_results, airplay_results = await asyncio.gather(
        asyncio.to_thread(_scan_cast_sync),
        _scan_airplay(),
    )
    combined = cast_results + airplay_results
    seen = set()
    deduped = []
    for d in combined:
        key = (d["protocol"], d["name"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)
    deduped.sort(key=lambda d: (d["protocol"], d["name"].lower()))
    return deduped
