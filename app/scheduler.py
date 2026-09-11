"""
The scheduling engine.

Deliberately NOT built on APScheduler + a persistent jobstore. That combo
is powerful but adds two extra dependencies (APScheduler, SQLAlchemy) and
a class of subtle bugs around misfire handling and jobstore locking that
are hard to reason about. Instead this is a small, fully-owned tick loop:
every few seconds it compares "now" against today's schedule (persisted in
our own `todays_schedule` table) and fires whatever needs firing. It is
simple enough to read top-to-bottom and trust.

Restart safety, by construction:
  - Today's schedule is recomputed (for not-yet-fired prayers only) on
    every process start and at each local midnight.
  - Each row remembers whether its start/stop already fired, so a restart
    mid-window resumes correctly instead of re-firing or losing state.
  - If the process was down through an entire prayer's window (missed it
    completely), that prayer is marked "skipped" rather than firing a
    surprise, late azan - see `_tick_once`.

Nothing in this module ever raises out of the loop: every exception is
caught, logged, and the loop just tries again next tick.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from . import db, prayer_times
from .backends import get_backend, run_with_resilience

logger = logging.getLogger("azan.scheduler")


# A short-early-start like "15 seconds before azan" needs the tick loop
# itself to check more often than that, or the requested lead time gets
# silently swallowed by the loop's own granularity (checking every 15s
# can only ever fire the moment "now" catches up, which can land anywhere
# from on-time to ~15s late relative to a 15s-early target). 5s keeps that
# slop small while still being a trivially cheap loop to run continuously.
TICK_SECONDS = 5
PRAYER_NAMES = ["fajr", "dhuhr", "asr", "maghrib", "isha"]

# Mid-window playback recheck (see _mid_window_recheck): how far into a
# device's own start->stop window to check back in on it, clamped so a
# short window still gets checked reasonably soon and a long one doesn't
# wait needlessly late.
_MID_WINDOW_MIN_DELAY_SECONDS = 25.0
_MID_WINDOW_MAX_DELAY_SECONDS = 90.0
_MID_WINDOW_FRACTION = 0.4

_last_scheduled_date: str | None = None
_last_fetch_attempt: dt.datetime | None = None
_last_skip_log_date: str | None = None
FETCH_RETRY_INTERVAL = dt.timedelta(minutes=10)


def get_tz() -> ZoneInfo:
    return ZoneInfo(db.get_setting("timezone", "Asia/Singapore"))


def _combine(date_str: str, hhmm: str, tz: ZoneInfo) -> dt.datetime:
    h, m = hhmm.split(":")
    d = dt.datetime.strptime(date_str, "%Y-%m-%d")
    return dt.datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=tz)


async def ensure_schedule_for_today(today_str: str, tz: ZoneInfo, *, force_refetch: bool) -> None:
    global _last_fetch_attempt, _last_skip_log_date

    times = None
    if force_refetch:
        now = dt.datetime.now(tz)
        if _last_fetch_attempt is None or now - _last_fetch_attempt > FETCH_RETRY_INTERVAL:
            _last_fetch_attempt = now
            times = await prayer_times.refresh_for_date(today_str)

    if times is None:
        times = prayer_times.get_cached_times_for(today_str)

    if times is None:
        logger.error("No prayer times available for %s (no live fetch, no cache)", today_str)
        db.log("ERROR", "scheduler", f"No prayer times available for {today_str} yet")
        return

    prayer_cfg = {row["prayer_name"]: row for row in db.get_prayer_settings()}
    default_duration = int(db.get_setting("duration_default_minutes", "7"))
    default_start_offset_seconds = int(db.get_setting("start_offset_default_seconds", "15"))

    # Log *why* a prayer is being left out of today's schedule - once per day,
    # not every tick - so a disabled prayer (or missing source data) shows up
    # plainly in the Logs page instead of just... never firing with nothing
    # to explain it.
    log_skips = _last_skip_log_date != today_str

    new_rows = []
    for name in PRAYER_NAMES:
        cfg = prayer_cfg.get(name)
        if cfg is None or not cfg["enabled"]:
            if log_skips:
                db.log("INFO", "scheduler", f"{name}: skipped today - disabled in Settings/Prayers")
            continue
        hhmm = times.get(name)
        if not hhmm:
            if log_skips:
                db.log(
                    "WARNING",
                    "scheduler",
                    f"{name}: skipped today - no time available from the prayer-time source",
                )
            continue
        duration = cfg["duration_minutes"] if cfg["duration_minutes"] else default_duration
        # start_offset_seconds may not exist as a key on older in-memory Row
        # objects mid-migration; .keys() check keeps this safe either way.
        # Compared with "is not None" (not plain truthiness) so an explicit
        # per-prayer override of 0 - "start exactly on time for just this
        # prayer" - is respected instead of silently falling back to the
        # global default.
        offset_override = cfg["start_offset_seconds"] if "start_offset_seconds" in cfg.keys() else None
        start_offset_seconds = offset_override if offset_override is not None else default_start_offset_seconds
        start_at = _combine(today_str, hhmm, tz) - dt.timedelta(seconds=start_offset_seconds)
        stop_at = start_at + dt.timedelta(minutes=duration)
        new_rows.append(
            {
                "prayer_name": name,
                "start_at": start_at.isoformat(),
                "stop_at": stop_at.isoformat(),
            }
        )

    db.replace_unfired_schedule_for_today(today_str, new_rows)
    if log_skips:
        _last_skip_log_date = today_str


async def _mid_window_recheck(
    today_str: str,
    prayer_name: str,
    device,
    stream_url: str,
    content_type: str,
    station_name: str,
    start_at: dt.datetime,
    stop_at: dt.datetime,
) -> None:
    """
    Catches a device that silently drops playback mid-window - confirmed to
    happen in production (Sherif's Echo Show 10, Isha 2026-09-10: dropped
    from playing to idle ~30s after a successful start, well before its
    ~5min stop time, and nothing caught it because the app never checked
    again until the scheduled stop fired and reported "already stopped").

    Runs once per device per prayer as a background task, so it never
    blocks the main tick loop or any other device's start/stop. Must never
    raise - it's launched with asyncio.create_task() and nothing awaits it.
    """
    try:
        backend = get_backend(device["backend"])
        window_seconds = (stop_at - start_at).total_seconds()
        delay = max(
            _MID_WINDOW_MIN_DELAY_SECONDS,
            min(_MID_WINDOW_MAX_DELAY_SECONDS, window_seconds * _MID_WINDOW_FRACTION),
        )
        await asyncio.sleep(delay)

        # If the window's stop has already fired (a short duration, or the
        # process fell behind), there's nothing useful left to check or
        # restart - the stop already told this device to be quiet.
        rows = db.get_todays_schedule(today_str)
        row = next((r for r in rows if r["prayer_name"] == prayer_name), None)
        if row is None or row["stop_fired"]:
            return

        try:
            result = await asyncio.wait_for(backend.verify_playing(device["target"]), timeout=15)
        except NotImplementedError:
            return  # this backend has no way to confirm playback state - nothing to check
        except Exception:  # noqa: BLE001 - a failed check must never crash the loop
            logger.exception(
                "Mid-window playback check raised for %s (%s)", device["label"], prayer_name
            )
            return

        if result.ok:
            return  # still playing - nothing to do

        db.log(
            "WARNING",
            f"backend.{device['backend']}",
            f"{device['label']}: dropped out mid-{prayer_name} ({result.message}) - restarting it",
        )
        restart = await run_with_resilience(
            lambda: backend.start(device["target"], stream_url, content_type, station_name),
            label=f"{device['backend']}:{device['label']} mid-window restart",
        )
        db.log(
            "INFO" if restart.ok else "ERROR",
            f"backend.{device['backend']}",
            f"{device['label']}: mid-{prayer_name} restart "
            f"{'succeeded' if restart.ok else 'failed'} - {restart.message}",
        )
    except Exception:  # noqa: BLE001 - background task, must never raise
        logger.exception("Mid-window recheck task crashed for %s (%s)", device.get("label"), prayer_name)


async def _fire_start(today_str: str, row) -> None:
    prayer_name = row["prayer_name"]
    stream_url = db.get_setting("stream_url", "")
    content_type = db.get_setting("stream_content_type", "audio/mpeg")
    station_name = db.get_setting("station_name", "Warna 94.2FM")
    devices = db.get_devices_for_prayer(prayer_name, enabled_only=True)

    if not devices:
        db.mark_fired(today_str, prayer_name, "start", "no devices assigned to this prayer")
        db.log("WARNING", "scheduler", f"{prayer_name}: start fired but no devices are assigned to it")
        return

    start_at = dt.datetime.fromisoformat(row["start_at"])
    stop_at = dt.datetime.fromisoformat(row["stop_at"])

    async def run_one(device):
        backend = get_backend(device["backend"])
        result = await run_with_resilience(
            lambda: backend.start(device["target"], stream_url, content_type, station_name),
            label=f"{device['backend']}:{device['label']} start",
        )
        level = "INFO" if result.ok else "ERROR"
        db.log(level, f"backend.{device['backend']}", f"{device['label']}: {result.message}")
        if result.ok:
            # Fire-and-forget: confirms this device is still actually
            # playing partway through the window, and restarts it once if
            # not. Never awaited here - must not delay the other devices'
            # start, or this prayer's "start fired" log line.
            asyncio.create_task(
                _mid_window_recheck(
                    today_str, prayer_name, device, stream_url, content_type, station_name, start_at, stop_at
                )
            )
        return f"{device['label']}: {'OK' if result.ok else 'FAILED'} - {result.message}"

    results = await asyncio.gather(*(run_one(d) for d in devices))
    db.mark_fired(today_str, prayer_name, "start", " | ".join(results))
    logger.info("%s start fired: %s", prayer_name, results)


async def _fire_stop(today_str: str, prayer_name: str) -> None:
    devices = db.get_devices_for_prayer(prayer_name, enabled_only=True)

    async def run_one(device):
        backend = get_backend(device["backend"])
        result = await run_with_resilience(
            lambda: backend.stop(device["target"]),
            label=f"{device['backend']}:{device['label']} stop",
        )
        level = "INFO" if result.ok else "ERROR"
        db.log(level, f"backend.{device['backend']}", f"{device['label']}: {result.message}")
        return f"{device['label']}: {'OK' if result.ok else 'FAILED'} - {result.message}"

    results = await asyncio.gather(*(run_one(d) for d in devices)) if devices else []
    db.mark_fired(today_str, prayer_name, "stop", " | ".join(results) if results else "no devices")
    logger.info("%s stop fired: %s", prayer_name, results)


async def _tick_once() -> None:
    global _last_scheduled_date

    tz = get_tz()
    now = dt.datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    is_new_day = _last_scheduled_date != today_str
    if is_new_day:
        await ensure_schedule_for_today(today_str, tz, force_refetch=True)
        _last_scheduled_date = today_str
    else:
        # Cheap: only actually re-fetches if nothing fresh in the retry window,
        # and only touches not-yet-fired rows.
        await ensure_schedule_for_today(today_str, tz, force_refetch=False)

    rows = db.get_todays_schedule(today_str)
    for row in rows:
        start_at = dt.datetime.fromisoformat(row["start_at"])
        stop_at = dt.datetime.fromisoformat(row["stop_at"])

        if not row["start_fired"] and now >= stop_at:
            # We were completely offline through this prayer's entire window.
            # Don't fire a surprise/late azan - just record it as skipped.
            db.mark_fired(today_str, row["prayer_name"], "start", "skipped (window passed while offline)")
            db.mark_fired(today_str, row["prayer_name"], "stop", "skipped (window passed while offline)")
            db.log("WARNING", "scheduler", f"{row['prayer_name']}: window passed while the app was offline, skipped")
            continue

        if not row["start_fired"] and now >= start_at:
            await _fire_start(today_str, row)
            continue

        if row["start_fired"] and not row["stop_fired"] and now >= stop_at:
            await _fire_stop(today_str, row["prayer_name"])


async def scheduler_loop() -> None:
    logger.info("Scheduler loop starting (tick every %ss)", TICK_SECONDS)
    while True:
        try:
            await _tick_once()
        except Exception:  # noqa: BLE001 - the loop must never die
            logger.exception("Scheduler tick raised an unexpected error - will retry next tick")
            db.log("ERROR", "scheduler", "Unexpected error in scheduler tick - see file log for traceback")
        await asyncio.sleep(TICK_SECONDS)


async def trigger_test(device_id: int, action: str) -> str:
    """Used by the admin UI's 'Test Now' button. action is 'start' or 'stop'."""
    devices = {d["id"]: d for d in db.list_devices()}
    device = devices.get(device_id)
    if device is None:
        return "Device not found"
    backend = get_backend(device["backend"])
    stream_url = db.get_setting("stream_url", "")
    content_type = db.get_setting("stream_content_type", "audio/mpeg")
    station_name = db.get_setting("station_name", "Warna 94.2FM")
    if action == "start":
        result = await run_with_resilience(
            lambda: backend.start(device["target"], stream_url, content_type, station_name),
            label=f"test-start {device['label']}",
        )
    else:
        result = await run_with_resilience(
            lambda: backend.stop(device["target"]), label=f"test-stop {device['label']}"
        )
    db.log("INFO" if result.ok else "ERROR", "test", f"{device['label']} {action}: {result.message}")
    return result.message
