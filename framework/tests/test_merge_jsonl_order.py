"""framework/tools/merge_jsonl.py keeps a line move of either side: the order of the common names comes from the side that
changed it, and two different moves are a conflict (#3065)."""
import json

import merge_jsonl


def driver(tmp_path, base, ours, theirs):
    """(exit code, names of the result): the driver on three files, as git calls it (%O %A %B)."""
    paths = []
    for side, names in (("base", base), ("ours", ours), ("theirs", theirs)):
        p = tmp_path / f"{side}.jsonl"
        p.write_text("".join(json.dumps({"name": n}) + "\n" for n in names))
        paths.append(str(p))
    rc = merge_jsonl.main(["merge_jsonl.py", *paths])
    return rc, [json.loads(s)["name"] if s.startswith("{") else s.strip() for s in open(paths[1])]


BASE = ["easiest", "hard", "standard"]
MOVED = ["easiest", "standard", "hard"]


def test_a_move_of_theirs_stays_with_a_new_line_of_ours(tmp_path):
    assert driver(tmp_path, BASE, BASE + ["extreme"], MOVED) == (0, ["easiest", "standard", "hard", "extreme"])


def test_a_move_of_ours_stays_with_a_new_line_of_theirs(tmp_path):
    assert driver(tmp_path, BASE, MOVED, BASE + ["extreme"]) == (0, ["easiest", "standard", "hard", "extreme"])


def test_the_same_move_on_both_sides_merges(tmp_path):
    assert driver(tmp_path, BASE, MOVED + ["extreme"], MOVED) == (0, ["easiest", "standard", "hard", "extreme"])


def test_a_move_of_theirs_keeps_a_delete_of_ours(tmp_path):
    assert driver(tmp_path, BASE, ["easiest", "hard"], ["standard", "easiest", "hard"]) == (0, ["easiest", "hard"])


def test_two_different_moves_are_a_conflict(tmp_path):
    rc, out = driver(tmp_path, BASE, MOVED, ["hard", "easiest", "standard"])
    assert rc == 1 and out[0] == "<<<<<<< ours" and out[-1] == ">>>>>>> theirs" and "=======" in out
