from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import bcrypt
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import db, prayer_times, scheduler
from .backends import BACKEND_LABELS, get_backend
from .backends import google_cast as google_cast_mod
from .backends import homepod_airplay as homepod_mod
from .backends import alexa as alexa_mod
from .logging_setup import setup_logging

BASE_DIR = Path(__file__).resolve().parent
setup_logging()
logger = logging.getLogger("azan.main")

app = FastAPI(title="Azan Radio Scheduler")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

_session_secret_path = BASE_DIR.parent / "data" / "session_secret.txt"


def _get_or_create_session_secret() -> str:
    _session_secret_path.parent.mkdir(parents=True, exist_ok=True)
    if _session_secret_path.exists():
        return _session_secret_path.read_text().strip()
    import secrets

    secret = secrets.token_hex(32)
    _session_secret_path.write_text(secret)
    return secret


# In-memory state for the interactive pairing wizards. These are short-lived
# (a human is actively clicking through a setup flow) so process memory is
# fine - nothing here needs to survive a restart.
_pairing_sessions: dict[str, dict] = {}
_alexa_login_state: dict = {}

PRAYER_LABELS = {
    "fajr": "Fajr",
    "dhuhr": "Dhuhr",
    "asr": "Asr",
    "maghrib": "Maghrib",
    "isha": "Isha",
}


@app.on_event("startup")
async def on_startup() -> None:
    db.init_db()
    asyncio.create_task(scheduler.scheduler_loop())
    logger.info("Azan Radio Scheduler started")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# ---------- auth ----------

def _is_authed(request: Request) -> bool:
    return bool(request.session.get("authed"))


def _setup_needed() -> bool:
    return not db.get_setting("admin_password_hash")


MAX_PASSWORD_BYTES = 72  # inherent bcrypt limit


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


@app.middleware("http")
async def require_login(request: Request, call_next):
    open_paths = ("/login", "/setup", "/static", "/healthz")
    if request.url.path.startswith(open_paths):
        return await call_next(request)
    if _setup_needed():
        return RedirectResponse("/setup", status_code=303)
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


# Registered AFTER require_login is defined so that, in Starlette's stack,
# SessionMiddleware ends up OUTER than require_login (middleware added
# later wraps outer) - it must attach request.session before require_login
# tries to read it, or every request 500s with "SessionMiddleware must be
# installed". Order here is not cosmetic.
app.add_middleware(SessionMiddleware, secret_key=_get_or_create_session_secret())


@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    if not _setup_needed():
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "setup.html", {})


@app.post("/setup")
async def setup_post(request: Request, password: str = Form(...), confirm: str = Form(...)):
    if not _setup_needed():
        return RedirectResponse("/login", status_code=303)
    if password != confirm or len(password) < 8:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Passwords must match and be at least 8 characters"},
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return templates.TemplateResponse(
            request, "setup.html", {"error": "Password is too long (max 72 characters)"}
        )
    db.set_setting("admin_password_hash", hash_password(password))
    request.session["authed"] = True
    return RedirectResponse("/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if _setup_needed():
        return RedirectResponse("/setup", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login")
async def login_post(request: Request, password: str = Form(...)):
    stored_hash = db.get_setting("admin_password_hash", "")
    if stored_hash and verify_password(password, stored_hash):
        request.session["authed"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Wrong password"}
    )


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------- dashboard ----------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    tz = scheduler.get_tz()
    import datetime as dt

    today_str = dt.datetime.now(tz).strftime("%Y-%m-%d")
    times = prayer_times.get_cached_times_for(today_str) or {}
    schedule_rows = {r["prayer_name"]: r for r in db.get_todays_schedule(today_str)}
    devices = db.list_devices()

    prayer_rows = []
    for name in ["fajr", "dhuhr", "asr", "maghrib", "isha"]:
        sched = schedule_rows.get(name)
        prayer_rows.append(
            {
                "name": name,
                "label": PRAYER_LABELS[name],
                "time": times.get(name, "-"),
                "scheduled": sched is not None,
                "start_at": sched["start_at"] if sched else None,
                "stop_at": sched["stop_at"] if sched else None,
                "start_fired": bool(sched["start_fired"]) if sched else False,
                "stop_fired": bool(sched["stop_fired"]) if sched else False,
                "last_start_result": sched["last_start_result"] if sched else None,
                "last_stop_result": sched["last_stop_result"] if sched else None,
            }
        )

    recent_logs = db.get_recent_logs(50)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "today": today_str,
            "prayer_rows": prayer_rows,
            "devices": devices,
            "backend_labels": BACKEND_LABELS,
            "recent_logs": recent_logs,
        },
    )


# ---------- settings ----------

@app.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request):
    settings = db.get_all_settings()
    prayer_settings = db.get_prayer_settings()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": settings,
            "prayer_settings": prayer_settings,
            "prayer_labels": PRAYER_LABELS,
        },
    )


@app.post("/settings/general")
async def settings_general(
    request: Request,
    duration_default_minutes: int = Form(...),
    start_offset_default_minutes: int = Form(0),
    stream_url: str = Form(""),
    stream_content_type: str = Form("audio/mpeg"),
    station_name: str = Form("Warna 94.2FM"),
    timezone: str = Form("Asia/Singapore"),
    location_mode: str = Form("singapore_muis"),
    aladhan_latitude: str = Form("1.3521"),
    aladhan_longitude: str = Form("103.8198"),
    aladhan_method: str = Form("3"),
):
    db.set_settings(
        {
            "duration_default_minutes": str(duration_default_minutes),
            "start_offset_default_minutes": str(start_offset_default_minutes),
            "stream_url": stream_url.strip(),
            "stream_content_type": stream_content_type.strip() or "audio/mpeg",
            "station_name": station_name.strip() or "Warna 94.2FM",
            "timezone": timezone.strip() or "Asia/Singapore",
            "location_mode": location_mode,
            "aladhan_latitude": aladhan_latitude,
            "aladhan_longitude": aladhan_longitude,
            "aladhan_method": aladhan_method,
        }
    )
    db.log("INFO", "settings", "General settings updated")
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/prayers")
async def settings_prayers(request: Request):
    form = await request.form()
    for name in PRAYER_LABELS:
        enabled = form.get(f"enabled_{name}") == "on"
        duration_raw = form.get(f"duration_{name}", "").strip()
        duration = int(duration_raw) if duration_raw else None
        offset_raw = form.get(f"start_offset_{name}", "").strip()
        start_offset = int(offset_raw) if offset_raw else None
        db.set_prayer_setting(name, enabled, duration, start_offset)
    db.log("INFO", "settings", "Per-prayer settings updated")
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/password")
async def settings_password(
    request: Request, current_password: str = Form(...), new_password: str = Form(...)
):
    stored_hash = db.get_setting("admin_password_hash", "")
    if not verify_password(current_password, stored_hash):
        return RedirectResponse("/settings?error=wrongpass", status_code=303)
    if len(new_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return RedirectResponse("/settings?error=toolong", status_code=303)
    db.set_setting("admin_password_hash", hash_password(new_password))
    db.log("INFO", "settings", "Admin password changed")
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/refresh-prayer-times")
async def refresh_prayer_times_now(request: Request):
    import datetime as dt

    tz = scheduler.get_tz()
    today_str = dt.datetime.now(tz).strftime("%Y-%m-%d")
    result = await prayer_times.refresh_for_date(today_str)
    if result:
        db.log("INFO", "settings", "Manual prayer-time refresh succeeded")
    else:
        db.log("WARNING", "settings", "Manual prayer-time refresh failed, see logs")
    return RedirectResponse("/settings", status_code=303)


# ---------- devices ----------

@app.get("/devices", response_class=HTMLResponse)
async def devices_get(request: Request):
    devices = db.list_devices()
    return templates.TemplateResponse(
        request,
        "devices.html",
        {
            "devices": devices,
            "backend_labels": BACKEND_LABELS,
            "alexa_logged_in": (await alexa_mod.get_cached_login()) is not None,
        },
    )


@app.post("/devices/google/discover")
async def google_discover(request: Request):
    try:
        names = await asyncio.to_thread(google_cast_mod.list_available_devices)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})
    return JSONResponse({"ok": True, "devices": names})


@app.post("/devices/google/add")
async def google_add(request: Request, label: str = Form(...), target: str = Form(...)):
    db.add_device("google_cast", label, target)
    db.log("INFO", "devices", f"Added Google Cast device '{label}' ({target})")
    return RedirectResponse("/devices", status_code=303)


@app.post("/devices/homepod/discover")
async def homepod_discover(request: Request):
    try:
        names = await homepod_mod.list_available_devices()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})
    return JSONResponse({"ok": True, "devices": names})


@app.post("/devices/homepod/pair/begin")
async def homepod_pair_begin(request: Request, target: str = Form(...)):
    try:
        handler, storage = await homepod_mod.begin_pairing(target)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})
    _pairing_sessions[target] = {"handler": handler, "storage": storage}
    provides_pin = handler.device_provides_pin
    return JSONResponse({"ok": True, "device_provides_pin": provides_pin})


@app.post("/devices/homepod/pair/finish")
async def homepod_pair_finish(request: Request, target: str = Form(...), pin: str = Form(...)):
    session = _pairing_sessions.pop(target, None)
    if session is None:
        return JSONResponse({"ok": False, "error": "Pairing session expired, start again"})
    try:
        await homepod_mod.finish_pairing(session["handler"], session["storage"], pin)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})
    db.log("INFO", "devices", f"Paired with HomePod '{target}'")
    return JSONResponse({"ok": True})


@app.post("/devices/homepod/add")
async def homepod_add(request: Request, label: str = Form(...), target: str = Form(...)):
    db.add_device("homepod_airplay", label, target)
    db.log("INFO", "devices", f"Added HomePod device '{label}' ({target})")
    return RedirectResponse("/devices", status_code=303)


@app.post("/devices/alexa/login/start")
async def alexa_login_start(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    otp_secret: str = Form(""),
    login_url: str = Form("amazon.com"),
):
    try:
        login = await alexa_mod.get_login(login_url, email, password, otp_secret)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})
    status = login.status or {}
    if status.get("captcha_required"):
        _alexa_login_state["login"] = login
        return JSONResponse(
            {
                "ok": True,
                "needs_captcha": True,
                "captcha_image_url": status.get("captcha_image_url"),
            }
        )
    if status.get("login_successful") or login.session:
        db.log("INFO", "devices", "Logged into Alexa")
        return JSONResponse({"ok": True, "needs_captcha": False, "logged_in": True})
    return JSONResponse({"ok": False, "error": "Login did not complete - check credentials"})


@app.post("/devices/alexa/login/captcha")
async def alexa_login_captcha(request: Request, captcha: str = Form(...)):
    login = _alexa_login_state.get("login")
    if login is None:
        return JSONResponse({"ok": False, "error": "Login session expired, start again"})
    try:
        await alexa_mod.continue_login(login, captcha=captcha)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})
    if login.status.get("login_successful"):
        db.log("INFO", "devices", "Logged into Alexa (after captcha)")
        return JSONResponse({"ok": True, "logged_in": True})
    return JSONResponse({"ok": False, "error": "Still not logged in - captcha may be wrong"})


@app.post("/devices/alexa/discover")
async def alexa_discover(request: Request):
    login = await alexa_mod.get_cached_login()
    if login is None:
        return JSONResponse({"ok": False, "error": "Log into Alexa first"})
    try:
        devices = await alexa_mod.list_available_devices(login)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})
    simplified = [
        {"name": d.get("accountName"), "serial": d.get("serialNumber")} for d in devices
    ]
    return JSONResponse({"ok": True, "devices": simplified})


@app.post("/devices/alexa/add")
async def alexa_add(request: Request, label: str = Form(...), target: str = Form(...)):
    db.add_device("alexa", label, target)
    db.log("INFO", "devices", f"Added Alexa device '{label}' ({target})")
    return RedirectResponse("/devices", status_code=303)


@app.post("/devices/{device_id}/toggle")
async def device_toggle(request: Request, device_id: int, enabled: bool = Form(...)):
    db.set_device_enabled(device_id, enabled)
    return RedirectResponse("/devices", status_code=303)


@app.post("/devices/{device_id}/delete")
async def device_delete(request: Request, device_id: int):
    db.delete_device(device_id)
    return RedirectResponse("/devices", status_code=303)


@app.post("/devices/{device_id}/test")
async def device_test(request: Request, device_id: int, action: str = Form(...)):
    message = await scheduler.trigger_test(device_id, action)
    return JSONResponse({"ok": True, "message": message})


# ---------- logs ----------

@app.get("/logs", response_class=HTMLResponse)
async def logs_get(request: Request):
    logs = db.get_recent_logs(500)
    return templates.TemplateResponse(request, "logs.html", {"logs": logs})
