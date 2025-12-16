"""Garmin Connect client wrapper using garth."""

from __future__ import annotations

import logging
from pathlib import Path

import garth
from garth.exc import GarthException

logger = logging.getLogger(__name__)


class GarminAuthError(Exception):
    """Raised when Garmin authentication fails."""


class GarminClient:
    """Client for Garmin Connect API using garth library."""

    def __init__(self, garth_home: Path) -> None:
        self.garth_home = garth_home
        self._authenticated = False

    def login(self, email: str, password: str) -> None:
        """Authenticate with Garmin Connect (interactive, may require MFA)."""
        try:
            garth.login(email, password)
            garth.save(self.garth_home)
            self._authenticated = True
            logger.info("Successfully logged in to Garmin Connect")
        except GarthException as e:
            raise GarminAuthError(f"Failed to login to Garmin: {e}") from e

    def resume_session(self) -> None:
        """Resume a previously saved session."""
        try:
            garth.resume(self.garth_home)
            self._authenticated = True
            logger.debug("Resumed Garmin session from saved tokens")
        except FileNotFoundError:
            raise GarminAuthError(
                f"No saved Garmin session found at {self.garth_home}. "
                "Run 'garava setup' first to authenticate."
            )
        except GarthException as e:
            raise GarminAuthError(f"Failed to resume Garmin session: {e}") from e

    def verify_session(self) -> bool:
        """Verify the current session is valid by making a test request."""
        if not self._authenticated:
            self.resume_session()

        try:
            # Simple request to verify authentication
            garth.connectapi("/userprofile-service/socialProfile")
            return True
        except GarthException as e:
            logger.warning(f"Session verification failed: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._authenticated

    def get_activities(self, start: int = 0, limit: int = 20) -> list[dict]:
        """Fetch recent activities from Garmin Connect.

        Args:
            start: Starting index for pagination
            limit: Number of activities to fetch

        Returns:
            List of activity dictionaries from Garmin API
        """
        if not self._authenticated:
            self.resume_session()

        try:
            activities = garth.connectapi(
                "/activitylist-service/activities/search/activities",
                params={"start": start, "limit": limit},
            )
            logger.debug(f"Fetched {len(activities)} activities from Garmin")
            return activities
        except GarthException as e:
            logger.error(f"Failed to fetch activities: {e}")
            raise

    def download_activity_fit(self, activity_id: str) -> bytes:
        """Download the original FIT file for an activity.

        Args:
            activity_id: Garmin activity ID

        Returns:
            Raw bytes of the ZIP file containing the FIT file
        """
        if not self._authenticated:
            self.resume_session()

        try:
            # Download returns a ZIP containing the FIT file
            response = garth.download(
                f"/download-service/files/activity/{activity_id}"
            )
            logger.debug(f"Downloaded FIT file for activity {activity_id}")
            return response
        except GarthException as e:
            logger.error(f"Failed to download activity {activity_id}: {e}")
            raise
