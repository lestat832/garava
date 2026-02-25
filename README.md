# Garava

**Selective Garmin-to-Strava activity sync.** Use the right data source for each activity on Strava -- block the ones your other devices already handle better.

## Why this exists

Garmin Connect's native Strava sync pushes everything your watch records. No filter. That's fine if a Garmin watch is your only device -- but if you also record with a cycling computer, a gym app or anything else that syncs to Strava on its own, you end up with duplicates. And Garmin's version is usually the worse one.

### Garmin watch + Hammerhead Karoo

You wear a Garmin watch all day for training load and recovery data, and you ride with a Karoo. Both record the ride. The Karoo has your power meter, shifting data and full cycling metrics -- that's the version you want on Strava. But Garmin pushes the watch's version too, so you get a duplicate or Strava picks the wrong one.

**Fix:** Garava blocks Garmin's cycling types so only the Karoo's upload reaches Strava. Your watch still tracks the ride for Garmin's training load -- it just doesn't push it to Strava.

### Garmin watch + Hevy

You wear a Garmin watch during gym sessions so it counts toward training load, but you log your actual workout in Hevy -- sets, reps, weight, rest times. Hevy syncs to Strava with all that detail. Garmin also syncs a generic "Strength Training" entry with nothing but heart rate and duration. Two entries for the same session and the Garmin one is useless.

**Fix:** Garava blocks Garmin's strength training type so only Hevy's detailed log makes it to Strava.

### The pattern

Any time you have a better source for a specific activity type, Garava blocks the Garmin version and keeps the good one. Everything else (runs, swims, hikes) still syncs from Garmin automatically.

## How It Works

```
Garmin Connect
      │
      ▼
   Garava
   ┌─────────────────────┐
   │  Fetch activities    │
   │  Apply blocklist     │
   │  Download FIT file   │
   │  Upload to Strava    │
   │  Record in database  │
   └─────────────────────┘
      │
      ▼
    Strava
```

It downloads the original FIT files from Garmin and uploads them to Strava, so you keep all your sensor data (heart rate, power, GPS, etc.). A SQLite database tracks what's been processed so nothing gets duplicated or missed.

## Features

- **Selective sync** — block Garmin activity types you have a better source for (cycling computer, gym app, etc.)
- **FIT file upload** — sends the original Garmin FIT files to Strava so all sensor data comes through
- **No duplicates** — tracks every activity by Garmin ID, won't process the same one twice
- **Token refresh** — refreshes expired Strava OAuth tokens on its own
- **Flexible scheduling** — run once on demand or poll continuously on an interval
- **Retries** — if an upload fails, it tries again next cycle
- **Auth recovery** — if Garmin auth expires mid-cycle, it re-authenticates and keeps going
- **Docker support** — includes Dockerfile and docker-compose for running on a server

## Important: Before You Start

**Disable Garmin's native Strava sync.** Garava replaces it entirely -- your runs, hikes and swims still get synced through Garava instead of Garmin's direct connection. In Garmin Connect, go to Settings > Third-Party Apps > Strava and remove the connection. If you leave it on, both Garava and Garmin will push activities and you'll get duplicates.

**Your machine needs to be on.** Garava runs as a background process on your computer (or a server). If your laptop is asleep or shut down, syncing pauses until it wakes up. Nothing gets lost — it picks up where it left off.

## Quick Start

### Prerequisites

- Python 3.9+
- A [Strava API application](https://www.strava.com/settings/api) (you need the Client ID and Client Secret)
- Garmin Connect account

### Install

```bash
git clone https://github.com/lestat832/garava.git
cd garava
pip install -e .
```

### Configure

```bash
cp .env.example .env
```

Edit `.env` with your Strava API credentials:

```
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
```

### Setup Auth

```bash
garava setup
```

This walks you through logging into Garmin Connect and authorizing Strava access.

### Run

```bash
# Single sync cycle
garava run --once

# Continuous sync (runs at :00, :15, :30, :45)
garava run
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STRAVA_CLIENT_ID` | — | Strava API application client ID |
| `STRAVA_CLIENT_SECRET` | — | Strava API application client secret |
| `GARAVA_BLOCKED_TYPES` | `strength_training` | Comma-separated activity types to skip |
| `GARAVA_POLL_INTERVAL` | — | Deprecated. Sync runs at quarter-hour marks (:00, :15, :30, :45) |
| `GARAVA_FETCH_LIMIT` | `20` | Max activities to fetch per cycle |
| `GARAVA_DB_PATH` | `./garava.db` | Path to SQLite database |
| `GARTH_HOME` | `~/.garth` | Path to Garmin session tokens |

### Blocked Activity Types

By default, only `strength_training` is blocked. You configure the blocklist based on which activity types you have a better source for.

Set `GARAVA_BLOCKED_TYPES` to a comma-separated list of Garmin activity type keys. Some common setups:

**Karoo cyclist** -- block all cycling so the Karoo is the sole source on Strava:

```
GARAVA_BLOCKED_TYPES=cycling,road_biking,mountain_biking,gravel_cycling,indoor_cycling,virtual_ride
```

**Hevy gym user** -- block strength training so Hevy's detailed logs are the sole source:

```
GARAVA_BLOCKED_TYPES=strength_training
```

**Both:**

```
GARAVA_BLOCKED_TYPES=cycling,road_biking,mountain_biking,gravel_cycling,indoor_cycling,virtual_ride,strength_training
```

Here are the type keys Garmin uses, so you know what to put in your blocklist:

| Type Key | Activity |
|----------|----------|
| `cycling` | Cycling (general) |
| `road_biking` | Road cycling |
| `mountain_biking` | Mountain biking |
| `gravel_cycling` | Gravel riding |
| `virtual_ride` | Virtual / Zwift rides |
| `indoor_cycling` | Stationary bike, trainer |
| `strength_training` | Weight lifting, gym |
| `indoor_cardio` | Treadmill, elliptical |
| `breathwork` | Breathing exercises |
| `yoga` | Yoga |
| `pilates` | Pilates |
| `fitness_equipment` | General gym equipment |

## CLI Reference

| Command | Description |
|---------|-------------|
| `garava setup` | Interactive auth setup for Garmin and Strava |
| `garava run` | Continuous sync with polling (`--once` for a single cycle) |
| `garava status` | Show sync stats, last run time and any failed activities |
| `garava history` | Show recently processed activities (`--limit N`, default 20) |

All commands accept `--log-level` (DEBUG, INFO, WARNING, ERROR).

## Docker

```bash
# First: run setup locally (interactive auth)
garava setup

# Then: deploy with Docker
cd docker
docker-compose up -d
```

The Docker setup uses a persistent volume for the database and Garmin session tokens. Strava credentials are passed through from your `.env` file.

## License

[MIT](LICENSE)
