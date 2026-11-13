"""A call of `ship_pr.py` or `merge_main.py` waits for CI or solves a conflict: it is no verify call, also when its
command has the word pytest (#2780: the CI wait of 12 README runs counted as `verify`, 80 min of `pytest`)."""
import tokens

SHIP = "python3 framework/tools/ship_pr.py 7 --message m.txt --title 'Describe X in the README' --body b.md"


def test_a_chained_ship_call_is_ci():
    cmd = "python3 -m pytest -m readme && " + SHIP
    assert tokens.check(cmd) is None
    assert tokens.phase("Bash", {"command": cmd}) == "ci"


def test_the_word_pytest_in_quoted_text_of_a_ship_call_is_no_check():
    cmd = "printf 'Verified: python3 -m pytest tests/test_a.py\\n' > b.md && " + SHIP
    assert tokens.check(cmd) is None
    assert tokens.phase("Bash", {"command": cmd}) == "ci"


def test_a_merge_main_call_with_pytest_is_conflict():
    cmd = "python3 framework/tools/merge_main.py --push 7 && python3 -m pytest tests/test_a.py"
    assert tokens.check(cmd) is None
    assert tokens.phase("Bash", {"command": cmd}) == "conflict"


def test_a_check_alone_is_still_verify():
    assert tokens.check("python3 -m pytest -m readme") == "pytest"
    assert tokens.check("python3 -m pytest tests/test_a.py") == "pytest files"
    assert tokens.phase("Bash", {"command": "ruff check . && python3 -m pytest tests/test_a.py"}) == "verify"
