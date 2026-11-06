"""framework/tools/merge_jsonl.py merges the lines of a JSON lines table by name, not by union (#2004)."""
import json
import os
import subprocess
import sys

import merge_jsonl

TOOL = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools", "merge_jsonl.py"))


def line(name, **kw):
    return json.dumps({"name": name, **kw}) + "\n"


BASE = [line("AZTECS", missing=["A"]), line("BRITONS", missing=["A"]), line("CELTS", missing=["A"])]


def git(d, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=d, capture_output=True, text=True)


def merged(tmp_path, ours, theirs):
    """(exit code of git merge, lines of the file): a real git merge with the driver of the hook."""
    d = str(tmp_path)
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "merge.jsonl.driver", f"{sys.executable} {TOOL} %O %A %B")
    open(os.path.join(d, ".gitattributes"), "w").write("*.jsonl merge=jsonl\n")
    path = os.path.join(d, "civs.jsonl")
    for branch, lines in (("main", BASE), ("ours", ours), ("theirs", theirs)):
        if branch != "main":
            git(d, "checkout", "-q", "-b", branch, "main")
        open(path, "w").writelines(lines)
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", branch)
    git(d, "checkout", "-q", "ours")
    rc = git(d, "merge", "-q", "--no-edit", "theirs").returncode
    return rc, open(path).readlines()


def test_changes_of_different_lines_give_one_line_per_name(tmp_path):
    ours = [BASE[0], line("BRITONS", missing=["A", "B"]), BASE[2]]
    theirs = [BASE[0], BASE[1], line("CELTS", missing=[]), line("DUTCH", missing=["C"])]
    rc, lines = merged(tmp_path, ours, theirs)
    assert rc == 0
    assert lines == [BASE[0], ours[1], theirs[2], theirs[3]]


def test_a_key_changed_to_two_values_is_a_conflict(tmp_path):
    ours = [BASE[0], line("BRITONS", missing=["A"], twice=["B"]), BASE[2]]
    theirs = [BASE[0], line("BRITONS", missing=["A"], twice=["C"]), BASE[2]]
    rc, lines = merged(tmp_path, ours, theirs)
    assert rc != 0
    assert lines == [BASE[0], "<<<<<<< ours\n", ours[1], "=======\n", theirs[1], ">>>>>>> theirs\n", BASE[2]]


def test_new_names_of_both_sides_in_the_lists_of_all_lines_merge(tmp_path):
    """#2027 and #2038: the slinger and the Varangian Guard in the "missing" list of each civ line (#2064)."""
    ours = [line(c, missing=["A", "SLINGER"]) for c in ("AZTECS", "BRITONS", "CELTS")]
    theirs = [line(c, missing=["A", "ELITE_VARANGIAN_GUARD", "VARANGIAN_GUARD"]) for c in ("AZTECS", "BRITONS", "CELTS")]
    rc, lines = merged(tmp_path, ours, theirs)
    assert rc == 0
    assert lines == [line(c, missing=["A", "ELITE_VARANGIAN_GUARD", "SLINGER", "VARANGIAN_GUARD"])
                     for c in ("AZTECS", "BRITONS", "CELTS")]


def both(base, ours, theirs):
    """(lines, conflicts) of the merge of one line that both sides changed."""
    return merge_jsonl.merge(*(merge_jsonl.rows_of([x]) for x in (base, ours, theirs)))


def test_different_keys_of_one_line_merge_also_in_a_nested_object():
    """#2022 and #2038: a new key "costs" on one side, a new name in "missing" on the other (#2064)."""
    base = line("MUISCA", cost={"food": 50, "gold": 20}, missing=["A"])
    ours = line("MUISCA", cost={"food": 60, "gold": 20}, missing=["A"], costs=[["ages", "gold", [0.5, 0.5]]])
    theirs = line("MUISCA", cost={"food": 50, "gold": 25}, missing=["A", "B"])
    assert both(base, ours, theirs) == (
        [line("MUISCA", cost={"food": 60, "gold": 25}, missing=["A", "B"], costs=[["ages", "gold", [0.5, 0.5]]])], 0)


def test_a_name_removed_on_one_side_and_added_on_the_other():
    assert both(line("X", missing=["A", "B"]), line("X", missing=["B"]), line("X", missing=["A", "B", "C"])) == (
        [line("X", missing=["B", "C"])], 0)


def test_an_unsorted_list_keeps_the_order_of_ours_and_the_neighbour_of_theirs():
    assert both(line("X", classes=["b", "a"]), line("X", classes=["b", "a", "c"]), line("X", classes=["b", "d", "a"])) == (
        [line("X", classes=["b", "d", "a", "c"])], 0)


def test_a_pair_or_a_number_list_changed_on_both_sides_is_a_conflict():
    for o, a, b in ((["A", "B"], ["A", "C"], ["A", "D"]),          # the pair "upgrade": [OLD, NEW]
                    ([0.5, 0.5], [0.4, 0.5], [0.5, 0.6])):         # a value per age
        assert both(line("X", upgrade=o), line("X", upgrade=a), line("X", upgrade=b))[1] == 1


def test_a_line_new_on_both_sides_or_changed_and_deleted_is_a_conflict():
    assert merge_jsonl.merge({}, *(merge_jsonl.rows_of([line("X", a=n)]) for n in (1, 2)))[1] == 1
    assert merge_jsonl.merge(*(merge_jsonl.rows_of(x) for x in ([line("X", a=1)], [line("X", a=2)], [])))[1] == 1


def test_the_same_change_on_both_sides_and_deletes():
    same = line("BRITONS", missing=[])
    lines, conflicts = merge_jsonl.merge(*(merge_jsonl.rows_of(x) for x in (
        BASE, [BASE[0], same], [same, BASE[2]])))
    assert (lines, conflicts) == ([same], 0)              # AZTECS deleted by theirs, CELTS by ours


def test_new_lines_of_theirs_stay_below_their_neighbour():
    ours = BASE + [line("DUTCH")]
    theirs = [BASE[0], line("ARMENIANS"), BASE[1], BASE[2]]
    lines, conflicts = merge_jsonl.merge(*(merge_jsonl.rows_of(x) for x in (BASE, ours, theirs)))
    assert lines == [BASE[0], theirs[1], BASE[1], BASE[2], ours[3]] and conflicts == 0

