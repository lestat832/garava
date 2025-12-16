"""Single activity processing pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from garava.database import Database
from garava.garmin.activities import FitExtractionError, download_fit_file
from garava.garmin.client import GarminClient
from garava.models import Activity, ActivityStatus, GarminActivity
from garava.strava.client import StravaClient
from garava.strava.upload import UploadResult, upload_fit_file
from garava.sync.filters import ActivityFilter

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """Result of processing a single activity."""

    activity: Activity
    success: bool
    action: str  # 'synced', 'skipped', 'failed', 'duplicate', 'exists'


def process_activity(
    garmin_activity: GarminActivity,
    db: Database,
    garmin_client: GarminClient,
    strava_client: StravaClient,
    activity_filter: ActivityFilter,
    initial_sync_time: str | None = None,
) -> ProcessResult:
    """Process a single Garmin activity through the sync pipeline.

    Args:
        garmin_activity: The activity to process
        db: Database for state tracking
        garmin_client: Authenticated Garmin client
        strava_client: Authenticated Strava client
        activity_filter: Filter for activity types
        initial_sync_time: ISO timestamp, skip activities before this

    Returns:
        ProcessResult indicating what happened
    """
    activity_id = garmin_activity.activity_id
    activity_type = garmin_activity.activity_type

    # Check if already processed (idempotency)
    if db.activity_exists(activity_id):
        logger.debug(f"Activity {activity_id} already processed, skipping")
        existing = db.get_activity(activity_id)
        return ProcessResult(
            activity=existing,
            success=True,
            action="exists",
        )

    # Check filter
    if not activity_filter.should_sync(activity_type):
        reason = activity_filter.get_block_reason(activity_type)
        activity = _record_skipped(db, garmin_activity, reason)
        return ProcessResult(activity=activity, success=True, action="skipped")

    # Check initial sync boundary
    # Normalize date formats for comparison (Garmin uses space, we use T separator)
    if initial_sync_time:
        activity_time = garmin_activity.start_time.replace(" ", "T")
        sync_time = initial_sync_time.replace(" ", "T")
        if activity_time < sync_time:
            activity = _record_skipped(db, garmin_activity, "before_initial_sync")
            return ProcessResult(activity=activity, success=True, action="skipped")

    # Download FIT file
    try:
        fit_bytes = download_fit_file(garmin_client, activity_id)
    except FitExtractionError as e:
        activity = _record_failed(db, garmin_activity, str(e))
        return ProcessResult(activity=activity, success=False, action="failed")
    except Exception as e:
        activity = _record_failed(db, garmin_activity, f"Download failed: {e}")
        return ProcessResult(activity=activity, success=False, action="failed")

    # Upload to Strava
    external_id = f"garmin_{activity_id}"
    result = upload_fit_file(
        strava_client=strava_client,
        fit_bytes=fit_bytes,
        external_id=external_id,
        activity_name=garmin_activity.activity_name or None,
    )

    # Record result
    if result.is_duplicate:
        activity = _record_duplicate(db, garmin_activity, result.duplicate_id)
        return ProcessResult(activity=activity, success=True, action="duplicate")

    if result.success:
        activity = _record_synced(db, garmin_activity, result.strava_activity_id)
        return ProcessResult(activity=activity, success=True, action="synced")

    activity = _record_failed(db, garmin_activity, result.error or "Unknown error")
    return ProcessResult(activity=activity, success=False, action="failed")


def _record_synced(
    db: Database,
    garmin_activity: GarminActivity,
    strava_id: str,
) -> Activity:
    """Record a successfully synced activity."""
    activity = Activity(
        garmin_activity_id=garmin_activity.activity_id,
        activity_type=garmin_activity.activity_type,
        activity_name=garmin_activity.activity_name,
        garmin_start_time=garmin_activity.start_time,
        status=ActivityStatus.SYNCED,
        strava_activity_id=strava_id,
        processed_at=datetime.utcnow().isoformat(),
    )
    db.insert_activity(activity)
    logger.info(
        f"Synced: Garmin {garmin_activity.activity_id} "
        f"({garmin_activity.activity_type}) -> Strava {strava_id}"
    )
    return activity


def _record_skipped(
    db: Database,
    garmin_activity: GarminActivity,
    reason: str,
) -> Activity:
    """Record a skipped activity."""
    activity = Activity(
        garmin_activity_id=garmin_activity.activity_id,
        activity_type=garmin_activity.activity_type,
        activity_name=garmin_activity.activity_name,
        garmin_start_time=garmin_activity.start_time,
        status=ActivityStatus.SKIPPED,
        skip_reason=reason,
        processed_at=datetime.utcnow().isoformat(),
    )
    db.insert_activity(activity)
    logger.info(f"Skipped: {garmin_activity.activity_id} ({reason})")
    return activity


def _record_duplicate(
    db: Database,
    garmin_activity: GarminActivity,
    strava_id: str | None,
) -> Activity:
    """Record a duplicate activity."""
    activity = Activity(
        garmin_activity_id=garmin_activity.activity_id,
        activity_type=garmin_activity.activity_type,
        activity_name=garmin_activity.activity_name,
        garmin_start_time=garmin_activity.start_time,
        status=ActivityStatus.DUPLICATE,
        strava_activity_id=strava_id,
        processed_at=datetime.utcnow().isoformat(),
    )
    db.insert_activity(activity)
    logger.info(f"Duplicate: {garmin_activity.activity_id} (Strava: {strava_id})")
    return activity


def _record_failed(
    db: Database,
    garmin_activity: GarminActivity,
    error: str,
) -> Activity:
    """Record a failed activity."""
    activity = Activity(
        garmin_activity_id=garmin_activity.activity_id,
        activity_type=garmin_activity.activity_type,
        activity_name=garmin_activity.activity_name,
        garmin_start_time=garmin_activity.start_time,
        status=ActivityStatus.FAILED,
        error_message=error,
        processed_at=datetime.utcnow().isoformat(),
    )
    db.insert_activity(activity)
    logger.error(f"Failed: {garmin_activity.activity_id} - {error}")
    return activity
