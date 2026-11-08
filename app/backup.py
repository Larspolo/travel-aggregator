"""Back up the database before a migration that changes data (run by docker-entrypoint.sh).

A migration marks itself with `changes_data = True` at module level. A missing marker means "no data change".
The step reads the pending revisions with the Alembic API. If one has the marker, it writes `pg_dump --format=custom`
to BACKUP_DIR. `python -m app.backup --now` writes a manual backup at any time. A failed dump gives a non-zero exit code, so the entrypoint stops before any migration.
`python -m app.backup --daily` runs as a service: it writes a `<UTC stamp>-daily.dump` when the newest one is older than
BACKUP_INTERVAL_HOURS (default 24), and retries a failed dump after an hour. A failed dump sends "Backup failed" by the
channel of `app/notify.py` at most once in 24 hours, and the next good dump sends "Backup works again" (#1087).
"""

import argparse
import logging
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
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db import make_engine, make_sessionmaker, sqlalchemy_url

log = logging.getLogger(__name__)
ALERT_KEY = "backup_alert_at"
ALERT_REPEAT = timedelta(hours=24)
BACKUP_MAX_AGE = timedelta(hours=48)  # older: the settings page warns and an ingest sends a message (#1088)


def stale_backup_messages(session, backup_dir: Path, now: datetime) -> list:
    """The "No backup" messages of an ingest (#1088), at most once in ALERT_REPEAT (the key of #1087).

    Messages when the newest backup is older than BACKUP_MAX_AGE, or when BACKUP_DIR has none and the database has
    trips. A missing BACKUP_DIR gives none: then the app runs with no backup service (a run with no Docker).
    """
    from app import notify
    from app.models import Setting, Trip

    newest = newest_backup(backup_dir)
    if newest is None:
        if not backup_dir.is_dir() or session.query(Trip.id).first() is None:
            return []
        text = "No backup yet."
    elif now - newest[0] > BACKUP_MAX_AGE:
        text = f"No backup for {(now - newest[0]).days} days."
    else:
        return []
    row = session.get(Setting, ALERT_KEY)
    if row is not None and now - datetime.fromisoformat(row.value) < ALERT_REPEAT:
        return []
    msgs = notify.alert_messages(session, text.rstrip("."), text, "")
    session.merge(Setting(key=ALERT_KEY, value=now.isoformat()))
    session.commit()
    return msgs


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
DEFAULT_KEEP = 14
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def keep_count() -> int:
    """BACKUP_KEEP: how many daily dumps stay. A value that is not a number of at least 1 gives the default, with a log line."""
    raw = os.environ.get("BACKUP_KEEP", "")
    if not raw:
        return DEFAULT_KEEP
    try:
        n = int(raw)
    except ValueError:
        n = 0
    if n < 1:
        print(f"BACKUP_KEEP={raw!r} is not a number of at least 1: keep {DEFAULT_KEEP} daily dumps", file=sys.stderr)
        return DEFAULT_KEEP
    return n


def rotate_daily(backup_dir: Path, keep: int) -> list[Path]:
    """Delete the `*-daily.dump` files of backup_dir except the newest `keep`. Return the deleted paths."""
    dumps = sorted(backup_dir.glob("*-daily.dump"), key=lambda p: p.name.split("-", 1)[0]) if backup_dir.is_dir() else []
    old = dumps[:-keep] if keep > 0 else dumps
    for path in old:
        path.unlink(missing_ok=True)
    return old


def newest_daily(backup_dir: Path) -> datetime | None:
    """The time in the name of the newest `*-daily.dump` in backup_dir, or None."""
    names = sorted(p.name for p in backup_dir.glob("*-daily.dump")) if backup_dir.is_dir() else []
    if not names:
        return None
    return datetime.strptime(names[-1].split("-", 1)[0], STAMP_FORMAT).replace(tzinfo=UTC)


def newest_backup(backup_dir: Path) -> tuple[datetime, int] | None:
    """The UTC time (from the name) and the size in bytes of the newest `<stamp>-<label>.dump`, or None.

    Other file names do not count. A missing directory gives None.
    """
    best = None
    if backup_dir.is_dir():
        for p in backup_dir.glob("*-*.dump"):
            stamp, label = p.name[:-len(".dump")].split("-", 1)
            try:
                when = datetime.strptime(stamp, STAMP_FORMAT).replace(tzinfo=UTC)
            except ValueError:
                continue
            if label and p.is_file() and (best is None or when > best[0]):
                best = (when, p.stat().st_size)
    return best


def _redact(text: str, url: str) -> str:
    """Remove the database URL and its password from a message text (P5)."""
    secrets = [url, sqlalchemy_url(url)]
    try:
        password = make_url(sqlalchemy_url(url)).password
    except Exception:  # noqa: BLE001
        password = None
    if password:
        secrets.append(str(password))
    for value in sorted(filter(None, secrets), key=len, reverse=True):
        text = text.replace(value, "***")
    return text


def _alert(url: str, now: datetime, error: str | None) -> None:
    """Send "Backup failed" (error) or "Backup works again" (None) when due. A failure only logs a warning."""
    from app import notify
    from app.models import Setting

    engine = make_engine(sqlalchemy_url(url))
    try:
        with make_sessionmaker(engine)() as session:
            row = session.get(Setting, ALERT_KEY)
            if error is not None:
                if row is not None and now - datetime.fromisoformat(row.value) < ALERT_REPEAT:
                    return
                msgs = notify.alert_messages(session, "Backup failed", _redact(error, url), "")
                session.merge(Setting(key=ALERT_KEY, value=now.isoformat()))
            else:
                if row is None:
                    return
                msgs = notify.alert_messages(session, "Backup works again", "The daily backup works again.", "")
                session.delete(row)
            session.commit()
        notify.deliver(msgs)
    except Exception as e:  # noqa: BLE001 (an alert must not stop the backup loop)
        log.warning("backup message not sent: %s", _redact(str(e), url))
    finally:
        engine.dispose()


def daily_step(url: str, backup_dir: Path, interval: timedelta, now: datetime | None = None) -> float:
    """One step of the daily loop: dump when due. Return the seconds until the next step.

    The time of the newest daily dump decides, so a restart writes no extra dump. A failed dump prints an error and
    returns the retry delay of one hour; it does not raise. After a new dump, the older daily dumps beyond BACKUP_KEEP
    are deleted.
    """
    now = now or datetime.now(UTC)
    last = newest_daily(backup_dir)
    if last is None or now - last >= interval:
        try:
            dump(url, backup_dir, "daily")
        except BackupError as exc:
            print(f"ERROR: daily backup failed: {exc}; retry in {DAILY_RETRY_SECONDS} s", file=sys.stderr)
            _alert(url, now, str(exc))
            return float(DAILY_RETRY_SECONDS)
        rotate_daily(backup_dir, keep_count())
        _alert(url, now, None)
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
