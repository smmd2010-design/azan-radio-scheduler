from __future__ import annotations

from .alexa import AlexaBackend
from .base import BackendResult, PlayerBackend, run_with_resilience
from .google_cast import GoogleCastBackend
from .homepod_airplay import HomePodAirPlayBackend
from .sony_tv import SonyTVBackend

REGISTRY: dict[str, PlayerBackend] = {
    "google_cast": GoogleCastBackend(),
    "homepod_airplay": HomePodAirPlayBackend(),
    "alexa": AlexaBackend(),
    "sony_tv": SonyTVBackend(),
}

BACKEND_LABELS = {
    "google_cast": "Google Home / Nest speaker",
    "homepod_airplay": "Apple HomePod",
    "alexa": "Amazon Alexa / Echo",
    "sony_tv": "Sony BRAVIA (Android TV)",
}


def get_backend(name: str) -> PlayerBackend:
    backend = REGISTRY.get(name)
    if backend is None:
        raise ValueError(f"Unknown backend '{name}'")
    return backend


__all__ = [
    "REGISTRY",
    "BACKEND_LABELS",
    "get_backend",
    "BackendResult",
    "PlayerBackend",
    "run_with_resilience",
]
