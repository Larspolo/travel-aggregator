"""framework/tools/unconflict.py keeps a conflict with no conflict markers (modify/delete) as a real conflict (#3062)."""
import os
import subprocess
import sys

import pytest

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools", "unconflict.py")


def git(d, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "merge.conflictStyle=diff3",
                           *args], cwd=d, capture_output=True, text=True)


def modify_delete(tmp_path, delete_on_main):
    """A repository in a merge of main into a branch: one side deletes t.py, the other side adds a line to it."""
    d = str(tmp_path)
    git(d, "init", "-q", "-b", "main")
    (tmp_path / "t.py").write_text("x = 1\n")
    git(d, "add", "t.py")
    git(d, "commit", "-qm", "base")
    git(d, "checkout", "-qb", "side")
    for branch in ("main", "side"):
        git(d, "checkout", "-q", branch)
        if (branch == "main") == delete_on_main:
            git(d, "rm", "-q", "t.py")
        else:
            (tmp_path / "t.py").write_text("x = 1\ny = 2\n")
        git(d, "commit", "-qam", branch)
    r = git(d, "merge", "-q", "--no-edit", "main")
    assert r.returncode != 0 and "modify/delete" in r.stdout, r.stdout
    return d


@pytest.mark.parametrize("delete_on_main", [True, False], ids=["main deletes", "branch deletes"])
def test_a_modify_delete_conflict_stays(tmp_path, delete_on_main):
    d = modify_delete(tmp_path, delete_on_main)
    r = subprocess.run([sys.executable, TOOL], cwd=d, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout
    assert "t.py" in r.stdout and "no conflict markers" in r.stdout
    assert git(d, "diff", "--name-only", "--diff-filter=U").stdout.split() == ["t.py"]     # not added
