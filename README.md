# Azan Radio Scheduler

Automatically plays a radio station on your smart speakers at each Islamic
prayer time, for a configurable duration, then stops it — no daily manual
work. Built for Sherif's Synology NAS (playing Warna 94.2FM in Singapore),
but nothing about it is hardcoded to that setup: it's meant to be handed to
anyone else to self-host on their own NAS, anywhere.

## How it works

Every 15 seconds a small scheduler loop checks the current time against
today's prayer schedule. When a prayer time arrives, it tells every enabled
speaker to start playing; after the configured duration, it tells them to
stop. Prayer times are refreshed daily from an official source (see below)
and cached locally, so a bad internet day never causes a silent outage.

It talks to three completely different smart-speaker ecosystems, each
through its own isolated backend module — a failure in one (say, an
expired Alexa login) can never block or crash the other two, or the
scheduler itself:

| Ecosystem | How it's controlled | Robustness |
|---|---|---|
| Google Home / Nest | Official Cast protocol (`pychromecast`) — casts the stream URL directly | Most reliable — no account login needed |
| Apple HomePod | AirPlay (`pyatv`) — one-time pairing, then streams the URL | Solid, but Apple's own AirPlay stack for HomePod streaming is less mature than for Apple TV; a HomeKit/Homebridge-automation fallback is documented below if needed |
| Amazon Alexa / Echo | Unofficial account login (`alexapy`) emulating "Alexa, play `<station>` on TuneIn" | Least solid leg — no official API exists for this on Alexa at all; isolated so its failures don't affect anything else |

## Verifying the stream URL

The app ships with a default stream URL for Warna 94.2FM
(`https://playerservices.streamtheworld.com/api/livestream-redirect/WARNA942FMAAC_SC`),
found via a third-party station directory that lists Mediacorp/RTM
stations' actual StreamTheWorld CDN endpoints. **This could not be
verified end-to-end from the build environment**, which has no route to
the public internet at all — the very first thing to do after deploying is
use the **Test Now** button on a device in the Devices page and confirm
you actually hear the station. If it doesn't work, the Settings page lets
you paste a different stream URL with no code changes needed — the
easiest way to find a working one is opening
[melisten.sg/radio/warna-942fm](https://www.melisten.sg/radio/warna-942fm)
in a desktop browser, hitting play, and checking the browser's Network tab
for the actual audio request URL.

## Prayer time source

- **Singapore (default)**: the official MUIS "Muslim Prayer Timetable",
  published as open government data at
  [data.gov.sg](https://data.gov.sg/datasets/d_d441e7242e78efc566024dd5b0d9829c/view).
  This is MUIS's own published timetable, republished by the Singapore
  government — the most authoritative source available, and stable
  (published a year at a time).
- **Anywhere else**: switch "Prayer time source" in Settings to the
  generic Aladhan calculation API and enter your latitude/longitude and
  preferred calculation method.

If a daily fetch fails, the app keeps using the last successfully cached
timetable and shows a warning in the log — it never goes silent for a
whole day because of one network hiccup.

## Deploying on a Synology NAS (Container Manager)

1. Enable SSH (Control Panel → Terminal & SNMP) and Container Manager
   (from Package Center) if not already on.
2. Copy this whole folder onto the NAS, e.g. to
   `/volume1/docker/azan-radio-scheduler`.
3. Copy `.env.example` to `.env` and adjust the timezone if needed.
4. In Container Manager, create a project from this folder's
   `docker-compose.yml` — **make sure "Use the same network as Docker
   host" is enabled** (this is `network_mode: host` in the compose file).
   This is required, not optional: Google Cast and AirPlay discovery both
   rely on local-network multicast (mDNS) traffic that a normal Docker
   bridge network blocks.
5. Start the project. Visit `http://<nas-ip>:8730` and set an admin
   password on first load.
6. Go to **Settings** and enter your radio stream URL, duration, and
   confirm the prayer-time source.
7. Go to **Devices** and add your speakers:
   - **Google Home**: click Discover, then Add.
   - **HomePod**: click Discover, click Pair, enter the PIN shown on the
     HomePod, then Add.
   - **Alexa**: log into your Amazon account once (solving a CAPTCHA here
     if Amazon shows one), then Discover, then Add.
8. Use the **Start/Stop** test buttons next to each device before trusting
   it to a real prayer time.

### Deploying anywhere else (generic Docker)

```
git clone <this repo>
cd azan-radio-scheduler
cp .env.example .env
docker compose up -d --build
```

Same host-networking requirement applies on any Docker host.

## HomePod fallback (if AirPlay streaming proves unreliable)

If `pyatv` streaming to your specific HomePod/OS version is flaky, you can
route around it using Homebridge (if you already run it, as Sherif does):
create a virtual switch in Homebridge, add a HomeKit Automation that plays
a Siri Shortcut / scene on that HomePod when the switch turns on, and point
this app at that switch instead via a small custom webhook backend (not
included by default, since most setups won't need it — ask if you want
this wired up).

## Project layout

```
app/
  main.py              FastAPI app + all routes (admin UI + JSON API)
  db.py                SQLite storage: settings, devices, prayer cache, schedule, activity log
  scheduler.py          The tick-loop scheduler (see "How it works")
  prayer_times.py       MUIS (data.gov.sg) + generic Aladhan fetchers, with caching/fallback
  logging_setup.py      Rotating file logger
  backends/
    base.py             Shared interface + timeout/retry wrapper
    google_cast.py       Google Home / Nest (pychromecast)
    homepod_airplay.py   Apple HomePod (pyatv)
    alexa.py             Amazon Alexa (alexapy)
  web/                  Jinja2 templates + static assets for the admin UI
data/                   Everything persistent (Docker volume): SQLite DB, logs,
                         AirPlay/Alexa credentials
Dockerfile, docker-compose.yml, requirements.txt, .env.example
```

## Operational notes

- All settings (duration, enabled prayers, stream URL, devices) live in
  `data/app.db` (SQLite, WAL mode) and survive container restarts/rebuilds
  as long as the `data/` volume is kept.
- If the container is restarted mid-prayer-window, it resumes correctly
  (won't re-fire a prayer that already started, won't skip the stop).
- If the container was completely offline through an entire prayer's
  window, that prayer is marked "skipped" rather than firing a late,
  out-of-context azan when it comes back up.
- Full-detail logs (including tracebacks) are in
  `data/logs/azan.log` (rotated, 5MB × 5 files kept). The admin UI's Logs
  page shows a human-readable summary of the same events.
- `/healthz` is a plain liveness endpoint for Docker's healthcheck.

## License

MIT — see `LICENSE`.
