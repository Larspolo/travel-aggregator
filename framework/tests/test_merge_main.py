"""framework/tools/merge_main.py merges main in one call and solves the hunks that only add lines (owner, 2026-10-28)."""
import os
import subprocess
import sys

import merge_main

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools", "merge_main.py")
BASE = 'T = {"A": 1,\n     "D": 4,\n     "G": 7}\nLIMIT = 1\n'


def git(d, *args):
    return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True)


def repo(tmp_path, ours, theirs):
    """A clone on branch `side` (t.py = ours) whose origin/main has t.py = theirs, both changed from BASE."""
    origin, work = str(tmp_path / "origin.git"), str(tmp_path / "work")
    git(str(tmp_path), "init", "-q", "--bare", "-b", "main", origin)
    git(str(tmp_path), "clone", "-q", origin, work)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git(work, "config", k, v)
    (tmp_path / "work" / "t.py").write_text(BASE)
    git(work, "add", "t.py")
    git(work, "commit", "-qm", "base")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "checkout", "-qb", "side")
    (tmp_path / "work" / "t.py").write_text(ours)
    git(work, "commit", "-qam", "ours")
    git(work, "checkout", "-q", "main")
    (tmp_path / "work" / "t.py").write_text(theirs)
    git(work, "commit", "-qam", "theirs")
    git(work, "push", "-q", "origin", "main")
    git(work, "checkout", "-q", "side")
    return work


def tool(d, *args):
    return subprocess.run([sys.executable, TOOL, "--no-test", *args], cwd=d, capture_output=True, text=True)


def parents(d):
    return len(git(d, "log", "-1", "--format=%P").stdout.split())


def test_two_new_entries_merge_in_one_call(tmp_path):
    d = repo(tmp_path, BASE.replace('"D": 4,\n', '"D": 4,\n     "E": 5,\n'),
             BASE.replace('"D": 4,\n', '"D": 4,\n     "F": 6,\n'))
    r = tool(d)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"E": 5,\n     "F": 6,' in (tmp_path / "work" / "t.py").read_text() and parents(d) == 2


def test_a_real_conflict_stays_and_the_rest_is_solved(tmp_path):
    ours = BASE.replace('"D": 4,\n', '"D": 4,\n     "E": 5,\n').replace("LIMIT = 1", "LIMIT = 2")
    theirs = BASE.replace('"D": 4,\n', '"D": 4,\n     "F": 6,\n').replace("LIMIT = 1", "LIMIT = 3")
    d = repo(tmp_path, ours, theirs)
    r = tool(d)
    text = (tmp_path / "work" / "t.py").read_text()
    assert r.returncode == 1 and "t.py:6: both sides change the same lines" in r.stdout and "LIMIT = 3" in r.stdout
    assert '"E": 5,\n     "F": 6,' in text and text.count("<<<<<<<") == 1    # the table hunk is solved
    (tmp_path / "work" / "t.py").write_text(text.split("<<<<<<<")[0] + "LIMIT = 3\n")
    git(d, "add", "t.py")
    r = tool(d)                                                                 # finishes the merge
    assert r.returncode == 0 and "merge committed" in r.stdout and parents(d) == 2


def test_the_tests_of_a_merge():
    tests = {"tests/test_a.py": "import scenario\n", "tests/test_b.py": "from game import train\n",
             "tests/test_c.py": "import app\n", "tests/test_mine.py": "x = 1\n"}
    run, rest = merge_main.test_files(["game/scenario.py", "docs/X.md"], ["tests/test_mine.py", "app.py"], tests)
    assert run == ["tests/test_mine.py", "tests/test_a.py"] and rest == []
    many = {f"tests/test_{i}.py": "import app\n" for i in range(40)}
    assert merge_main.test_files(["app.py"], [], many) == ([], sorted(many))     # CI runs them
