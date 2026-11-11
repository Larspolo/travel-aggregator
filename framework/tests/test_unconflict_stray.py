"""framework/tools/unconflict.py keeps a conflict when two sides add one new module (a second docstring or import, #224)."""
from test_unconflict import git, tool


def merge_of_two_new_files(tmp_path, ours, theirs):
    """A repository in a merge in which both sides add t.py to an empty base (git cannot merge it)."""
    d = str(tmp_path)
    git(d, "init", "-q", "-b", "main")
    (tmp_path / "t.py").write_text("")
    git(d, "add", "t.py")
    git(d, "commit", "-qm", "base")
    git(d, "checkout", "-qb", "side")
    (tmp_path / "t.py").write_text(theirs)
    git(d, "commit", "-qam", "theirs")
    git(d, "checkout", "-q", "main")
    (tmp_path / "t.py").write_text(ours)
    git(d, "commit", "-qam", "ours")
    git(d, "merge", "side")
    return d


RISK = '"""Risk extras."""\nimport math\n\n\ndef risk(x):\n    return math.sqrt(x)\n'
OTHER = '"""Other module."""\nimport os\n\n\ndef sep(x):\n    return os.sep\n'


def test_two_new_modules_in_one_file_stay_a_conflict(tmp_path):
    d = merge_of_two_new_files(tmp_path, RISK, OTHER)
    r = tool(d)
    assert r.returncode == 1, r.stdout
    assert "t.py" in r.stdout and "second docstring or an import" in r.stdout
    assert "<<<<<<<" in (tmp_path / "t.py").read_text()          # not written


def test_two_new_functions_at_the_end_of_one_module_still_merge(tmp_path):
    d = merge_of_two_new_files(tmp_path, "def book(g):\n    pass\n", "def victory(g):\n    pass\n")
    r = tool(d)
    assert r.returncode == 0, r.stdout
    text = (tmp_path / "t.py").read_text()
    assert "def book(g)" in text and "def victory(g)" in text
