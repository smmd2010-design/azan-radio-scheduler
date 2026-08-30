"""
Amazon Alexa / Echo backend.

This is the least solid of the three legs, by design constraint rather than
implementation choice: Amazon does not offer an official local API for
"play this specific stream on this Echo right now". We use `alexapy` (the
same unofficial library Home Assistant's Alexa Media Player integration is
built on) which logs into your Amazon account and emulates the voice
command "Alexa, play <search phrase> on TuneIn" via `send_sequence`.

Because it's a real account login, it can require re-authentication if
Amazon's login flow changes, shows a CAPTCHA, or the session cookie
expires - the admin UI's Alexa page surfaces "needs re-login" clearly
rather than failing silently, and (this is the important part) a failure
here is fully isolated: it never blocks or crashes the Google Cast or
HomePod backends, or the scheduler loop itself.

Login is a small multi-step wizard because Amazon may show a CAPTCHA or
ask for a 2FA/OTP code:
  1. get_login(email, password, otp_secret) -> attempts login (reusing a
     saved session if one exists)
  2. if login.status contains "captcha_required", the UI shows the
     captcha image and calls continue_login(captcha=...)
  3. once logged in, alexapy persists its own session cookies to disk
     (via save_cookiefile(), see `_outputpath` below) and reuses them on
     every subsequent start, including after a container restart.

Cookie persistence deliberately uses alexapy's OWN load_cookie()/
save_cookiefile() methods rather than a custom pickle file: alexapy writes
a specific versioned JSON structure (and migrates older formats) that only
its own loader round-trips correctly. `outputpath` is the hook alexapy
uses to turn its internal relative filenames (e.g.
".storage/amazon.com.<email>.cookies") into real paths on disk - it must
map every such name under our persistent data volume.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alexapy import AlexaAPI, AlexaLogin

from .base import BackendResult, PlayerBackend

logger = logging.getLogger("azan.backends.alexa")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "alexa"

# Amazon Alexa accounts registered in Singapore normally still authenticate
# against the amazon.com marketplace domain (there is no separate Alexa
# amazon.sg login). This is overridable in Settings for anyone reusing the
# project from a marketplace where that isn't true.
DEFAULT_LOGIN_URL = "amazon.com"

MUSIC_PROVIDER_ID = "TUNEIN"

_login_singleton: AlexaLogin | None = None


def _outputpath(relative_path: str) -> str:
    full = DATA_DIR / relative_path
    full.parent.mkdir(parents=True, exist_ok=True)
    return str(full)


async def get_login(url: str, email: str, password: str, otp_secret: str = "") -> AlexaLogin:
    global _login_singleton
    login = AlexaLogin(
        url=url or DEFAULT_LOGIN_URL,
        email=email,
        password=password,
        outputpath=_outputpath,
        otp_secret=otp_secret or "",
    )
    cookies = await login.load_cookie()
    if cookies:
        await login.login(cookies=cookies)
        if not login.status.get("login_successful"):
            logger.warning("Saved Alexa session was rejected, doing a fresh login")
            await login.login()
    else:
        await login.login()
    if login.status.get("login_successful"):
        await login.save_cookiefile()
    _login_singleton = login
    return login


async def continue_login(login: AlexaLogin, **data: str) -> None:
    await login.login(data=data)
    if login.status.get("login_successful"):
        await login.save_cookiefile()


async def get_cached_login() -> AlexaLogin | None:
    """Reuse the already-authenticated login object if one exists in this process.

    Checking `.session` here used to be enough to make the UI *and* every
    caller below believe login had succeeded, but a session object exists
    the moment any login attempt starts - success or failure. Requiring the
    login library's own "login_successful" flag is what actually reflects
    whether the account is authenticated.
    """
    global _login_singleton
    if (
        _login_singleton is not None
        and _login_singleton.session
        and (_login_singleton.status or {}).get("login_successful")
    ):
        return _login_singleton
    return None


async def list_available_devices(login: AlexaLogin) -> list[dict]:
    devices = await AlexaAPI.get_devices(login)
    return devices or []


async def _get_api_for(target_serial: str) -> AlexaAPI:
    login = await get_cached_login()
    if login is None:
        raise RuntimeError("Not logged into Alexa - complete the login wizard in Settings first")
    devices = await AlexaAPI.get_devices(login)
    device = next((d for d in (devices or []) if d.get("serialNumber") == target_serial), None)
    if device is None:
        raise RuntimeError(f"Alexa device with serial '{target_serial}' not found on this account")
    return AlexaAPI(device, login)


async def _start_async(target: str, search_phrase: str) -> BackendResult:
    api = await _get_api_for(target)
    await api.play_music(MUSIC_PROVIDER_ID, search_phrase)
    return BackendResult(ok=True, message=f"Asked Alexa device to play '{search_phrase}' via TuneIn")


async def _stop_async(target: str) -> BackendResult:
    api = await _get_api_for(target)
    await api.stop()
    return BackendResult(ok=True, message="Stopped Alexa playback")


async def _health_async(target: str) -> BackendResult:
    login = await get_cached_login()
    if login is None:
        return BackendResult(ok=False, message="Not logged into Alexa - needs re-login")
    devices = await AlexaAPI.get_devices(login)
    device = next((d for d in (devices or []) if d.get("serialNumber") == target), None)
    if device is None:
        return BackendResult(ok=False, message="Device not found on this account")
    online = device.get("online", True)
    return BackendResult(ok=bool(online), message="Online" if online else "Device reports offline")


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
