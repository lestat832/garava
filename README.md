# Garava

**Selective Garmin-to-Strava activity sync.** Pick which activities get synced, block the ones you don't want.

## Why this exists

If you wear a Garmin watch and also record with a cycling computer (or any other device that uploads to Strava on its own), you get duplicate rides on Strava. And even without a second device, Garmin's native sync pushes *everything* — gym sessions, indoor rides, sauna, breathwork. There's no way to tell it "sync my runs but skip the rest."

Garava replaces Garmin's native Strava sync. You give it a blocklist of activity types to ignore and it handles the rest — pulls activities from Garmin, skips the ones you don't want and uploads the FIT files for everything else.

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

- **Selective sync** — block any Garmin activity type you don't want on Strava (e.g. strength training, indoor cycling)
- **FIT file upload** — sends the original Garmin FIT files to Strava so all sensor data comes through
- **No duplicates** — tracks every activity by Garmin ID, won't process the same one twice
- **Token refresh** — refreshes expired Strava OAuth tokens on its own
- **Flexible scheduling** — run once on demand or poll continuously on an interval
- **Retries** — if an upload fails, it tries again next cycle
- **Auth recovery** — if Garmin auth expires mid-cycle, it re-authenticates and keeps going
- **Docker support** — includes Dockerfile and docker-compose for running on a server

## Important: Before You Start

**Disable Garmin's native Strava sync.** Since Garava replaces it, you need to disconnect the built-in integration. In Garmin Connect, go to Settings > Third-Party Apps > Strava and remove the connection. If you leave it on, both Garava and Garmin will push activities to Strava and you'll get duplicates.

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

# Continuous polling (default: every 10 minutes)
garava run
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STRAVA_CLIENT_ID` | — | Strava API application client ID |
| `STRAVA_CLIENT_SECRET` | — | Strava API application client secret |
| `GARAVA_BLOCKED_TYPES` | `strength_training` | Comma-separated activity types to skip |
| `GARAVA_POLL_INTERVAL` | `10` | Minutes between sync cycles |
| `GARAVA_FETCH_LIMIT` | `20` | Max activities to fetch per cycle |
| `GARAVA_DB_PATH` | `./garava.db` | Path to SQLite database |
| `GARTH_HOME` | `~/.garth` | Path to Garmin session tokens |

### Blocked Activity Types

By default, only `strength_training` is blocked. You pick what to block based on what you don't want on Strava.

Set `GARAVA_BLOCKED_TYPES` to a comma-separated list of Garmin activity type keys. For example, if you wanted to block gym sessions and indoor rides:

```
GARAVA_BLOCKED_TYPES=strength_training,indoor_cycling
```

Here are the type keys Garmin uses, so you know what to put in your blocklist:

| Type Key | Activity |
|----------|----------|
| `strength_training` | Weight lifting, gym workouts |
| `indoor_cycling` | Stationary bike, trainer rides |
| `indoor_cardio` | Treadmill, elliptical |
| `breathwork` | Breathing exercises |
| `yoga` | Yoga sessions |
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
