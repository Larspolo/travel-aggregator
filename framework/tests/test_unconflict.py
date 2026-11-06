"""framework/tools/unconflict.py solves the merge conflicts in which both sides only add lines (#1864)."""
import os
import subprocess
import sys

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools", "unconflict.py")
BASE = 'T = {"A": 1,\n     "D": 4,\n     "G": 7}\n'


def git(d, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "merge.conflictStyle=diff3",
                           *args], cwd=d, capture_output=True, text=True)


def conflict(tmp_path, ours, theirs):
    """A repository in a merge of `theirs` into `ours` (both changes of BASE in t.py) that git cannot solve."""
    d = str(tmp_path)
    git(d, "init", "-q", "-b", "main")
    (tmp_path / "t.py").write_text(BASE)
    git(d, "add", "t.py")
    git(d, "commit", "-qm", "base")
    git(d, "checkout", "-qb", "side")
    (tmp_path / "t.py").write_text(theirs)
    git(d, "commit", "-qam", "theirs")
    git(d, "checkout", "-q", "main")
    (tmp_path / "t.py").write_text(ours)
    git(d, "commit", "-qam", "ours")
    assert git(d, "merge", "-q", "--no-edit", "side").returncode != 0
    return d


def tool(d):
    return subprocess.run([sys.executable, TOOL], cwd=d, capture_output=True, text=True)


def test_two_new_table_entries_at_one_place_stay_in_order(tmp_path):
    d = conflict(tmp_path, BASE.replace('"D": 4,\n', '"D": 4,\n     "F": 6,\n'),
                 BASE.replace('"D": 4,\n', '"D": 4,\n     "E": 5,\n'))
    r = tool(d)
    assert r.returncode == 0, r.stdout
    text = (tmp_path / "t.py").read_text()
    assert text == 'T = {"A": 1,\n     "D": 4,\n     "E": 5,\n     "F": 6,\n     "G": 7}\n'
    assert git(d, "diff", "--name-only", "--diff-filter=U").stdout == ""      # added to the index


def test_a_change_of_the_same_line_stays_a_conflict(tmp_path):
    d = conflict(tmp_path, BASE.replace('"D": 4', '"D": 5'), BASE.replace('"D": 4', '"D": 6'))
    r = tool(d)
    assert r.returncode == 1 and "same lines" in r.stdout
    assert "<<<<<<<" in (tmp_path / "t.py").read_text()          # not written


def test_the_same_key_on_both_sides_stays_a_conflict(tmp_path):
    d = conflict(tmp_path, BASE.replace('"D": 4,\n', '"D": 4,\n     "E": 5,\n'),
                 BASE.replace('"D": 4,\n', '"D": 4,\n     "E": 6,\n'))
    assert tool(d).returncode == 1


def test_code_blocks_keep_both_sides_and_must_compile(tmp_path):
    base_ok = "x = 1\n"
    d = str(tmp_path)
    git(d, "init", "-q", "-b", "main")
    (tmp_path / "t.py").write_text(base_ok)
    git(d, "add", "t.py")
    git(d, "commit", "-qm", "base")
    git(d, "checkout", "-qb", "side")
    (tmp_path / "t.py").write_text(base_ok + "if x:\n    y = 2\n")
    git(d, "commit", "-qam", "theirs")
    git(d, "checkout", "-q", "main")
    (tmp_path / "t.py").write_text(base_ok + "if x:\n    z = 3\n")
    git(d, "commit", "-qam", "ours")
    git(d, "merge", "-q", "--no-edit", "side")
    r = tool(d)
    assert r.returncode == 0, r.stdout
    assert (tmp_path / "t.py").read_text() == "x = 1\nif x:\n    z = 3\nif x:\n    y = 2\n"
