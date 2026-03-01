"""Strava gear assignment based on activity rules."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from stravalib.model import Activity

from garava.strava.client import StravaClient

logger = logging.getLogger(__name__)


@dataclass
class GearRule:
    """A rule mapping a condition to a Strava gear ID."""

    condition: str
    gear_id: str


@dataclass
class GearAssignmentResult:
    """Result of a gear assignment pass."""

    checked: int = 0
    updated: int = 0
    already_correct: int = 0
    errors: int = 0


def parse_gear_rules(rules_str: str) -> list[GearRule]:
    """Parse gear rules from config string.

    Format: condition:gear_id[,condition:gear_id,...]
    Example: trainer:b3513943
    """
    if not rules_str.strip():
        return []

    rules = []
    for part in rules_str.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            logger.warning(f"Invalid gear rule format: {part}")
            continue
        condition, gear_id = part.split(":", 1)
        condition = condition.strip()
        gear_id = gear_id.strip()
        if condition and gear_id:
            rules.append(GearRule(condition=condition, gear_id=gear_id))
    return rules


def _matches_rule(activity: Activity, rule: GearRule) -> bool:
    """Check if a Strava activity matches a gear rule condition."""
    if rule.condition == "trainer":
        if not activity.trainer:
            return False
        return str(activity.type) == "Ride"
    logger.debug(f"Unknown gear rule condition: {rule.condition}")
    return False


def apply_gear_rules(
    strava_client: StravaClient,
    rules: list[GearRule],
    after: datetime | None = None,
    limit: int = 50,
) -> GearAssignmentResult:
    """Check recent Strava activities and assign gear based on rules.

    Args:
        strava_client: Authenticated StravaClient
        rules: Parsed gear rules
        after: Only check activities after this time
        limit: Max activities to check

    Returns:
        GearAssignmentResult with counts
    """
    result = GearAssignmentResult()

    try:
        activities = strava_client.client.get_activities(after=after, limit=limit)
    except Exception as e:
        logger.warning(f"Failed to fetch activities for gear assignment: {e}")
        return result

    for activity in activities:
        result.checked += 1

        matched_rule = next((r for r in rules if _matches_rule(activity, r)), None)
        if matched_rule is None:
            continue

        if activity.gear_id == matched_rule.gear_id:
            result.already_correct += 1
            continue

        try:
            strava_client.client.update_activity(
                activity.id, gear_id=matched_rule.gear_id
            )
            result.updated += 1
            logger.info(
                f"Assigned gear {matched_rule.gear_id} to activity "
                f"{activity.id} ({activity.name})"
            )
        except Exception as e:
            result.errors += 1
            logger.warning(
                f"Failed to assign gear to activity {activity.id}: {e}"
            )

    return result
