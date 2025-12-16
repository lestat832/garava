"""Activity type filtering for sync decisions."""

from __future__ import annotations

import logging

from garava.config import Config

logger = logging.getLogger(__name__)


class ActivityFilter:
    """Determines which activities should be synced to Strava."""

    def __init__(self, blocked_types: list[str]) -> None:
        """Initialize filter with blocked activity types.

        Args:
            blocked_types: List of Garmin activity typeKeys to block
        """
        # Normalize to lowercase for case-insensitive matching
        self.blocked_types = {t.lower().strip() for t in blocked_types}
        logger.info(f"ActivityFilter initialized with blocked types: {self.blocked_types}")

    def should_sync(self, activity_type: str) -> bool:
        """Check if an activity type should be synced.

        Args:
            activity_type: Garmin activity typeKey (e.g., 'running', 'strength_training')

        Returns:
            True if activity should be synced, False if blocked
        """
        normalized_type = activity_type.lower().strip()
        should_sync = normalized_type not in self.blocked_types

        if not should_sync:
            logger.debug(f"Activity type '{activity_type}' is blocked")

        return should_sync

    def get_block_reason(self, activity_type: str) -> str | None:
        """Get the reason an activity type is blocked.

        Args:
            activity_type: Garmin activity typeKey

        Returns:
            Reason string if blocked, None if not blocked
        """
        if not self.should_sync(activity_type):
            return f"blocked_type:{activity_type.lower()}"
        return None

    @classmethod
    def from_config(cls, config: Config) -> ActivityFilter:
        """Create filter from application config.

        Args:
            config: Application configuration

        Returns:
            Configured ActivityFilter
        """
        return cls(blocked_types=config.blocked_activity_types)


# Default blocked types for reference
DEFAULT_BLOCKED_TYPES = [
    "strength_training",  # Garmin strength - blocked (use Hevy instead)
]

# Other types that users might want to optionally block
OPTIONAL_BLOCKED_TYPES = [
    "indoor_cardio",  # Often treadmill warmups before strength
    "breathwork",  # Meditation/breathing exercises
    "yoga",  # Some prefer Garmin yoga separate
    "pilates",
    "fitness_equipment",  # Generic gym equipment
]
