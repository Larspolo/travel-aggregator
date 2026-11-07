"""Back up the database before a migration that changes data (run by docker-entrypoint.sh).

A migration marks itself with `changes_data = True` at module level. A missing marker means "no data change".
The step reads the pending revisions with the Alembic API. If one has the marker, it writes `pg_dump --format=custom`
to BACKUP_DIR. `python -m app.backup --now` writes a manual backup at any time. A failed dump gives a non-zero exit code, so the entrypoint stops before any migration.
`python -m app.backup --daily` runs as a service: it writes a `<UTC stamp>-daily.dump` when the newest one is older than
BACKUP_INTERVAL_HOURS (default 24), and retries a failed dump after an hour.
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from app.config import get_settings
from app.db import sqlalchemy_url


class BackupError(RuntimeError):
    pass


def pending_data_revisions(cfg: Config, url: str) -> list[str]:
    """The ids of the pending revisions that have `changes_data = True`, oldest first."""
    script = ScriptDirectory.from_config(cfg)
    engine = create_engine(sqlalchemy_url(url))
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_heads()
    finally:
        engine.dispose()
    found = []
    for rev in script.iterate_revisions("heads", current or "base", implicit_base=True):
        if rev.revision in current:
            continue
        if getattr(rev.module, "changes_data", False) is True:
            found.append(rev.revision)
    return list(reversed(found))


def dump(url: str, backup_dir: Path, label: str) -> Path:
    """Write `<UTC stamp>-<label>.dump` to backup_dir with pg_dump. Return its path. Raise BackupError on failure."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{stamp}-{label}.dump"
    pg_url = "postgresql://" + sqlalchemy_url(url).split("://", 1)[1]
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["pg_dump", "--format=custom", "--file", str(target), "--dbname", pg_url],
            capture_output=True, text=True,
        )
    except OSError as exc:
        raise BackupError(f"cannot run pg_dump: {exc}") from exc
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed (exit {result.returncode}): {result.stderr.strip()}")
    return target


def backup_if_needed(url: str, backup_dir: Path, cfg: Config | None = None) -> Path | None:
    """Write a dump when a pending revision changes data. Return its path, or None. Raise BackupError on failure."""
    cfg = cfg or Config("alembic.ini")
    revisions = pending_data_revisions(cfg, url)
    if not revisions:
        return None
    return dump(url, backup_dir, revisions[-1])


DAILY_RETRY_SECONDS = 3600
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def newest_daily(backup_dir: Path) -> datetime | None:
    """The time in the name of the newest `*-daily.dump` in backup_dir, or None."""
    names = sorted(p.name for p in backup_dir.glob("*-daily.dump")) if backup_dir.is_dir() else []
    if not names:
        return None
    return datetime.strptime(names[-1].split("-", 1)[0], STAMP_FORMAT).replace(tzinfo=UTC)


def daily_step(url: str, backup_dir: Path, interval: timedelta, now: datetime | None = None) -> float:
    """One step of the daily loop: dump when due. Return the seconds until the next step.

    The time of the newest daily dump decides, so a restart writes no extra dump. A failed dump prints an error and
    returns the retry delay of one hour; it does not raise.
    """
    now = now or datetime.now(UTC)
    last = newest_daily(backup_dir)
    if last is None or now - last >= interval:
        try:
            dump(url, backup_dir, "daily")
        except BackupError as exc:
            print(f"ERROR: daily backup failed: {exc}; retry in {DAILY_RETRY_SECONDS} s", file=sys.stderr)
            return float(DAILY_RETRY_SECONDS)
        return interval.total_seconds()
    return (last + interval - now).total_seconds()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.backup", description="Back up the database")
    ap.add_argument("--now", action="store_true", help="write a backup now (<UTC stamp>-manual.dump) and print its path")
    ap.add_argument("--daily", action="store_true", help="loop: a daily backup each BACKUP_INTERVAL_HOURS (default 24)")
    a = ap.parse_args([] if argv is None else argv)
    url = get_settings().database_url
    backup_dir = Path(os.environ.get("BACKUP_DIR", "/backups"))
    if a.daily:
        interval = timedelta(hours=float(os.environ.get("BACKUP_INTERVAL_HOURS", "24")))
        while True:
            time.sleep(daily_step(url, backup_dir, interval))
    if a.now:
        try:
            target = dump(url, backup_dir, "manual")
        except BackupError as exc:
            print(f"ERROR: backup failed: {exc}", file=sys.stderr)
            return 1
        print(target)
        return 0
    try:
        target = backup_if_needed(url, backup_dir)
    except BackupError as exc:
        print(f"ERROR: backup before migration failed, migration not started: {exc}", file=sys.stderr)
        return 1
    if target:
        print(f"Backup written: {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
