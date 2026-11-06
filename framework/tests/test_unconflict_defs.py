"""framework/tools/unconflict.py does not keep both sides when both add a function of the same name (#2631)."""
from test_unconflict import BASE, conflict, tool  # BASE: the file of the merge base


def test_two_new_functions_of_the_same_name_stay_a_conflict(tmp_path):
    d = conflict(tmp_path, BASE + "\n\ndef tick(g):\n    g.book()\n",
                 BASE + "\n\ndef tick(g):\n    g.victory()\n")
    r = tool(d)
    assert r.returncode == 1 and "define tick" in r.stdout
    assert "<<<<<<<" in (tmp_path / "t.py").read_text()          # not written


def test_two_new_functions_of_other_names_keep_both(tmp_path):
    d = conflict(tmp_path, BASE + "\n\ndef book(g):\n    pass\n",
                 BASE + "\n\ndef victory(g):\n    pass\n")
    r = tool(d)
    assert r.returncode == 0, r.stdout
    text = (tmp_path / "t.py").read_text()
    assert "def book(g)" in text and "def victory(g)" in text
