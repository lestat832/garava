"""Data models for Garava."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ActivityStatus(str, Enum):
    """Status of a processed activity."""

    SYNCED = "synced"
    SKIPPED = "skipped"
    FAILED = "failed"
    DUPLICATE = "duplicate"


@dataclass
class Activity:
    """Record of a processed Garmin activity."""

    garmin_activity_id: str
    activity_type: str
    garmin_start_time: str
    status: ActivityStatus
    activity_name: str = ""
    strava_activity_id: str | None = None
    skip_reason: str | None = None
    error_message: str | None = None
    processed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    id: int | None = None

    @classmethod
    def from_row(cls, row: tuple) -> Activity:
        """Create Activity from database row."""
        return cls(
            id=row[0],
            garmin_activity_id=row[1],
            activity_type=row[2],
            activity_name=row[3] or "",
            garmin_start_time=row[4],
            status=ActivityStatus(row[5]),
            strava_activity_id=row[6],
            skip_reason=row[7],
            error_message=row[8],
            processed_at=row[9],
        )


@dataclass
class StravaToken:
    """Strava OAuth2 tokens."""

    access_token: str
    refresh_token: str
    expires_at: int  # Unix timestamp
    athlete_id: int | None = None
    id: int = 1  # Always 1 for single-user

    @classmethod
    def from_row(cls, row: tuple) -> StravaToken:
        """Create StravaToken from database row."""
        return cls(
            id=row[0],
            access_token=row[1],
            refresh_token=row[2],
            expires_at=row[3],
            athlete_id=row[4],
        )

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired or will expire soon."""
        import time

        return self.expires_at < (time.time() + buffer_seconds)


@dataclass
class SyncRun:
    """Record of a sync cycle execution."""

    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str | None = None
    activities_checked: int = 0
    activities_synced: int = 0
    activities_skipped: int = 0
    activities_failed: int = 0
    error: str | None = None
    id: int | None = None

    @classmethod
    def from_row(cls, row: tuple) -> SyncRun:
        """Create SyncRun from database row."""
        return cls(
            id=row[0],
            started_at=row[1],
            completed_at=row[2],
            activities_checked=row[3],
            activities_synced=row[4],
            activities_skipped=row[5],
            activities_failed=row[6],
            error=row[7],
        )

    def complete(self) -> None:
        """Mark this run as completed."""
        self.completed_at = datetime.utcnow().isoformat()


@dataclass
class GarminActivity:
    """Parsed Garmin activity from API response."""

    activity_id: str
    activity_type: str
    activity_name: str
    start_time: str
    duration_seconds: float | None = None
    distance_meters: float | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> GarminActivity:
        """Parse from Garmin Connect API response."""
        return cls(
            activity_id=str(data["activityId"]),
            activity_type=data.get("activityType", {}).get("typeKey", "unknown"),
            activity_name=data.get("activityName", ""),
            start_time=data.get("startTimeGMT", ""),
            duration_seconds=data.get("duration"),
            distance_meters=data.get("distance"),
        )
