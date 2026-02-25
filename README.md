# Garava

**Selective Garmin-to-Strava activity sync.** Choose exactly which Garmin activities make it to Strava — block the rest.

## The Problem

If you wear a Garmin watch and also use a cycling computer (or any other device that uploads to Strava directly), you end up with duplicates. Garmin Connect's native sync pushes *everything* to Strava — every gym session, indoor ride, sauna visit and breathwork exercise. There's no built-in way to filter.

Garava sits between Garmin Connect and Strava. It downloads your activities, checks them against a blocklist you configure and only uploads the ones you actually want. The rest stay on Garmin where they belong.

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

Garava downloads the original FIT files from Garmin and uploads them directly to Strava — no data loss, full sensor data preserved. A local SQLite database tracks every processed activity so nothing gets duplicated or missed.

## Features

- **Selective sync** — configurable blocklist for activity types (strength training, indoor cycling, yoga, etc.)
- **FIT file preservation** — uploads original Garmin FIT files to Strava with full sensor data intact
- **Idempotent** — tracks every activity by Garmin ID, never processes the same one twice
- **Auto token refresh** — handles expired Strava OAuth tokens transparently
- **Flexible scheduling** — run once on demand or poll continuously at a configurable interval
- **Failed activity retry** — automatically retries previously failed uploads on the next cycle
- **Auth recovery** — re-authenticates mid-cycle if Garmin session expires
- **Docker ready** — includes Dockerfile and docker-compose for always-on deployment

## Quick Start

### Prerequisites

- Python 3.9+
- A [Strava API application](https://www.strava.com/settings/api) (you'll need the Client ID and Client Secret)
- Garmin Connect account credentials

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

Set `GARAVA_BLOCKED_TYPES` to a comma-separated list of Garmin activity type keys:

```
GARAVA_BLOCKED_TYPES=strength_training,indoor_cycling,breathwork,yoga
```

Common types you might want to block:

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
