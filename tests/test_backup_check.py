"""check_dump(): a dump that reads gives its table count; a broken dump raises BackupError (#1489)."""

import os
import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from app import backup
from app.db import make_engine

PG_BIN = Path("/usr/lib/postgresql/16/bin")


@pytest.fixture
def pg_tools(monkeypatch):
    if not (PG_BIN / "pg_dump").exists() and not shutil.which("pg_dump"):
        pytest.skip("no pg_dump")
    monkeypatch.setenv("PATH", f"{PG_BIN}:" + os.environ["PATH"])


@pytest.fixture
def one_table_dump(pg_tools, empty_database_url, tmp_path):
    engine = make_engine(empty_database_url)
    with engine.begin() as c:
        c.execute(text("CREATE TABLE item (id integer PRIMARY KEY)"))
        c.execute(text("INSERT INTO item (id) VALUES (1)"))
    engine.dispose()
    return backup.dump(empty_database_url, tmp_path / "bk", "check")


def test_check_dump_counts_the_tables_of_a_good_dump(one_table_dump):
    assert backup.check_dump(one_table_dump) >= 1


def test_half_cut_dump_raises_backup_error(one_table_dump, tmp_path):
    data = one_table_dump.read_bytes()
    cut = tmp_path / "cut.dump"
    cut.write_bytes(data[: len(data) // 2])
    with pytest.raises(backup.BackupError) as info:
        backup.check_dump(cut)
    assert str(info.value).startswith("backup check failed")


def test_empty_file_raises_backup_error(tmp_path):
    empty = tmp_path / "empty.dump"
    empty.write_bytes(b"")
    with pytest.raises(backup.BackupError) as info:
        backup.check_dump(empty)
    assert str(info.value).startswith("backup check failed")
