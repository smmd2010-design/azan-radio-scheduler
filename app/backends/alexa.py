"""
Amazon Alexa / Echo backend - via Home Assistant.

Amazon doesn't offer an official local API for "play this specific stream
on this Echo right now", and this project's first attempt at that (logging
into Amazon directly with the unofficial `alexapy` library) hit a real,
unresolvable wall for this account: Amazon's 2FA/security-check pages for
this specific login weren't recognized by any of alexapy's known
page-detection selectors, even though a normal browser login for the same
account works fine and only ever shows a standard verification-code prompt.

Rather than keep guessing at Amazon's HTML, this now talks to a Home
Assistant instance (already running on the same NAS) that has the
community-maintained "Alexa Media Player" HACS integration installed and
logged into the Amazon account. Home Assistant's own, more mature login UI
did the hard part; this module just calls Home Assistant's REST API to
tell the resulting `media_player` entities to "play this station" / "stop".

Two settings drive everything here (captured in the Devices page's Alexa
card, stored via db.set_settings):
  - ha_base_url: e.g. "http://192.168.1.106:8123" (no trailing slash)
  - ha_token: a Home Assistant "Long-Lived Access Token"
    (Home Assistant -> profile -> Security -> Long-Lived Access Tokens)

Each Alexa "device" configured in *this* app is really a Home Assistant
`media_player` entity_id (e.g. "media_player.kitchen_echo_dot") exposed by
the Alexa Media Player integration. Home Assistant's plain REST API (unlike
its websocket API) doesn't expose which integration owns an entity, so
discovery below identifies Alexa Media Player entities by two attribute
keys (`connected_bluetooth`, `bluetooth_list`) that integration always sets
and no other media_player integration is likely to use.

Playing a station reuses the same "voice-search-style" request the old
alexapy code sent: Alexa Media Player's `media_player.play_media` service,
called with `media_content_type: "TUNEIN"` and `media_content_id` set to
the station's search phrase (e.g. "Warna 94.2FM"), plays it exactly the way
saying "Alexa, play Warna 94.2FM on TuneIn" would.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from .. import db
from .base import BackendResult, PlayerBackend

logger = logging.getLogger("azan.backends.alexa")

HTTP_TIMEOUT = 10.0

# Attribute keys the Alexa Media Player integration always sets on its
# media_player entities (see its media_player.py extra_state_attributes) -
# used to tell its entities apart from any other media_player integration
# Home Assistant might have configured, since the REST API's /api/states
# doesn't say which integration owns an entity.
_ALEXA_MEDIA_MARKER_ATTRS = ("connected_bluetooth", "bluetooth_list")

MUSIC_PROVIDER_ID = "TUNEIN"

# How long to give the Echo to actually start playing before we check back
# in on it. media_player.play_media returning success only means Alexa
# *accepted* the request - see _start_async.
_CONFIRM_DELAY_SECONDS = 3.0

# States that mean audio is genuinely coming out of the speaker.
_PLAYING_STATES = {"playing", "buffering"}


class HomeAssistantNotConfigured(RuntimeError):
    pass


def _get_config() -> tuple[str, str]:
    base_url = (db.get_setting("ha_base_url") or "").strip().rstrip("/")
    token = (db.get_setting("ha_token") or "").strip()
    if not base_url or not token:
        raise HomeAssistantNotConfigured(
            "Home Assistant isn't connected yet - add its URL and access token in "
            "Settings/Devices first"
        )
    return base_url, token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def test_connection(base_url: str, token: str) -> tuple[bool, str]:
    """Used right after the user pastes a URL/token, before we save them."""
    base_url = base_url.strip().rstrip("/")
    token = token.strip()
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(f"{base_url}/api/", headers=_headers(token))
        if resp.status_code == 401:
            return False, "Home Assistant rejected that token - check it was copied in full"
        if resp.status_code >= 400:
            return False, f"Home Assistant returned an error (HTTP {resp.status_code})"
        return True, ""
    except httpx.HTTPError as exc:
        return False, f"Couldn't reach Home Assistant at that URL: {exc}"


async def list_available_devices() -> list[dict]:
    base_url, token = _get_config()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{base_url}/api/states", headers=_headers(token))
    resp.raise_for_status()
    devices = []
    for entity in resp.json():
        entity_id = entity.get("entity_id", "")
        if not entity_id.startswith("media_player."):
            continue
        attributes = entity.get("attributes") or {}
        if not any(key in attributes for key in _ALEXA_MEDIA_MARKER_ATTRS):
            continue
        devices.append(
            {
                "entity_id": entity_id,
                "name": attributes.get("friendly_name", entity_id),
            }
        )
    return devices


async def _call_service(domain: str, service: str, data: dict) -> None:
    base_url, token = _get_config()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(
            f"{base_url}/api/services/{domain}/{service}", headers=_headers(token), json=data
        )
    resp.raise_for_status()


async def _get_state(entity_id: str) -> tuple[str | None, float | None]:
    """Returns (state, volume_level) for one entity, or (None, None) on error."""
    base_url, token = _get_config()
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(f"{base_url}/api/states/{entity_id}", headers=_headers(token))
        resp.raise_for_status()
        entity = resp.json()
        return entity.get("state"), (entity.get("attributes") or {}).get("volume_level")
    except httpx.HTTPError as exc:
        logger.warning("Couldn't read back state for %s after starting it: %s", entity_id, exc)
        return None, None


async def _start_async(target: str, search_phrase: str) -> BackendResult:
    await _call_service(
        "media_player",
        "play_media",
        {
            "entity_id": target,
            "media_content_id": search_phrase,
            "media_content_type": MUSIC_PROVIDER_ID,
        },
    )
    # Production incidents, Isha 2026-09-09/10: this call reported a plain
    # success both nights (Alexa Media Player's play_media only confirms
    # Alexa *accepted* the request, never that anything audible happened),
    # but nothing was actually heard - once because the Echo's own volume
    # was left at 0%, once because Alexa silently dropped the stream on its
    # own about 30 seconds in. Home Assistant's reported state/volume are
    # the only signal available from here to catch either case, so check
    # back in shortly after asking it to play instead of trusting the
    # service call alone.
    await asyncio.sleep(_CONFIRM_DELAY_SECONDS)
    state, volume = await _get_state(target)
    if state is not None and state not in _PLAYING_STATES:
        return BackendResult(
            ok=False,
            message=(
                f"asked Alexa to play '{search_phrase}' but the device now reports "
                f"state '{state}' instead of playing"
            ),
        )
    if volume is not None and volume <= 0.01:
        # Not treated as a failure (retrying won't raise the volume, and the
        # request itself did succeed) - but surfaced clearly so a silent
        # azan shows up in the log instead of looking identical to a normal
        # success.
        return BackendResult(
            ok=True,
            message=(
                f"Asked Alexa (via Home Assistant) to play '{search_phrase}' - "
                f"WARNING: device volume is at 0%, azan will be silent"
            ),
        )
    return BackendResult(ok=True, message=f"Asked Alexa (via Home Assistant) to play '{search_phrase}'")


async def _stop_async(target: str) -> BackendResult:
    await _call_service("media_player", "media_stop", {"entity_id": target})
    return BackendResult(ok=True, message="Stopped Alexa playback (via Home Assistant)")


async def _health_async(target: str) -> BackendResult:
    base_url, token = _get_config()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{base_url}/api/states/{target}", headers=_headers(token))
    if resp.status_code == 404:
        return BackendResult(ok=False, message="Device entity not found in Home Assistant anymore")
    resp.raise_for_status()
    entity = resp.json()
    state = entity.get("state")
    if state in ("unavailable", "unknown"):
        return BackendResult(ok=False, message=f"Device reports '{state}' in Home Assistant")
    return BackendResult(ok=True, message="Online")


async def _verify_playing_async(target: str) -> BackendResult:
    """Used by the scheduler's mid-window recheck - see base.PlayerBackend.verify_playing."""
    state, volume = await _get_state(target)
    if state is None:
        return BackendResult(ok=False, message="couldn't read device state back from Home Assistant")
    if state not in _PLAYING_STATES:
        return BackendResult(ok=False, message=f"device reports state '{state}' instead of playing")
    if volume is not None and volume <= 0.01:
        return BackendResult(ok=False, message="device volume is at 0%")
    return BackendResult(ok=True, message="still playing")


class AlexaBackend(PlayerBackend):
    name = "alexa"

    async def start(
        self, target: str, stream_url: str, content_type: str, station_name: str
    ) -> BackendResult:
        # `stream_url`/`content_type` are unused for Alexa - Amazon doesn't
        # support casting an arbitrary stream URL, only voice-command-style
        # search+play. `station_name` (e.g. "Warna 94.2FM", configurable in
        # Settings) is what gets spoken into the TuneIn search.
        return await _start_async(target, station_name)

    async def stop(self, target: str) -> BackendResult:
        return await _stop_async(target)

    async def health(self, target: str) -> BackendResult:
        return await _health_async(target)

    async def verify_playing(self, target: str) -> BackendResult:
        return await _verify_playing_async(target)
