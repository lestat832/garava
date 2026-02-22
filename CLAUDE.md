# Garava

Selective Garmin-to-Strava activity sync CLI. Downloads activities from Garmin Connect, filters by configurable blocklist, uploads FIT files to Strava. Idempotent — database tracks every processed activity to prevent duplicates.

## Architecture

garava/
  config.py       — Config dataclass, env vars + DB overrides
  database.py     — SQLite Database class, SCHEMA constant, CRUD
  models.py       — Activity, StravaToken, SyncRun, GarminActivity
  __main__.py     — Entry point (loads dotenv before imports)
  cli/commands.py — Click group: setup, run, status, history
  garmin/
    client.py     — GarminClient (garth wrapper), GarminAuthError
    activities.py — Fetch activities, download/extract FIT from ZIP
  strava/
    client.py     — StravaClient (stravalib wrapper)
    auth.py       — OAuth2 with local HTTP callback server
    upload.py     — FIT upload, duplicate detection, UploadResult
  sync/
    core.py       — SyncEngine orchestration
    processor.py  — Single activity pipeline (core business logic)
    filters.py    — ActivityFilter blocklist

Data flow: Garmin API → GarminActivity → ActivityFilter → FIT download → Strava upload → DB record

## Commands

pip install -e ".[dev]"          # Install dev
ruff check garava/ tests/        # Lint (must pass before commit)
pytest                           # Test
python -m garava setup           # Interactive auth setup
python -m garava run --once      # Single sync cycle
python -m garava run             # Continuous polling
python -m garava status          # Stats
python -m garava history         # Activity log

## Code Conventions

- All modules: `from __future__ import annotations` at top
- Data containers: `@dataclass` (not Pydantic, not TypedDict)
- Type unions: `X | None` (not `Optional[X]`)
- File paths: `pathlib.Path` (not raw strings)
- Logging: `logger = logging.getLogger(__name__)` per module
- Ruff: rules E, F, I, N, W, UP; line-length 100; target py39
- Models: `from_row(cls, row: tuple)` for DB, `from_api_response(cls, data: dict)` for API
- Enums: `class XStatus(str, Enum)` for DB-serializable enums
- Database: context manager `_connect()`, parameterized queries, `SCHEMA` constant
- CLI: Click group with `@click.pass_context`, config in `ctx.obj["config"]`

## Error Handling

GarminAuthError              (garmin/client.py, standalone)
FitExtractionError           (garmin/activities.py, standalone)
SyncError                    (sync/core.py)
  └─ AuthenticationError     (sync/core.py)
UploadError                  (strava/upload.py)
  ├─ DuplicateActivityError
  ├─ UploadTimeoutError
  └─ UploadProcessingError

Pattern: Catch specific exceptions, wrap in result dataclasses (ProcessResult, UploadResult) with `success: bool` + `error: str | None`. Only AuthenticationError propagates up.

## Security

Never commit or expose:
- `.env` — STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET
- `.garth/` — Garmin session tokens
- `garava.db` — contains Strava OAuth tokens
- `logs/` — may contain activity data

## Testing

No tests yet. When adding:
- pytest with tmp_path for test databases
- Mock garth (Garmin) and stravalib (Strava) — no real API calls
- Best starting points: processor.py pipeline, filters.py logic

## Change Rules

- stravalib pinned to <2 for API stability
- DB schema: add columns/tables only, never remove/rename existing
- New CLI commands follow Click patterns in commands.py

## Learned Patterns
<!-- Auto-graduated from corrections. No hard cap — entries get absorbed into conventions above over time. -->
