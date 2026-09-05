# Azan Radio Scheduler — User Manual

*Languages: **English** · [العربية](ar.md) · [Bahasa Melayu](ms.md) · [اردو](ur.md) · [Français](fr.md)*

## About this project

This app was created by Sherif, for the sake of Allah — built freely so
that anyone can have the azan called automatically on their own smart
speakers at prayer time, with no daily manual work. It's free to use,
free to share, and free to change. If it benefits you or your family,
that's the whole point.

This manual is for using the app once it's already installed and running
— it doesn't cover installing it on a server (see the main
[README](../../README.md) for that). It assumes someone (you, a
tech-savvy friend, or family member) has already set it up and given you
a web address like `http://<your-server-address>:8730`.

## Opening the app for the first time

1. Open the app's web address in any browser (computer or phone).
2. The very first time, it will ask you to **create an admin password**
   (at least 8 characters). This is the only password protecting the app
   — choose one you'll remember, and don't share it with anyone who
   shouldn't be able to change your settings.
3. After that, every time you open the app it will ask for this password
   to log in.

## The Dashboard

This is the page you land on after logging in. It shows:

- Today's five prayer times, as fetched from the prayer-time source you
  configured.
- Whether each prayer's radio has already started/stopped today.
- A short list of recent activity (useful for a quick glance, without
  needing the full Logs page).

## Settings page

### Radio & timing

- **Stream URL** — the web address of the radio station's audio stream.
  You shouldn't normally need to change this unless the station changes
  its stream address.
- **Stream content type** — a technical detail some speakers need; leave
  as-is unless told otherwise.
- **Station name** — used only for Alexa, since Alexa can't play an
  arbitrary web address directly; it "asks" Alexa to play this station
  by name instead (like saying "Alexa, play *Warna 94.2FM*").
- **Default duration** — how many minutes the radio plays before
  automatically stopping.
- **Start early** — how many *seconds* before the actual prayer time the
  radio should start (0 = starts exactly on time). A small head start
  (e.g. 15 seconds) can be useful so the sound is already playing right
  as the prayer time begins.
- **Timezone** — the timezone prayer times are calculated/displayed in.
- **Prayer time source** — choose **Singapore (MUIS)** if you're in
  Singapore, for the official government-published timetable. Otherwise
  choose **Generic (Aladhan)** and enter your latitude/longitude and a
  calculation method — this works for anywhere in the world.

Click **Save** after making changes. **Refresh today's prayer times now**
manually re-fetches today's schedule (normally happens automatically
every day).

### Prayers

A table letting you fine-tune each of the 5 prayers individually:

- **Enabled** — untick to skip a specific prayer entirely (e.g. if you
  don't want an automatic azan for Fajr).
- **Duration override** — a different play duration just for this
  prayer, overriding the global default above. Leave blank to use the
  default.
- **Start early override** — a different early-start time (in seconds)
  just for this prayer. Leave blank to use the global default; enter `0`
  to make this one prayer start exactly on time even if others start
  early.

### Admin password

Change your login password here. You'll need to enter your current
password first.

## Devices page

This is where you connect your actual smart speakers.

### Configured devices (table at the top)

Once you've added at least one device, it appears here with:

- **Enabled / Disable** — turn a device on or off entirely without
  removing it.
- **Plays for** — a checkbox for each of the 5 prayers. Untick a prayer
  to stop that *specific device* from playing at that prayer, while
  still playing at the others. This lets you, for example, have a
  bedroom speaker only play Fajr and Isha, while a living-room speaker
  plays all five.
- **Test (Start/Stop)** — manually trigger the device right now, useful
  for confirming it actually works before trusting it to a real prayer
  time.
- **Remove** — permanently delete this device from the app (you can
  always re-add it later through Discover).

### Adding a Google Home / Nest speaker

1. Click **Discover Google speakers** — this scans your local network
   for a few seconds.
2. Click **Add** next to the speaker you want. It must already be set up
   in the Google Home app on your phone first.

### Adding an Apple HomePod

1. Click **Discover HomePods**.
2. Click **Pair** next to the one you want — your HomePod will show (or
   announce) a PIN code.
3. Enter that PIN and confirm.
4. Click **Add**.

### Adding an Amazon Alexa / Echo device

Alexa doesn't offer a way to control it directly the way Google and Apple
do, so this app talks to it through a **Home Assistant** instance instead
(a separate, free, open-source home-automation program) that has the
community **Alexa Media Player** add-on installed and logged into your
Amazon account.

1. If Home Assistant with Alexa Media Player isn't already set up, ask
   whoever manages your network to set it up first (this is a one-time
   technical step).
2. In Home Assistant, generate a **Long-Lived Access Token** (found under
   your profile → Security).
3. Back in this app's Devices page, paste your Home Assistant's web
   address and that token into the Alexa card, then click **Save & test
   connection**.
4. Click **Discover Alexa devices** — this asks Home Assistant which Echo
   devices it knows about.
5. Click **Add** next to each real speaker you want (skip any entries
   that look like device groups rather than an actual physical speaker,
   such as "Everywhere" or "Echo group").

## Logs page

A running list of everything the app has done — device connections,
successful/failed plays and stops, warnings, and errors. If a prayer
didn't play, or a device didn't stop when it should have, this is the
first place to check: it'll show exactly what happened and why.

## Getting help

This project is open source and free for anyone to use, adapt, and
share. If you run into a problem, have a translation correction for this
manual, or want to suggest an improvement, please open an issue or pull
request on the project's GitHub page.

*May this be of benefit to you and your family. Jazakumullahu khairan.*
