"""CLI commands for Garava."""

from __future__ import annotations

import logging
import os
import stat
import sys
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click

from garava.config import Config, get_config
from garava.database import Database
from garava.garmin.client import GarminAuthError, GarminClient
from garava.models import ActivityStatus
from garava.strava.auth import run_oauth_flow
from garava.strava.client import StravaClient
from garava.sync.core import SyncEngine


def setup_logging(level: str, log_dir: Path | None = None) -> None:
    """Configure logging to stdout and optionally to a rotating file."""
    log_level = getattr(logging, level.upper())
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(log_level)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handler (5 MB, 3 rotations)
    if log_dir is None:
        log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(log_dir, stat.S_IRWXU)
    except OSError:
        pass
    log_file = log_dir / "garava.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    try:
        os.chmod(log_file, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


@click.group()
@click.option("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """Garava: Selective Garmin-to-Strava sync."""
    setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["config"] = get_config()


@cli.command()
@click.pass_context
def setup(ctx: click.Context) -> None:
    """Set up Garmin and Strava authentication."""
    config: Config = ctx.obj["config"]

    # Validate config
    errors = config.validate()
    if errors:
        click.echo("Configuration errors:", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)
        click.echo("\nSet STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET environment variables.")
        sys.exit(1)

    db = Database(config.db_path)
    click.echo(f"Database: {config.db_path}")

    # Garmin setup
    click.echo("\n=== Garmin Connect Setup ===")
    garmin = GarminClient(config.garth_home)

    # Check for existing session
    try:
        garmin.resume_session()
        if garmin.verify_session():
            click.echo("Garmin: Already authenticated (session valid)")
        else:
            raise GarminAuthError("Session invalid")
    except GarminAuthError:
        click.echo("Garmin: Need to authenticate")
        email = click.prompt("Garmin email")
        password = click.prompt("Garmin password", hide_input=True)

        try:
            garmin.login(email, password)
            click.echo("Garmin: Authentication successful!")
        except GarminAuthError as e:
            click.echo(f"Garmin authentication failed: {e}", err=True)
            sys.exit(1)

    # Strava setup
    click.echo("\n=== Strava Setup ===")
    strava = StravaClient(config.strava_client_id, config.strava_client_secret)

    # Check for existing token
    existing_token = db.get_strava_token()
    if existing_token and not existing_token.is_expired():
        click.echo("Strava: Already authenticated (token valid)")
    else:
        click.echo("Strava: Need to authenticate")
        click.echo("Opening browser for Strava authorization...")

        result = run_oauth_flow(strava)

        if result.success and result.token:
            db.save_strava_token(result.token)
            athlete = result.token.athlete_id
            click.echo(f"Strava: Authentication successful! (athlete_id: {athlete})")
        else:
            click.echo(f"Strava authentication failed: {result.error}", err=True)
            sys.exit(1)

    click.echo("\n=== Setup Complete ===")
    click.echo("You can now run 'garava run' to start syncing.")


@cli.command()
@click.option("--once", is_flag=True, help="Run once and exit (no scheduler)")
@click.pass_context
def run(ctx: click.Context, once: bool) -> None:
    """Run the sync service."""
    config: Config = ctx.obj["config"]
    logger = logging.getLogger("garava")

    # Validate config
    errors = config.validate()
    if errors:
        click.echo("Configuration errors:", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)

    # Create sync engine
    engine = SyncEngine.create(config)

    if once:
        # Single run mode
        click.echo("Running single sync cycle...")
        result = engine.run_cycle()
        _print_cycle_result(result.run)
    else:
        # Continuous mode — sync at :00, :15, :30, :45
        click.echo("Starting sync service (schedule: :00, :15, :30, :45)")
        click.echo("Press Ctrl+C to stop")

        try:
            result = engine.run_cycle()
            _print_cycle_result(result.run)

            while True:
                sleep_seconds, next_time = _seconds_until_next_quarter_hour()
                logger.info(f"Next sync at {next_time.strftime('%H:%M')}")
                time.sleep(sleep_seconds)

                result = engine.run_cycle()
                _print_cycle_result(result.run)

        except KeyboardInterrupt:
            click.echo("\nShutting down...")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show sync status and statistics."""
    config: Config = ctx.obj["config"]
    db = Database(config.db_path)

    click.echo("=== Garava Status ===\n")

    # Config
    click.echo(f"Database: {config.db_path}")
    click.echo(f"Blocked types: {', '.join(config.blocked_activity_types)}")
    click.echo("Schedule: quarter-hour (:00, :15, :30, :45)")

    # Stats
    stats = db.get_stats()
    click.echo("\n--- Activity Statistics ---")
    click.echo(f"Total sync runs: {stats.get('total_runs', 0)}")
    click.echo(f"Synced: {stats.get(ActivityStatus.SYNCED.value, 0)}")
    click.echo(f"Skipped: {stats.get(ActivityStatus.SKIPPED.value, 0)}")
    click.echo(f"Failed: {stats.get(ActivityStatus.FAILED.value, 0)}")
    click.echo(f"Duplicates: {stats.get(ActivityStatus.DUPLICATE.value, 0)}")

    # Last run
    last_run = db.get_last_sync_run()
    if last_run:
        click.echo("\n--- Last Sync Run ---")
        click.echo(f"Started: {last_run.started_at}")
        click.echo(f"Completed: {last_run.completed_at or 'In progress'}")
        click.echo(f"Checked: {last_run.activities_checked}")
        click.echo(f"Synced: {last_run.activities_synced}")
        click.echo(f"Skipped: {last_run.activities_skipped}")
        click.echo(f"Failed: {last_run.activities_failed}")
        if last_run.error:
            click.echo(f"Error: {last_run.error}")

    # Failed activities
    failed = db.get_failed_activities()
    if failed:
        click.echo(f"\n--- Failed Activities ({len(failed)}) ---")
        for activity in failed[:5]:
            click.echo(f"  {activity.garmin_activity_id}: {activity.error_message}")
        if len(failed) > 5:
            click.echo(f"  ... and {len(failed) - 5} more")


@cli.command()
@click.option("--limit", default=20, help="Number of activities to show")
@click.pass_context
def history(ctx: click.Context, limit: int) -> None:
    """Show recent activity history."""
    config: Config = ctx.obj["config"]
    db = Database(config.db_path)

    activities = db.get_recent_activities(limit=limit)

    if not activities:
        click.echo("No activities processed yet.")
        return

    click.echo(f"=== Recent Activities (last {len(activities)}) ===\n")

    for activity in activities:
        status_icon = {
            ActivityStatus.SYNCED: "✓",
            ActivityStatus.SKIPPED: "○",
            ActivityStatus.FAILED: "✗",
            ActivityStatus.DUPLICATE: "=",
        }.get(activity.status, "?")

        click.echo(
            f"{status_icon} [{activity.status.value:9}] "
            f"{activity.garmin_activity_id} "
            f"({activity.activity_type}) "
            f"- {activity.activity_name or 'Unnamed'}"
        )

        if activity.status == ActivityStatus.SKIPPED and activity.skip_reason:
            click.echo(f"    Reason: {activity.skip_reason}")
        elif activity.status == ActivityStatus.FAILED and activity.error_message:
            click.echo(f"    Error: {activity.error_message}")
        elif activity.strava_activity_id:
            click.echo(f"    Strava ID: {activity.strava_activity_id}")


def _seconds_until_next_quarter_hour(now: datetime | None = None) -> tuple[float, datetime]:
    """Calculate seconds until the next :00, :15, :30, or :45 mark."""
    if now is None:
        now = datetime.now()
    next_quarter = (now.minute // 15 + 1) * 15
    if next_quarter >= 60:
        next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_time = now.replace(minute=next_quarter, second=0, microsecond=0)
    seconds = max((next_time - now).total_seconds(), 1.0)
    return seconds, next_time


def _print_cycle_result(run) -> None:
    """Print summary of a sync cycle."""
    click.echo(
        f"Cycle complete: "
        f"checked={run.activities_checked}, "
        f"synced={run.activities_synced}, "
        f"skipped={run.activities_skipped}, "
        f"failed={run.activities_failed}"
    )
    if run.error:
        click.echo(f"Error: {run.error}", err=True)


if __name__ == "__main__":
    cli()
