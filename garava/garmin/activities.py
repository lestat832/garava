"""Garmin activity fetching and FIT file handling."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from garava.garmin.client import GarminClient
from garava.models import GarminActivity

logger = logging.getLogger(__name__)


class FitExtractionError(Exception):
    """Raised when FIT file extraction fails."""


def get_recent_activities(client: GarminClient, limit: int = 20) -> list[GarminActivity]:
    """Fetch recent activities and parse into GarminActivity objects.

    Args:
        client: Authenticated GarminClient
        limit: Maximum number of activities to fetch

    Returns:
        List of GarminActivity objects
    """
    raw_activities = client.get_activities(start=0, limit=limit)
    activities = []

    for raw in raw_activities:
        try:
            activity = GarminActivity.from_api_response(raw)
            activities.append(activity)
        except (KeyError, TypeError) as e:
            keys = list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__
            logger.warning(f"Failed to parse activity: {e}, keys: {keys}")
            continue

    return activities


def download_fit_file(client: GarminClient, activity_id: str) -> bytes:
    """Download and extract the FIT file for an activity.

    Args:
        client: Authenticated GarminClient
        activity_id: Garmin activity ID

    Returns:
        Raw bytes of the extracted FIT file

    Raises:
        FitExtractionError: If FIT file cannot be extracted from ZIP
    """
    # Download the ZIP file
    zip_bytes = client.download_activity_fit(activity_id)

    # Extract the FIT file from the ZIP
    try:
        return extract_fit_from_zip(zip_bytes)
    except Exception as e:
        raise FitExtractionError(f"Failed to extract FIT from ZIP for activity {activity_id}: {e}")


def extract_fit_from_zip(zip_bytes: bytes) -> bytes:
    """Extract FIT file from a ZIP archive.

    Garmin provides activity downloads as ZIP files containing a single FIT file.

    Args:
        zip_bytes: Raw bytes of the ZIP file

    Returns:
        Raw bytes of the extracted FIT file

    Raises:
        FitExtractionError: If no FIT file found or extraction fails
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # Find the FIT file in the archive
            fit_files = [name for name in zf.namelist() if name.lower().endswith(".fit")]

            if not fit_files:
                raise FitExtractionError("No FIT file found in ZIP archive")

            if len(fit_files) > 1:
                logger.warning(f"Multiple FIT files in archive, using first: {fit_files}")

            # Extract and return the first FIT file
            fit_filename = fit_files[0]
            fit_bytes = zf.read(fit_filename)
            logger.debug(f"Extracted FIT file: {fit_filename} ({len(fit_bytes)} bytes)")
            return fit_bytes

    except zipfile.BadZipFile as e:
        raise FitExtractionError(f"Invalid ZIP file: {e}")


def save_fit_file(fit_bytes: bytes, output_path: Path) -> None:
    """Save FIT file bytes to disk (for debugging/backup).

    Args:
        fit_bytes: Raw FIT file bytes
        output_path: Path to save the file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(fit_bytes)
    logger.info(f"Saved FIT file to {output_path}")
