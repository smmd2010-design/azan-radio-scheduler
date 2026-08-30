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
  1. start_login(email, password, otp_secret) -> attempts login
  2. if login.status contains "captcha_required", the UI shows the
     captcha image and calls continue_login(captcha=...)
  3. once logged in, cookies are saved to disk and reused on every
     subsequent start (including after a container restart)
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

from alexapy import AlexaAPI, AlexaLogin

from .base import BackendResult, PlayerBackend

logger = logging.getLogger("azan.backends.alexa")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "alexa"
COOKIE_FILE = DATA_DIR / "cookies.pickle"

# Amazon Alexa accounts registered in Singapore normally still authenticate
# against the amazon.com marketplace domain (there is no separate Alexa
# amazon.sg login). This is overridable in Settings for anyone reusing the
# project from a marketplace where that isn't true.
DEFAULT_LOGIN_URL = "amazon.com"

MUSIC_PROVIDER_ID = "TUNEIN"

_login_singleton: AlexaLogin | None = None


def _cookie_output_path(_email: str) -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(COOKIE_FILE)


async def get_login(url: str, email: str, password: str, otp_secret: str = "") -> AlexaLogin:
    global _login_singleton
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    login = AlexaLogin(
        url=url or DEFAULT_LOGIN_URL,
        email=email,
        password=password,
        outputpath=_cookie_output_path,
        otp_secret=otp_secret or "",
    )
    if COOKIE_FILE.exists():
        try:
            with open(COOKIE_FILE, "rb") as f:
                cookies = pickle.load(f)
            await login.login(cookies=cookies)
        except Exception:  # noqa: BLE001 - stale/corrupt cookie file, fall through to fresh login
            logger.warning("Saved Alexa cookies could not be reused, doing a fresh login")
            await login.login()
    else:
        await login.login()
    _login_singleton = login
    return login


async def continue_login(login: AlexaLogin, **data: str) -> None:
    await login.login(data=data)
    if login.status.get("login_successful"):
        _save_cookies(login)


def _save_cookies(login: AlexaLogin) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        cookies = login.session.cookies.get_dict() if login.session else {}
        with open(COOKIE_FILE, "wb") as f:
            pickle.dump(cookies, f)
    except Exception:
        logger.exception("Failed to persist Alexa session cookies")


async def get_cached_login() -> AlexaLogin | None:
    """Reuse the already-authenticated login object if one exists in this process."""
    global _login_singleton
    if _login_singleton is not None and _login_singleton.session:
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
