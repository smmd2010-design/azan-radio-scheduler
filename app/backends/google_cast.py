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
import time

import pychromecast

from .base import BackendResult, PlayerBackend

logger = logging.getLogger("azan.backends.google_cast")

# player_state values that mean "not actually playing" - used after a start
# to catch a receiver that silently failed to act on play_media() even
# though the command itself was accepted without raising.
_NOT_PLAYING_STATES = {"IDLE", "UNKNOWN", ""}


def _discover_and_connect(name: str, timeout: float = 10.0):
    """
    Find the named Chromecast and wait for its socket connection to come up,
    keeping the zeroconf discovery browser alive the whole time.

    This used to be two separate steps - discover-and-stop-browser, then
    `cast.wait()` afterwards in each caller - which tore down the zeroconf
    browser before the Chromecast object had actually finished connecting.
    That is what was causing every single start/stop to silently hang for
    the full 10s timeout and fail: pychromecast's connection setup for the
    returned Chromecast object depends on the browser still being alive,
    even though the *discovery* part (finding the device by name) had
    already succeeded. Plain TCP/ping connectivity to the device was never
    the problem - confirmed separately, both worked instantly.
    """
    chromecasts, browser = pychromecast.get_chromecasts(timeout=timeout)
    try:
        cast = next(
            (cc for cc in chromecasts if cc.name.strip().lower() == name.strip().lower()),
            None,
        )
        if cast is None:
            return None
        cast.wait(timeout=10)
        return cast
    finally:
        pychromecast.discovery.stop_discovery(browser)


def _start_sync(name: str, stream_url: str, content_type: str) -> BackendResult:
    cast = _discover_and_connect(name)
    if cast is None:
        return BackendResult(ok=False, message=f"No Chromecast device named '{name}' found on the network")
    mc = cast.media_controller
    mc.play_media(
        stream_url,
        content_type,
        title="Azan - Warna 94.2FM",
        stream_type="LIVE",
        autoplay=True,
    )
    mc.block_until_active(timeout=12)
    if mc.status.media_session_id is None:
        # Production incident, Isha 2026-09-05: play_media() was accepted
        # and the app logged a plain success, but the speaker never actually
        # played anything. block_until_active() only confirms the receiver
        # *acknowledged* a session - it does not confirm real playback - so
        # treat "no session ever showed up" as an explicit failure (which
        # run_with_resilience will retry) instead of a silent false success.
        return BackendResult(
            ok=False,
            message=f"'{name}' never reported an active playback session after being asked to play",
        )
    # Belt and braces: a session id can exist very briefly even when the
    # stream then fails to actually start playing (e.g. a transient fetch
    # error on the speaker's side). Give it a moment and check the reported
    # player state before trusting it.
    time.sleep(2)
    state = (mc.status.player_state or "").upper()
    if state in _NOT_PLAYING_STATES:
        return BackendResult(
            ok=False,
            message=f"'{name}' loaded the stream but reports state '{state or 'unknown'}' instead of playing",
        )
    return BackendResult(ok=True, message=f"Casting to '{name}'")


def _stop_sync(name: str) -> BackendResult:
    cast = _discover_and_connect(name)
    if cast is None:
        # Already off the network / already stopped - not an error for our purposes.
        return BackendResult(ok=True, message=f"'{name}' not found (assumed already stopped)")
    mc = cast.media_controller
    # pychromecast's stop() requires the media session id, which the media
    # channel only learns *after* connecting, via its own background
    # update_status() round-trip (triggered by channel_connected()). Calling
    # stop() immediately after _discover_and_connect() races that round-trip.
    #
    # This used to give up and assume "already stopped" whenever that
    # round-trip hadn't completed within the wait window - confirmed wrong in
    # production (2026-09-05, Zohr/Dhuhr: the speaker was still genuinely
    # playing and kept going for the rest of the window, because nothing was
    # ever actually sent to it, and it was logged as a normal success so
    # nothing alerted us). Now: wait a bit longer for the session id, and if
    # it still never shows up, fall back to quitting the running receiver
    # app outright - that reliably halts playback either way, unlike doing
    # nothing.
    mc.block_until_active(timeout=12)
    if mc.status.media_session_id is not None:
        mc.stop()
        # mc.stop() only halts the media session - on a device with a screen
        # (e.g. a Nest Hub) that leaves the receiver app's "now playing" UI
        # on screen (paused Warna 94.2FM tile) instead of returning to the
        # device's ambient/home screen. Reported by Sherif, Sept 2026: the
        # Google Nest Hub stayed on that screen after every azan. Quitting
        # the receiver app is what actually sends the display back to idle/
        # home - best-effort and never allowed to turn a successful stop
        # into a failure, since a speaker-only Cast target has no screen for
        # this to matter to anyway, and audio has already stopped either way.
        try:
            cast.quit_app()
        except Exception:  # noqa: BLE001 - best-effort only, audio already stopped
            logger.warning("'%s' stopped but quit_app() (for the home-screen reset) failed", name, exc_info=True)
            return BackendResult(ok=True, message=f"Stopped '{name}' (couldn't reset its screen to home)")
        return BackendResult(ok=True, message=f"Stopped '{name}' and returned it to its home screen")
    try:
        cast.quit_app()
    except Exception as exc:  # noqa: BLE001 - best-effort fallback, must never raise
        return BackendResult(
            ok=False,
            message=f"'{name}' had no confirmed session and quitting its app also failed: {exc}",
        )
    return BackendResult(
        ok=True, message=f"'{name}' had no confirmed session - quit its receiver app as a safety stop"
    )


def _health_sync(name: str) -> BackendResult:
    cast = _discover_and_connect(name, timeout=6.0)
    if cast is None:
        return BackendResult(ok=False, message=f"'{name}' not discoverable on the network")
    return BackendResult(ok=True, message=f"'{name}' is reachable")


def _verify_playing_sync(name: str) -> BackendResult:
    """Used by the scheduler's mid-window recheck - see base.PlayerBackend.verify_playing."""
    cast = _discover_and_connect(name, timeout=6.0)
    if cast is None:
        return BackendResult(ok=False, message=f"'{name}' not discoverable on the network")
    mc = cast.media_controller
    mc.block_until_active(timeout=8)
    state = (mc.status.player_state or "").upper()
    if state in _NOT_PLAYING_STATES:
        return BackendResult(
            ok=False, message=f"'{name}' reports state '{state or 'unknown'}' instead of playing"
        )
    return BackendResult(ok=True, message=f"'{name}' still playing")


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

    async def verify_playing(self, target: str) -> BackendResult:
        return await asyncio.to_thread(_verify_playing_sync, target)


def list_available_devices(timeout: float = 10.0) -> list[str]:
    """Used by the admin UI's device-setup page to show a pick-list."""
    chromecasts, browser = pychromecast.get_chromecasts(timeout=timeout)
    try:
        return sorted({cc.name for cc in chromecasts})
    finally:
        pychromecast.discovery.stop_discovery(browser)
