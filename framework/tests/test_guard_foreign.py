"""framework/tools/claim.py --guard: a branch that carries a commit closing another ticket ships two tickets (#4569)."""
import subprocess
import sys

import pytest
from test_claim import TOOL, run


def commit(d, message):
    run("git", "commit", "-q", "--allow-empty", "-m", message, cwd=d)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A remote with main and a clone on the branch run-1, which claims ticket 1."""
    remote, d = tmp_path / "remote.git", tmp_path / "run"
    run("git", "init", "-q", "--bare", str(remote), cwd=tmp_path)
    run("git", "init", "-q", "-b", "main", str(d), cwd=tmp_path)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        run("git", "config", k, v, cwd=d)
    run("git", "remote", "add", "origin", str(remote), cwd=d)
    commit(d, "base")
    run("git", "push", "-q", "origin", "main", cwd=d)
    run("git", "checkout", "-q", "-b", "run-1", cwd=d)
    assert subprocess.run([sys.executable, TOOL, "1"], cwd=d).returncode == 0
    monkeypatch.chdir(d)
    return d


def guard(d):
    return subprocess.run([sys.executable, TOOL, "1", "--guard"], cwd=d, capture_output=True, text=True)


def test_commit_closing_another_ticket_stops_the_guard(repo):
    commit(repo, "Closes #2")
    p = guard(repo)
    assert p.returncode == 1 and "#2" in p.stdout and "remove them from the branch" in p.stdout


def test_own_commit_and_a_part_commit_pass(repo):
    commit(repo, "Closes #1")
    commit(repo, "Part of #2")
    assert guard(repo).returncode == 0


def test_merged_main_with_another_ticket_passes(repo):
    run("git", "checkout", "-q", "main", cwd=repo)
    commit(repo, "Closes #3")
    run("git", "push", "-q", "origin", "main", cwd=repo)
    run("git", "checkout", "-q", "run-1", cwd=repo)
    run("git", "merge", "-q", "--no-edit", "origin/main", cwd=repo)
    assert guard(repo).returncode == 0
