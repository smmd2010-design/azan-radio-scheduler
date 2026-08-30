"""
Prayer time source.

Two modes, selected by the `location_mode` setting:

- singapore_muis (default): pulls the official MUIS "Muslim Prayer
  Timetable" dataset published on data.gov.sg. This is the Singapore
  government's own copy of MUIS's numbers - the most authoritative source
  available for Singapore, and stable (published as a whole-year table).
- generic_aladhan: for anyone reusing this project outside Singapore.
  Uses the free Aladhan calculation API with a configurable
  latitude/longitude and calculation method.

Robustness contract: `get_prayer_times_for(date)` NEVER raises for network
reasons. If a live fetch fails, it falls back to whatever is cached in
SQLite (today's row if we have it, otherwise the most recent row we've
ever successfully fetched), and logs a warning. The one case it legitimately
returns None is "no data was ever fetched for this date and there is no
cache at all" - callers must handle that (skip scheduling for the day and
surface the error in the UI) rather than crash.
"""

from __future__ import annotations

import datetime as dt
import logging

import httpx

from . import db

logger = logging.getLogger("azan.prayer_times")

MUIS_RESOURCE_ID_SETTING = "muis_resource_id"
# Singapore government re-publishes this dataset yearly under a new
# resource id. We keep the current year's id as a sane built-in default,
# but it is fully overridable from Settings without a code change if/when
# data.gov.sg rotates it again in a following year.
DEFAULT_MUIS_RESOURCE_ID = "d_d441e7242e78efc566024dd5b0d9829c"

MUIS_API_URL = "https://data.gov.sg/api/action/datastore_search"

# The dataset's column names have varied historically between spellings;
# we match case-insensitively and try every alias we've seen.
COLUMN_ALIASES = {
    "date": ["date"],
    "fajr": ["subuh", "fajr"],
    "dhuhr": ["zohor", "zuhur", "dhuhr", "zuhr"],
    "asr": ["asar", "asr"],
    "maghrib": ["maghrib"],
    "isha": ["isyak", "isha", "ishak"],
}

PRAYER_NAMES = ["fajr", "dhuhr", "asr", "maghrib", "isha"]


def _find_field(row: dict, canonical: str) -> str | None:
    lowered = {k.lower().strip(): v for k, v in row.items()}
    for alias in COLUMN_ALIASES[canonical]:
        if alias in lowered:
            return lowered[alias]
    return None


async def _fetch_muis_for_date(date_str: str) -> dict[str, str] | None:
    resource_id = db.get_setting(MUIS_RESOURCE_ID_SETTING, DEFAULT_MUIS_RESOURCE_ID)
    params = {"resource_id": resource_id, "q": date_str, "limit": 5}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(MUIS_API_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()

    if not payload.get("success"):
        raise RuntimeError(f"data.gov.sg reported failure: {payload}")

    records = payload.get("result", {}).get("records", [])
    for rec in records:
        date_val = _find_field(rec, "date")
        if date_val and _normalize_date(date_val) == date_str:
            times = {name: _find_field(rec, name) for name in PRAYER_NAMES}
            if all(times.values()):
                return {k: _normalize_time(v) for k, v in times.items()}
    return None


def _normalize_date(value: str) -> str:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def _normalize_time(value: str) -> str:
    """Normalize to HH:MM (24h). Handles 'HH:MM', 'HH:MM:SS', 'H.MM am'."""
    value = value.strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I.%M%p", "%I:%M%p"):
        try:
            return dt.datetime.strptime(value, fmt).strftime("%H:%M")
        except ValueError:
            continue
    # Last resort: strip seconds if present (HH:MM:SS -> HH:MM)
    parts = value.split(":")
    if len(parts) >= 2:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    return value


async def _fetch_aladhan_for_date(date_str: str) -> dict[str, str] | None:
    lat = db.get_setting("aladhan_latitude", "1.3521")
    lon = db.get_setting("aladhan_longitude", "103.8198")
    method = db.get_setting("aladhan_method", "3")
    d = dt.datetime.strptime(date_str, "%Y-%m-%d")
    url = f"https://api.aladhan.com/v1/timings/{d.strftime('%d-%m-%Y')}"
    params = {"latitude": lat, "longitude": lon, "method": method}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    timings = payload.get("data", {}).get("timings")
    if not timings:
        return None
    return {
        "fajr": timings["Fajr"][:5],
        "dhuhr": timings["Dhuhr"][:5],
        "asr": timings["Asr"][:5],
        "maghrib": timings["Maghrib"][:5],
        "isha": timings["Isha"][:5],
    }


async def refresh_for_date(date_str: str) -> dict[str, str] | None:
    """
    Fetch fresh prayer times for `date_str` (YYYY-MM-DD) and cache them.
    Returns the times dict on success, None on failure (cache is left as-is
    on failure so callers can fall back to it).
    """
    mode = db.get_setting("location_mode", "singapore_muis")
    source = "muis" if mode == "singapore_muis" else "aladhan"
    try:
        if mode == "singapore_muis":
            times = await _fetch_muis_for_date(date_str)
        else:
            times = await _fetch_aladhan_for_date(date_str)
    except Exception as exc:  # noqa: BLE001 - network/parse errors are all "failure", never fatal
        logger.warning("Prayer time fetch failed for %s (%s): %s", date_str, mode, exc)
        db.log("WARNING", "prayer_times", f"Fetch failed for {date_str} via {mode}: {exc}")
        return None

    if times is None:
        logger.warning("Prayer time fetch returned no data for %s via %s", date_str, mode)
        db.log("WARNING", "prayer_times", f"No data returned for {date_str} via {mode}")
        return None

    db.upsert_prayer_cache_row(date_str, times, source)
    logger.info("Cached prayer times for %s via %s: %s", date_str, mode, times)
    return times


def get_cached_times_for(date_str: str) -> dict[str, str] | None:
    """Read-only lookup: today's cached row, else the most recent cached row (stale fallback)."""
    row = db.get_prayer_cache_row(date_str)
    if row is None:
        row = db.get_latest_cached_row()
        if row is not None:
            db.log(
                "WARNING",
                "prayer_times",
                f"Using stale prayer times from {row['date']} for {date_str} "
                f"(no fresher data available)",
            )
    if row is None:
        return None
    return {name: row[name] for name in PRAYER_NAMES}
