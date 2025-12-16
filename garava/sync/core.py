"""Core sync engine orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from garava.config import Config
from garava.database import Database
from garava.garmin.activities import get_recent_activities
from garava.garmin.client import GarminAuthError, GarminClient
from garava.models import SyncRun
from garava.strava.auth import ensure_valid_token
from garava.strava.client import StravaClient
from garava.sync.filters import ActivityFilter
from garava.sync.processor import ProcessResult, process_activity

logger = logging.getLogger(__name__)


class SyncError(Exception):
    """Base class for sync errors."""


class AuthenticationError(SyncError):
    """Raised when authentication fails."""


@dataclass
class SyncCycleResult:
    """Result of a complete sync cycle."""

    run: SyncRun
    results: list[ProcessResult]

    @property
    def synced_count(self) -> int:
        return sum(1 for r in self.results if r.action == "synced")

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.action == "skipped")

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.action == "failed")

    @property
    def duplicate_count(self) -> int:
        return sum(1 for r in self.results if r.action == "duplicate")


class SyncEngine:
    """Main sync engine that orchestrates Garmin to Strava sync."""

    def __init__(
        self,
        config: Config,
        db: Database,
        garmin_client: GarminClient,
        strava_client: StravaClient,
        activity_filter: ActivityFilter,
    ) -> None:
        self.config = config
        self.db = db
        self.garmin = garmin_client
        self.strava = strava_client
        self.filter = activity_filter
        self._initial_sync_time: str | None = None

    def _ensure_initial_sync_time(self) -> str:
        """Get or set the initial sync timestamp."""
        if self._initial_sync_time:
            return self._initial_sync_time

        # Try to load from DB
        stored = self.db.get_config("initial_sync_time")
        if stored:
            self._initial_sync_time = stored
            return stored

        # First run - set to now
        now = datetime.utcnow().isoformat()
        self.db.set_config("initial_sync_time", now)
        self._initial_sync_time = now
        logger.info(f"Initial sync time set to {now}")
        return now

    def _ensure_auth(self) -> None:
        """Verify both Garmin and Strava authentication."""
        # Garmin
        try:
            if not self.garmin.verify_session():
                self.garmin.resume_session()
        except GarminAuthError as e:
            raise AuthenticationError(f"Garmin auth failed: {e}")

        # Strava
        token = ensure_valid_token(self.db, self.strava)
        if token is None:
            raise AuthenticationError(
                "Strava not authenticated. Run 'garava setup' to authorize."
            )

    def run_cycle(self) -> SyncCycleResult:
        """Execute one complete sync cycle.

        Returns:
            SyncCycleResult with run stats and individual results
        """
        run = self.db.create_sync_run()
        results: list[ProcessResult] = []

        try:
            # Step 1: Ensure authentication
            logger.info("Starting sync cycle...")
            self._ensure_auth()

            # Step 2: Get initial sync time
            initial_sync_time = self._ensure_initial_sync_time()

            # Step 3: Fetch recent activities from Garmin
            activities = get_recent_activities(self.garmin, limit=self.config.fetch_limit)
            run.activities_checked = len(activities)
            logger.info(f"Fetched {len(activities)} activities from Garmin")

            # Step 4: Process each activity
            for garmin_activity in activities:
                result = process_activity(
                    garmin_activity=garmin_activity,
                    db=self.db,
                    garmin_client=self.garmin,
                    strava_client=self.strava,
                    activity_filter=self.filter,
                    initial_sync_time=initial_sync_time,
                )
                results.append(result)

                # Update run counters
                if result.action == "synced":
                    run.activities_synced += 1
                elif result.action == "skipped":
                    run.activities_skipped += 1
                elif result.action == "failed":
                    run.activities_failed += 1
                elif result.action == "duplicate":
                    run.activities_synced += 1  # Count as success

            # Complete the run
            run.complete()
            self.db.update_sync_run(run)

            logger.info(
                f"Sync cycle complete: "
                f"checked={run.activities_checked}, "
                f"synced={run.activities_synced}, "
                f"skipped={run.activities_skipped}, "
                f"failed={run.activities_failed}"
            )

        except AuthenticationError as e:
            run.error = str(e)
            run.complete()
            self.db.update_sync_run(run)
            logger.error(f"Auth error during sync: {e}")
            raise

        except Exception as e:
            run.error = str(e)
            run.complete()
            self.db.update_sync_run(run)
            logger.exception(f"Unexpected error during sync: {e}")

        return SyncCycleResult(run=run, results=results)

    @classmethod
    def create(cls, config: Config) -> SyncEngine:
        """Factory method to create a fully configured SyncEngine.

        Args:
            config: Application configuration

        Returns:
            Configured SyncEngine ready to run
        """
        db = Database(config.db_path)
        garmin = GarminClient(config.garth_home)
        strava = StravaClient(config.strava_client_id, config.strava_client_secret)
        filter_ = ActivityFilter.from_config(config)

        return cls(
            config=config,
            db=db,
            garmin_client=garmin,
            strava_client=strava,
            activity_filter=filter_,
        )
