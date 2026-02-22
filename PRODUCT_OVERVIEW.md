# Garava — Product Overview

## Project Overview

Garava is a selective Garmin-to-Strava activity sync service. It downloads activities from Garmin Connect, filters them through a configurable blocklist (e.g., skip strength training), and uploads the original FIT files to Strava. The service is idempotent — a SQLite database tracks every processed activity to prevent duplicate uploads.

**Target user:** Individual athlete who uses Garmin devices but wants selective activity sync to Strava (e.g., sync runs and rides but not gym sessions).

## Tech Stack

| Component | Library | Version Constraint |
|---|---|---|
| Language | Python | >= 3.9 |
| Build system | Hatchling | — |
| Garmin API | garth | >= 0.4.46 |
| Strava API | stravalib | >= 1.6, < 2 |
| CLI framework | Click | >= 8.1.0 |
| Scheduler | APScheduler | >= 3.10.0 |
| Env loading | python-dotenv | >= 1.0.0 |
| Database | SQLite3 | stdlib |
| Linter | Ruff | >= 0.1.0 (dev) |
| Testing | pytest | >= 8.0 (dev) |
| Container | Docker | python:3.11-slim |

## Architecture

```
Garmin Connect API
       │
       ▼
  GarminClient (garth)          ──→  garmin/client.py
       │
       ▼
  get_recent_activities()       ──→  garmin/activities.py
       │
       ▼
  ActivityFilter.should_sync()  ──→  sync/filters.py
       │ (pass)          │ (block)
       ▼                 ▼
  download_fit_file()    _record_skipped()
       │
       ▼
  upload_fit_file()             ──→  strava/upload.py
       │
       ▼
  Database.insert_activity()    ──→  database.py
```

**Module responsibilities:**

| Module | Responsibility |
|---|---|
| `garava/config.py` | Config dataclass, env var loading, DB config overrides |
| `garava/models.py` | Activity, StravaToken, SyncRun, GarminActivity dataclasses |
| `garava/database.py` | SQLite Database class, SCHEMA constant, all CRUD operations |
| `garava/__main__.py` | Entry point — loads dotenv before imports |
| `garava/cli/commands.py` | Click CLI group: setup, run, status, history |
| `garava/garmin/client.py` | GarminClient wrapping garth — login, resume, verify, fetch, download |
| `garava/garmin/activities.py` | Activity list parsing, FIT file extraction from ZIP |
| `garava/strava/client.py` | StravaClient wrapping stravalib — OAuth, token exchange, refresh |
| `garava/strava/auth.py` | OAuth2 flow with local HTTP callback server, token refresh |
| `garava/strava/upload.py` | FIT upload, duplicate detection, polling for processing |
| `garava/sync/core.py` | SyncEngine orchestration — auth check, fetch, process loop |
| `garava/sync/processor.py` | Single activity pipeline (core business logic) |
| `garava/sync/filters.py` | ActivityFilter blocklist with case-insensitive matching |

## Key Features

- **Selective sync** — configurable activity type blocklist (default: blocks `strength_training`)
- **Idempotent processing** — SQLite tracks every activity by Garmin ID, never re-processes
- **FIT file preservation** — downloads original FIT from Garmin ZIP, uploads raw to Strava (no data loss)
- **Duplicate detection** — handles Strava's "duplicate activity" response gracefully
- **Token management** — auto-refreshes expired Strava OAuth tokens with 5-minute buffer
- **Continuous or one-shot** — `run --once` for single cycle, `run` for polling at configurable interval
- **Initial sync boundary** — records first-run timestamp, skips activities before that time
- **Interactive setup** — `setup` command handles both Garmin login and Strava OAuth in one flow
- **Docker deployment** — Dockerfile + docker-compose with persistent volume for data

## Business Logic

### Sync Pipeline (`sync/processor.py`)

For each Garmin activity, the pipeline runs in order:

1. **Idempotency check** — `db.activity_exists(garmin_id)` → if yes, return `exists`
2. **Filter check** — `activity_filter.should_sync(type)` → if blocked, record as `skipped` with reason `blocked_type:<type>`
3. **Initial sync boundary** — compare `start_time` against `initial_sync_time` → if before, record as `skipped` with reason `before_initial_sync`
4. **Download FIT** — `download_fit_file(client, id)` → extracts `.fit` from ZIP archive
5. **Upload to Strava** — `upload_fit_file(strava, fit_bytes, external_id)` → polls for processing completion
6. **Record result** — writes Activity row with status: `synced`, `duplicate`, `skipped`, or `failed`

### Activity Statuses

| Status | Meaning |
|---|---|
| `synced` | Successfully uploaded to Strava |
| `skipped` | Blocked by filter or before initial sync time |
| `failed` | Download or upload error |
| `duplicate` | Already exists in Strava (detected by Strava API) |

### Filter Configuration

- Default blocklist: `strength_training`
- Configurable via `GARAVA_BLOCKED_TYPES` env var (comma-separated) or DB `config` table
- Case-insensitive matching against Garmin's `activityType.typeKey`
- Optional types to consider blocking: `indoor_cardio`, `breathwork`, `yoga`, `pilates`, `fitness_equipment`

## CLI Interface

| Command | Description | Key Options |
|---|---|---|
| `garava setup` | Interactive auth for Garmin + Strava | — |
| `garava run` | Continuous sync with polling | `--once` (single cycle) |
| `garava status` | Show stats, last run, failed activities | — |
| `garava history` | Show recent processed activities | `--limit N` (default 20) |

Global option: `--log-level` (DEBUG, INFO, WARNING, ERROR)

Entry point: `python -m garava` or `garava` (via pyproject.toml scripts)

## Data Model

### `activities` table
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| garmin_activity_id | TEXT UNIQUE | Garmin's activity ID |
| activity_type | TEXT | Garmin typeKey (e.g., `running`) |
| activity_name | TEXT | Activity title |
| garmin_start_time | TEXT | ISO timestamp from Garmin |
| status | TEXT | synced/skipped/failed/duplicate |
| strava_activity_id | TEXT | Strava ID if uploaded |
| skip_reason | TEXT | Why it was skipped |
| error_message | TEXT | Error details if failed |
| processed_at | TEXT | When Garava processed it |
| created_at | TEXT | DB insertion time |

### `strava_tokens` table
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Always 1 (single-user) |
| access_token | TEXT | Current OAuth access token |
| refresh_token | TEXT | For token refresh |
| expires_at | INTEGER | Unix timestamp |
| athlete_id | INTEGER | Strava athlete ID |
| updated_at | TEXT | Last token update |

### `sync_runs` table
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| started_at | TEXT | Cycle start time |
| completed_at | TEXT | Cycle end time |
| activities_checked | INTEGER | Total activities fetched |
| activities_synced | INTEGER | Successfully uploaded |
| activities_skipped | INTEGER | Filtered out |
| activities_failed | INTEGER | Errors |
| error | TEXT | Cycle-level error |

### `config` table
| Column | Type | Notes |
|---|---|---|
| key | TEXT PK | Config key |
| value | TEXT | JSON-encoded for lists/dicts |

Known keys: `blocked_types`, `poll_interval_minutes`, `fetch_limit`, `initial_sync_time`

## Authentication & Authorization

### Garmin Connect
- Library: `garth` (handles Garmin's SSO flow including MFA)
- Session persisted to disk at `GARTH_HOME` (default `~/.garth/`)
- On each cycle: `verify_session()` → `resume_session()` → if both fail, `AuthenticationError` halts the cycle
- No automatic re-login — user must re-run `garava setup` if session expires

### Strava OAuth2
- Standard OAuth2 Authorization Code flow
- Scopes: `activity:read_all`, `activity:write`
- Local HTTP callback server on `localhost:8000/callback` (120s timeout)
- Token stored in `strava_tokens` table (single row, id=1)
- Auto-refresh: `ensure_valid_token()` checks expiry with 5-minute buffer, refreshes if needed
- Token refresh happens transparently at the start of each sync cycle

## Infrastructure & Deployment

### Local Development
```
pip install -e ".[dev]"
cp .env.example .env  # Fill in Strava credentials
python -m garava setup
python -m garava run --once
```

### Docker
- Image: `python:3.11-slim`
- Persistent volume `garava-data` mounted at `/data` (DB + Garmin tokens)
- Env vars passed through from host `.env`
- Restart policy: `unless-stopped`
- Note: `garava setup` must be run locally first (interactive auth), then copy `.garth/` and `garava.db` to the Docker volume

```
cd docker
docker-compose up -d
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `STRAVA_CLIENT_ID` | Yes | — | Strava API application client ID |
| `STRAVA_CLIENT_SECRET` | Yes | — | Strava API application client secret |
| `GARAVA_POLL_INTERVAL` | No | `10` | Minutes between sync cycles |
| `GARAVA_FETCH_LIMIT` | No | `20` | Max activities to fetch per cycle |
| `GARAVA_BLOCKED_TYPES` | No | `strength_training` | Comma-separated activity types to skip |
| `GARAVA_DB_PATH` | No | `./garava.db` | Path to SQLite database |
| `GARTH_HOME` | No | `~/.garth` | Path to Garmin session tokens |
| `GARAVA_LOG_LEVEL` | No | `INFO` | Logging level |

## File Structure

```
garava/
├── __init__.py
├── __main__.py            # Entry point (dotenv loading)
├── config.py              # Config dataclass + env/DB loading
├── database.py            # SQLite Database class + SCHEMA
├── models.py              # Activity, StravaToken, SyncRun, GarminActivity
├── cli/
│   ├── __init__.py
│   └── commands.py        # Click CLI: setup, run, status, history
├── garmin/
│   ├── __init__.py
│   ├── client.py          # GarminClient (garth wrapper)
│   └── activities.py      # Activity fetch + FIT extraction
├── strava/
│   ├── __init__.py
│   ├── client.py          # StravaClient (stravalib wrapper)
│   ├── auth.py            # OAuth2 flow + token refresh
│   └── upload.py          # FIT upload + duplicate handling
└── sync/
    ├── __init__.py
    ├── core.py            # SyncEngine orchestration
    ├── processor.py       # Single activity pipeline
    └── filters.py         # Activity type blocklist
docker/
├── Dockerfile             # python:3.11-slim based
└── docker-compose.yml     # Persistent volume, env passthrough
.env.example               # Template for required env vars
pyproject.toml             # Hatchling build, deps, ruff config
CLAUDE.md                  # Project-specific Claude Code config
```

## Dependencies

| Package | Purpose | Constraint |
|---|---|---|
| `garth` | Garmin Connect API client (handles SSO + MFA) | >= 0.4.46 |
| `stravalib` | Strava v3 API client (upload, OAuth) | >= 1.6, < 2 (pinned for stability) |
| `click` | CLI framework | >= 8.1.0 |
| `apscheduler` | Task scheduling (declared but not yet used — polling loop is manual) | >= 3.10.0 |
| `python-dotenv` | Load `.env` files | >= 1.0.0 |

## Implementation Status

| Feature | Status | Notes |
|---|---|---|
| Garmin auth (login + resume) | Built | `garmin/client.py` |
| Garmin activity fetch | Built | `garmin/activities.py` |
| FIT file download + extraction | Built | `garmin/activities.py` |
| Activity type filtering | Built | `sync/filters.py` |
| Strava OAuth2 flow | Built | `strava/auth.py` |
| Strava token refresh | Built | `strava/auth.py` |
| FIT upload to Strava | Built | `strava/upload.py` |
| Duplicate detection | Built | `strava/upload.py` |
| Sync pipeline (full cycle) | Built | `sync/core.py` + `sync/processor.py` |
| CLI commands (setup/run/status/history) | Built | `cli/commands.py` |
| SQLite state tracking | Built | `database.py` |
| Config (env + DB overrides) | Built | `config.py` |
| Docker deployment | Built | `docker/` |
| APScheduler integration | Declared dep, not used | Polling loop is `time.sleep()` |
| Tests | Not started | No test files exist yet |
| README | Not started | — |
| Health check endpoint | Planned | Commented out in docker-compose |
| Retry logic for failed activities | Not built | Failed activities stay failed |
