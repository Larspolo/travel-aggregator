"""One head of the migrations, named in `migrations/HEAD` (#1818, #2387).

Two PRs that each add a migration with the next number passed CI each alone, and main got two heads after both
merged: "Multiple head revisions are present" stopped all tests and the preview twice. Each migration PR now changes
the one line of `migrations/HEAD`, so two parallel migration PRs have a merge conflict and the second does not merge
until its run gives its migration the next number. No database: Alembic reads only the files.
"""
from pathlib import Path

from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"
GUARDS = ("migrations/*",)   # ship_pr runs this file for these changes, also with --tested (#1328)


def _script():
    return ScriptDirectory(str(MIGRATIONS))


def test_the_migrations_have_one_head():
    heads = _script().get_heads()
    assert len(heads) == 1, (
        f"the migrations have the heads {sorted(heads)}: give the newest migration the next number and set its "
        "`down_revision` to the head of main"
    )


def test_each_file_name_starts_with_its_revision():
    bad = [Path(r.path).name for r in _script().walk_revisions() if not Path(r.path).name.startswith(r.revision + "_")]
    assert not bad, f"rename these files to <revision>_<name>.py: {bad}"


def test_head_file_names_the_head_migration():
    script = _script()
    head = Path(script.get_revision(script.get_current_head()).path).name
    written = (MIGRATIONS / "HEAD").read_text().strip()
    assert written == head, (
        f"migrations/HEAD is {written!r}, but the head migration is {head!r}: write {head!r} into migrations/HEAD "
        "(one line). A merge conflict in this file means that another PR added a migration first: merge main, give "
        "your migration the next number and its `down_revision` the head of main"
    )
