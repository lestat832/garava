"""Strava activity upload handling."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

from stravalib.exc import ActivityUploadFailed, TimeoutExceeded

from garava.strava.client import StravaClient

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Base class for upload errors."""


class DuplicateActivityError(UploadError):
    """Raised when activity already exists in Strava."""

    def __init__(self, message: str, existing_id: str | None = None):
        super().__init__(message)
        self.existing_id = existing_id


class UploadTimeoutError(UploadError):
    """Raised when upload processing times out."""


class UploadProcessingError(UploadError):
    """Raised when Strava fails to process the upload."""


@dataclass
class UploadResult:
    """Result of an activity upload."""

    success: bool
    strava_activity_id: str | None = None
    error: str | None = None
    is_duplicate: bool = False
    duplicate_id: str | None = None


def upload_fit_file(
    strava_client: StravaClient,
    fit_bytes: bytes,
    external_id: str,
    activity_name: str | None = None,
    timeout: int = 120,
    poll_interval: int = 2,
) -> UploadResult:
    """Upload a FIT file to Strava.

    Args:
        strava_client: Authenticated StravaClient
        fit_bytes: Raw FIT file bytes
        external_id: Unique identifier for this upload (for idempotency)
        activity_name: Optional name override for the activity
        timeout: Maximum seconds to wait for processing
        poll_interval: Seconds between status checks

    Returns:
        UploadResult with status and activity ID
    """
    try:
        # Create upload
        uploader = strava_client.client.upload_activity(
            activity_file=io.BytesIO(fit_bytes),
            data_type="fit",
            external_id=external_id,
            name=activity_name,
        )

        logger.debug(f"Upload started, waiting for processing (timeout={timeout}s)")

        # Wait for processing
        activity = uploader.wait(timeout=timeout, poll_interval=poll_interval)

        logger.info(f"Upload successful: Strava activity {activity.id}")
        return UploadResult(
            success=True,
            strava_activity_id=str(activity.id),
        )

    except ActivityUploadFailed as e:
        error_msg = str(e).lower()

        # Check for duplicate
        if "duplicate" in error_msg:
            duplicate_id = _parse_duplicate_id(str(e))
            logger.info(f"Duplicate activity detected: {duplicate_id}")
            return UploadResult(
                success=True,  # Not a failure, just already exists
                is_duplicate=True,
                duplicate_id=duplicate_id,
                strava_activity_id=duplicate_id,
            )

        logger.error(f"Upload failed: {e}")
        return UploadResult(
            success=False,
            error=str(e),
        )

    except TimeoutExceeded as e:
        logger.error(f"Upload timed out after {timeout}s: {e}")
        return UploadResult(
            success=False,
            error=f"Upload processing timed out after {timeout} seconds",
        )

    except Exception as e:
        logger.error(f"Upload error: {e}")
        return UploadResult(
            success=False,
            error=str(e),
        )


def _parse_duplicate_id(error_message: str) -> str | None:
    """Try to extract the existing activity ID from a duplicate error message.

    Strava sometimes includes the existing activity ID in the error.

    Args:
        error_message: The error message from Strava

    Returns:
        Activity ID if found, None otherwise
    """
    # Pattern: activity ID is often mentioned like "activity XXXXX"
    patterns = [
        r"activity[:\s]+(\d+)",
        r"id[:\s]+(\d+)",
        r"(\d{10,})",  # Activity IDs are typically 10+ digits
    ]

    for pattern in patterns:
        match = re.search(pattern, error_message, re.IGNORECASE)
        if match:
            return match.group(1)

    return None
