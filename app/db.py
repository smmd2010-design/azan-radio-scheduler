"""
Single-file SQLite storage layer.

Design goal: this whole app must survive being restarted, killed mid-write,
or having its container recreated, without corrupting state or losing
today's remaining prayer schedule. SQLite in WAL mode gives us crash-safe
durability with zero moving parts (no separate DB server to fail).

Every function here opens its own short-lived connection - we never hold a
connection open across an await point, which avoids the classic
"sqlite3 objects created in one thread can only be used in that thread"
and long-lock-contention problems under asyncio + a background scheduler
thread running concurrently.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

# One process-wide lock. SQLite handles its own locking fine, but under
# heavy concurrent writes from asyncio tasks + the scheduler thread we've
# seen "database is locked" errors without this. The lock is cheap and
# writes here are infrequent (a handful of times a minute at most).
_WRITE_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS prayer_settings (
    prayer_name TEXT PRIMARY KEY,   -- fajr, dhuhr, asr, maghrib, isha
    enabled INTEGER NOT NULL DEFAULT 1,
    duration_minutes INTEGER,       -- NULL = use global default
    start_offset_minutes INTEGER    -- NULL = use global default; minutes to start BEFORE the prayer time
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend TEXT NOT NULL,          -- google_cast | homepod_airplay | alexa
    label TEXT NOT NULL,            -- friendly name shown in UI
    target TEXT NOT NULL,           -- backend-specific identifier (cast device name, AirPlay identifier, Alexa device serial)
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_prayers (
    device_id INTEGER NOT NULL,
    prayer_name TEXT NOT NULL,      -- fajr, dhuhr, asr, maghrib, isha
    PRIMARY KEY (device_id, prayer_name),
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS prayer_cache (
    date TEXT PRIMARY KEY,          -- YYYY-MM-DD
    fajr TEXT, dhuhr TEXT, asr TEXT, maghrib TEXT, isha TEXT,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS todays_schedule (
    date TEXT NOT NULL,
    prayer_name TEXT NOT NULL,
    start_at TEXT NOT NULL,         -- ISO8601 datetime, local tz
    stop_at TEXT NOT NULL,
    start_fired INTEGER NOT NULL DEFAULT 0,
    stop_fired INTEGER NOT NULL DEFAULT 0,
    last_start_result TEXT,
    last_stop_result TEXT,
    PRIMARY KEY (date, prayer_name)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    component TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_log_ts ON activity_log(ts DESC);
"""

DEFAULT_PRAYERS = ["fajr", "dhuhr", "asr", "maghrib", "isha"]

DEFAULT_SETTINGS = {
    "admin_password_hash": "",  # set on first run
    "duration_default_minutes": "7",
    "start_offset_default_seconds": "15",  # seconds to start BEFORE the prayer time, 0 = start exactly at prayer time
    # StreamTheWorld is the actual CDN Mediacorp/RTM stations are hosted
    # on; this URL pattern was found via a third-party station directory
    # and NOT verified end-to-end from this build environment (which has
    # no route to the public internet) - test it with the "Test Now"
    # button after deployment, and change it here if it's ever wrong or
    # moves. See README "Verifying the stream URL".
    "stream_url": "https://playerservices.streamtheworld.com/api/livestream-redirect/WARNA942FMAAC_SC",
    "stream_content_type": "audio/aac",
    "station_name": "Warna 94.2FM",  # used for Alexa's voice-search-style playback
    "location_mode": "singapore_muis",  # or generic_aladhan
    "timezone": "Asia/Singapore",
    "aladhan_latitude": "1.3521",
    "aladhan_longitude": "103.8198",
    "aladhan_method": "3",  # Muslim World League, used only in generic mode
    "setup_complete": "0",
    # Alexa is controlled through Home Assistant (its Alexa Media Player
    # HACS integration), not a direct Amazon login - see app/backends/alexa.py.
    "ha_base_url": "",
    "ha_token": "",
}


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _WRITE_LOCK, _connect() as conn:
        conn.executescript(SCHEMA)
        # Migration for DBs created before start_offset_minutes existed.
        # CREATE TABLE IF NOT EXISTS above only affects brand-new databases,
        # so an already-deployed app.db needs this column added explicitly.
        # Safe to run every startup: fails harmlessly once the column exists.
        try:
            conn.execute("ALTER TABLE prayer_settings ADD COLUMN start_offset_minutes INTEGER")
        except sqlite3.OperationalError:
            pass  # already migrated
        # Start-early support used to only go down to whole minutes; now
        # seconds-based so e.g. "15 seconds before azan" is possible. Old
        # minute values (almost certainly still the untouched default of 0)
        # aren't meaningfully worth converting, so this is a fresh column
        # rather than a straight *60 conversion of the old one.
        try:
            conn.execute("ALTER TABLE prayer_settings ADD COLUMN start_offset_seconds INTEGER")
        except sqlite3.OperationalError:
            pass  # already migrated
        for name in DEFAULT_PRAYERS:
            conn.execute(
                "INSERT OR IGNORE INTO prayer_settings (prayer_name, enabled, duration_minutes) "
                "VALUES (?, 1, NULL)",
                (name,),
            )
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
        # Migration for devices added before per-prayer assignment existed
        # (device_prayers is a brand-new table): a device with zero rows
        # there must keep behaving exactly as it always did - play on every
        # prayer - rather than silently going quiet on all of them the
        # moment this version starts up.
        device_ids = [r["id"] for r in conn.execute("SELECT id FROM devices").fetchall()]
        already_assigned = {
            r["device_id"]
            for r in conn.execute("SELECT DISTINCT device_id FROM device_prayers").fetchall()
        }
        for device_id in device_ids:
            if device_id not in already_assigned:
                conn.executemany(
                    "INSERT OR IGNORE INTO device_prayers (device_id, prayer_name) VALUES (?, ?)",
                    [(device_id, name) for name in DEFAULT_PRAYERS],
                )


def get_setting(key: str, default: str | None = None) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default


def get_all_settings() -> dict[str, str]:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def set_setting(key: str, value: str) -> None:
    with _WRITE_LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def set_settings(pairs: dict[str, str]) -> None:
    with _WRITE_LOCK, _connect() as conn:
        for key, value in pairs.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def get_prayer_settings() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM prayer_settings ORDER BY "
            "CASE prayer_name WHEN 'fajr' THEN 1 WHEN 'dhuhr' THEN 2 WHEN 'asr' THEN 3 "
            "WHEN 'maghrib' THEN 4 WHEN 'isha' THEN 5 ELSE 6 END"
        ).fetchall()


def set_prayer_setting(
    prayer_name: str,
    enabled: bool,
    duration_minutes: int | None,
    start_offset_seconds: int | None = None,
) -> None:
    with _WRITE_LOCK, _connect() as conn:
        conn.execute(
            "UPDATE prayer_settings SET enabled = ?, duration_minutes = ?, start_offset_seconds = ? "
            "WHERE prayer_name = ?",
            (1 if enabled else 0, duration_minutes, start_offset_seconds, prayer_name),
        )


def list_devices(enabled_only: bool = False) -> list[sqlite3.Row]:
    with _connect() as conn:
        q = "SELECT * FROM devices"
        if enabled_only:
            q += " WHERE enabled = 1"
        q += " ORDER BY backend, label"
        return conn.execute(q).fetchall()


def add_device(backend: str, label: str, target: str) -> int:
    with _WRITE_LOCK, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO devices (backend, label, target, enabled, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (backend, label, target, _now_iso()),
        )
        device_id = cur.lastrowid
        # Default a newly-added device to playing every prayer - matches
        # the app's historical behaviour and is the least surprising
        # starting point; per-prayer assignment can be narrowed afterwards
        # from the Devices page.
        conn.executemany(
            "INSERT OR IGNORE INTO device_prayers (device_id, prayer_name) VALUES (?, ?)",
            [(device_id, name) for name in DEFAULT_PRAYERS],
        )
        return device_id


def set_device_enabled(device_id: int, enabled: bool) -> None:
    with _WRITE_LOCK, _connect() as conn:
        conn.execute(
            "UPDATE devices SET enabled = ? WHERE id = ?", (1 if enabled else 0, device_id)
        )


def delete_device(device_id: int) -> None:
    with _WRITE_LOCK, _connect() as conn:
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))


def get_device_prayers(device_id: int) -> set[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT prayer_name FROM device_prayers WHERE device_id = ?", (device_id,)
        ).fetchall()
        return {r["prayer_name"] for r in rows}


def get_all_device_prayers() -> dict[int, set[str]]:
    """Every device's prayer assignment in one query - used by the Devices page."""
    with _connect() as conn:
        rows = conn.execute("SELECT device_id, prayer_name FROM device_prayers").fetchall()
    result: dict[int, set[str]] = {}
    for r in rows:
        result.setdefault(r["device_id"], set()).add(r["prayer_name"])
    return result


def set_device_prayers(device_id: int, prayer_names: list[str]) -> None:
    """Replace which prayers this device plays for. An empty list means never."""
    with _WRITE_LOCK, _connect() as conn:
        conn.execute("DELETE FROM device_prayers WHERE device_id = ?", (device_id,))
        conn.executemany(
            "INSERT INTO device_prayers (device_id, prayer_name) VALUES (?, ?)",
            [(device_id, name) for name in prayer_names if name in DEFAULT_PRAYERS],
        )


def get_devices_for_prayer(prayer_name: str, enabled_only: bool = False) -> list[sqlite3.Row]:
    with _connect() as conn:
        q = (
            "SELECT devices.* FROM devices "
            "JOIN device_prayers ON device_prayers.device_id = devices.id "
            "WHERE device_prayers.prayer_name = ?"
        )
        params: list = [prayer_name]
        if enabled_only:
            q += " AND devices.enabled = 1"
        q += " ORDER BY devices.backend, devices.label"
        return conn.execute(q, params).fetchall()


def upsert_prayer_cache_row(date: str, times: dict[str, str], source: str) -> None:
    with _WRITE_LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO prayer_cache (date, fajr, dhuhr, asr, maghrib, isha, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET fajr=excluded.fajr, dhuhr=excluded.dhuhr, "
            "asr=excluded.asr, maghrib=excluded.maghrib, isha=excluded.isha, "
            "source=excluded.source, fetched_at=excluded.fetched_at",
            (
                date,
                times.get("fajr"),
                times.get("dhuhr"),
                times.get("asr"),
                times.get("maghrib"),
                times.get("isha"),
                source,
                _now_iso(),
            ),
        )


def get_prayer_cache_row(date: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM prayer_cache WHERE date = ?", (date,)).fetchone()


def get_latest_cached_row() -> sqlite3.Row | None:
    """Fallback used only if we cannot fetch *and* have no row for today at all."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM prayer_cache ORDER BY date DESC LIMIT 1"
        ).fetchone()


def replace_unfired_schedule_for_today(date: str, new_rows: list[dict]) -> None:
    """
    (re)write today's schedule, but NEVER touch a row whose start already
    fired - re-running this (e.g. because the admin changed a duration, or
    the midnight refresh re-ran) must not un-do or re-trigger something
    that already happened today.
    """
    new_by_prayer = {r["prayer_name"]: r for r in new_rows}
    with _WRITE_LOCK, _connect() as conn:
        existing = {
            r["prayer_name"]: r
            for r in conn.execute(
                "SELECT * FROM todays_schedule WHERE date = ?", (date,)
            ).fetchall()
        }
        for prayer_name, r in new_by_prayer.items():
            already_fired = prayer_name in existing and existing[prayer_name]["start_fired"]
            if already_fired:
                continue
            conn.execute(
                "INSERT INTO todays_schedule (date, prayer_name, start_at, stop_at, "
                "start_fired, stop_fired) VALUES (?, ?, ?, ?, 0, 0) "
                "ON CONFLICT(date, prayer_name) DO UPDATE SET "
                "start_at = excluded.start_at, stop_at = excluded.stop_at "
                "WHERE todays_schedule.start_fired = 0",
                (date, prayer_name, r["start_at"], r["stop_at"]),
            )
        # Drop rows for prayers that are no longer enabled, as long as they haven't fired.
        for prayer_name, row in existing.items():
            if prayer_name not in new_by_prayer and not row["start_fired"]:
                conn.execute(
                    "DELETE FROM todays_schedule WHERE date = ? AND prayer_name = ?",
                    (date, prayer_name),
                )


def get_todays_schedule(date: str) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM todays_schedule WHERE date = ? ORDER BY start_at", (date,)
        ).fetchall()


def mark_fired(date: str, prayer_name: str, which: str, result: str) -> None:
    assert which in ("start", "stop")
    with _WRITE_LOCK, _connect() as conn:
        conn.execute(
            f"UPDATE todays_schedule SET {which}_fired = 1, last_{which}_result = ? "
            f"WHERE date = ? AND prayer_name = ?",
            (result, date, prayer_name),
        )


def log(level: str, component: str, message: str) -> None:
    with _WRITE_LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO activity_log (ts, level, component, message) VALUES (?, ?, ?, ?)",
            (_now_iso(), level, component, message),
        )
        # Keep the table bounded - this is a UI convenience log, not the
        # audit trail (the rotating file log is, see logging_setup.py).
        conn.execute(
            "DELETE FROM activity_log WHERE id NOT IN "
            "(SELECT id FROM activity_log ORDER BY id DESC LIMIT 2000)"
        )


def get_recent_logs(limit: int = 200) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
