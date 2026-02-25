"""SQLite database operations for Garava."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from garava.models import Activity, ActivityStatus, StravaToken, SyncRun

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    garmin_activity_id TEXT UNIQUE NOT NULL,
    activity_type TEXT NOT NULL,
    activity_name TEXT,
    garmin_start_time TEXT NOT NULL,
    status TEXT NOT NULL,
    strava_activity_id TEXT,
    skip_reason TEXT,
    error_message TEXT,
    processed_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_garmin_activity_id ON activities(garmin_activity_id);
CREATE INDEX IF NOT EXISTS idx_status ON activities(status);
CREATE INDEX IF NOT EXISTS idx_processed_at ON activities(processed_at);

CREATE TABLE IF NOT EXISTS strava_tokens (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    athlete_id INTEGER,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    activities_checked INTEGER DEFAULT 0,
    activities_synced INTEGER DEFAULT 0,
    activities_skipped INTEGER DEFAULT 0,
    activities_failed INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    """SQLite database manager for Garava state."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure_schema()
        self._set_file_permissions()

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _set_file_permissions(self) -> None:
        """Set restrictive permissions on the database file (owner read/write only)."""
        try:
            os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            logger.debug("Could not set file permissions on database")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # Activity operations

    def activity_exists(self, garmin_activity_id: str) -> bool:
        """Check if an activity has been successfully processed.

        Returns False for failed activities so they can be retried.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM activities WHERE garmin_activity_id = ? AND status != ?",
                (garmin_activity_id, ActivityStatus.FAILED.value),
            )
            return cursor.fetchone() is not None

    def delete_failed_activity(self, garmin_activity_id: str) -> bool:
        """Delete a failed activity record to allow retry.

        Returns True if a record was deleted.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM activities WHERE garmin_activity_id = ? AND status = ?",
                (garmin_activity_id, ActivityStatus.FAILED.value),
            )
            conn.commit()
            return cursor.rowcount > 0

    def insert_activity(self, activity: Activity) -> Activity:
        """Insert a new activity record."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO activities (
                    garmin_activity_id, activity_type, activity_name, garmin_start_time,
                    status, strava_activity_id, skip_reason, error_message, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activity.garmin_activity_id,
                    activity.activity_type,
                    activity.activity_name,
                    activity.garmin_start_time,
                    activity.status.value,
                    activity.strava_activity_id,
                    activity.skip_reason,
                    activity.error_message,
                    activity.processed_at,
                ),
            )
            conn.commit()
            activity.id = cursor.lastrowid
        return activity

    def get_activity(self, garmin_activity_id: str) -> Activity | None:
        """Get an activity by Garmin ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, garmin_activity_id, activity_type, activity_name, garmin_start_time,
                       status, strava_activity_id, skip_reason, error_message, processed_at
                FROM activities WHERE garmin_activity_id = ?
                """,
                (garmin_activity_id,),
            )
            row = cursor.fetchone()
            if row:
                return Activity.from_row(tuple(row))
        return None

    def get_recent_activities(self, limit: int = 50) -> list[Activity]:
        """Get recent activities ordered by processed time."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, garmin_activity_id, activity_type, activity_name, garmin_start_time,
                       status, strava_activity_id, skip_reason, error_message, processed_at
                FROM activities ORDER BY processed_at DESC LIMIT ?
                """,
                (limit,),
            )
            return [Activity.from_row(tuple(row)) for row in cursor.fetchall()]

    def get_failed_activities(self) -> list[Activity]:
        """Get all failed activities for review."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, garmin_activity_id, activity_type, activity_name, garmin_start_time,
                       status, strava_activity_id, skip_reason, error_message, processed_at
                FROM activities WHERE status = ?
                """,
                (ActivityStatus.FAILED.value,),
            )
            return [Activity.from_row(tuple(row)) for row in cursor.fetchall()]

    # Strava token operations

    def get_strava_token(self) -> StravaToken | None:
        """Get the stored Strava OAuth token."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT id, access_token, refresh_token, expires_at, athlete_id FROM strava_tokens"
            )
            row = cursor.fetchone()
            if row:
                return StravaToken.from_row(tuple(row))
        return None

    def save_strava_token(self, token: StravaToken) -> None:
        """Save or update Strava OAuth token."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strava_tokens
                    (id, access_token, refresh_token, expires_at, athlete_id, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    athlete_id = excluded.athlete_id,
                    updated_at = excluded.updated_at
                """,
                (
                    token.access_token,
                    token.refresh_token,
                    token.expires_at,
                    token.athlete_id,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    # Sync run operations

    def create_sync_run(self) -> SyncRun:
        """Create a new sync run record."""
        run = SyncRun()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sync_runs (started_at) VALUES (?)", (run.started_at,)
            )
            conn.commit()
            run.id = cursor.lastrowid
        return run

    def update_sync_run(self, run: SyncRun) -> None:
        """Update a sync run with results."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs SET
                    completed_at = ?,
                    activities_checked = ?,
                    activities_synced = ?,
                    activities_skipped = ?,
                    activities_failed = ?,
                    error = ?
                WHERE id = ?
                """,
                (
                    run.completed_at,
                    run.activities_checked,
                    run.activities_synced,
                    run.activities_skipped,
                    run.activities_failed,
                    run.error,
                    run.id,
                ),
            )
            conn.commit()

    def get_last_sync_run(self) -> SyncRun | None:
        """Get the most recent sync run."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, started_at, completed_at, activities_checked,
                       activities_synced, activities_skipped, activities_failed, error
                FROM sync_runs ORDER BY id DESC LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row:
                return SyncRun.from_row(tuple(row))
        return None

    # Config operations

    def get_config(self, key: str, default: str | None = None) -> str | None:
        """Get a config value."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row[0]
        return default

    def set_config(self, key: str, value: str | list | dict) -> None:
        """Set a config value (lists/dicts are JSON encoded)."""
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO config (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = ?",
                (key, value, value),
            )
            conn.commit()

    def get_stats(self) -> dict:
        """Get overall sync statistics."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM activities
                GROUP BY status
                """
            )
            stats = {row["status"]: row["count"] for row in cursor.fetchall()}

            cursor = conn.execute("SELECT COUNT(*) FROM sync_runs")
            stats["total_runs"] = cursor.fetchone()[0]

        return stats
