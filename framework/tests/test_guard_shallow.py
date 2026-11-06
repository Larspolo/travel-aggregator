"""The guard deepens a shallow clone before it looks for foreign commits (#4604)."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import claim  # noqa: E402


def run(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


def commit(cwd, msg):
    run(cwd, "commit", "--allow-empty", "-m", msg)


def test_a_shallow_clone_shows_no_commit_of_main(tmp_path, monkeypatch):
    up = tmp_path / "up"
    up.mkdir()
    run(up, "init", "-q", "-b", "main")
    commit(up, "start")
    run(up, "checkout", "-q", "-b", "work")
    commit(up, "Do the work\n\nCloses #1")
    run(up, "checkout", "-q", "main")
    commit(up, "Old main work\n\nCloses #10")
    run(up, "checkout", "-q", "work")
    run(up, "merge", "-q", "--no-edit", "main")
    run(up, "checkout", "-q", "main")
    for k in range(5):
        commit(up, f"New main work\n\nCloses #{20 + k}")
    clone = tmp_path / "clone"
    run(tmp_path, "clone", "-q", "--depth", "2", "--no-single-branch", up.as_uri(), str(clone))
    run(clone, "checkout", "-q", "work")
    monkeypatch.chdir(clone)
    assert claim.foreign(1) == []
    commit(clone, "Other ticket\n\nCloses #7")
    assert [m for m, _ in claim.foreign(1)] == [7]
