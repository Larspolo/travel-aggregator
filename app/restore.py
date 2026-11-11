"""Restore a dump of `python -m app.backup` (`python -m app.restore FILE`).

It runs `pg_restore --clean --if-exists --single-transaction --no-owner`. One transaction means that a failed restore
leaves the database unchanged. A missing or bad file stops first with exit code 1.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from app.config import get_settings
from app.db import sqlalchemy_url


class RestoreError(RuntimeError):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        raise RestoreError(f"cannot run {cmd[0]}: {exc}") from exc


def restore(url: str, path: Path) -> None:
    """Restore the dump at path into the database. Raise RestoreError on failure; the database stays unchanged."""
    if not path.is_file():
        raise RestoreError(f"the file does not exist: {path}")
    check = _run(["pg_restore", "--list", str(path)])
    if check.returncode != 0:
        raise RestoreError(f"not a valid dump file: {check.stderr.strip()}")
    pg_url = "postgresql://" + sqlalchemy_url(url).split("://", 1)[1]
    result = _run(["pg_restore", "--clean", "--if-exists", "--single-transaction", "--no-owner",
                   "--dbname", pg_url, str(path)])
    if result.returncode != 0:
        raise RestoreError(f"pg_restore failed (exit {result.returncode}): {result.stderr.strip()}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.restore", description="Restore the database from a dump")
    ap.add_argument("file", type=Path, help="a dump file written by python -m app.backup")
    a = ap.parse_args(argv)
    try:
        restore(get_settings().database_url, a.file)
    except RestoreError as exc:
        print(f"ERROR: restore failed: {exc}", file=sys.stderr)
        return 1
    print(f"Restored: {a.file}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
