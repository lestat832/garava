"""Configuration management for Garava."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Application configuration loaded from environment and database."""

    # Paths
    db_path: Path = field(default_factory=lambda: Path(os.getenv("GARAVA_DB_PATH", "./garava.db")))
    garth_home: Path = field(
        default_factory=lambda: Path(os.getenv("GARTH_HOME", Path.home() / ".garth"))
    )

    # Sync settings
    poll_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("GARAVA_POLL_INTERVAL", "10"))
    )
    fetch_limit: int = field(default_factory=lambda: int(os.getenv("GARAVA_FETCH_LIMIT", "20")))
    blocked_activity_types: list[str] = field(default_factory=list)

    # Strava OAuth
    strava_client_id: str = field(default_factory=lambda: os.getenv("STRAVA_CLIENT_ID", ""))
    strava_client_secret: str = field(default_factory=lambda: os.getenv("STRAVA_CLIENT_SECRET", ""))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("GARAVA_LOG_LEVEL", "INFO"))

    def __post_init__(self) -> None:
        """Parse blocked types from env if not already set."""
        if not self.blocked_activity_types:
            env_types = os.getenv("GARAVA_BLOCKED_TYPES", "strength_training")
            self.blocked_activity_types = [t.strip() for t in env_types.split(",") if t.strip()]

    @classmethod
    def load(cls, db_path: Path | None = None) -> Config:
        """Load config from environment, with optional DB overrides."""
        config = cls()

        if db_path:
            config.db_path = db_path

        # Load additional settings from DB config table if it exists
        if config.db_path.exists():
            config._load_db_overrides()

        return config

    def _load_db_overrides(self) -> None:
        """Load config overrides from database config table."""
        import sqlite3

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT key, value FROM config")
            for key, value in cursor.fetchall():
                if key == "blocked_types":
                    self.blocked_activity_types = json.loads(value)
                elif key == "poll_interval_minutes":
                    self.poll_interval_minutes = int(value)
                elif key == "fetch_limit":
                    self.fetch_limit = int(value)
            conn.close()
        except sqlite3.OperationalError:
            # Table doesn't exist yet, that's fine
            pass

    def validate(self) -> list[str]:
        """Return list of validation errors, empty if valid."""
        errors = []

        if not self.strava_client_id:
            errors.append("STRAVA_CLIENT_ID environment variable is required")
        if not self.strava_client_secret:
            errors.append("STRAVA_CLIENT_SECRET environment variable is required")
        if self.poll_interval_minutes < 1:
            errors.append("Poll interval must be at least 1 minute")
        if self.fetch_limit < 1:
            errors.append("Fetch limit must be at least 1")

        return errors


def get_config() -> Config:
    """Get the application configuration."""
    return Config.load()
