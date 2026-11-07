"""A test file with a `GUARDS` line runs when a changed file matches it, also with no import of that file (#595)."""

import merge_main


def test_a_changed_js_file_runs_the_test_that_guards_it():
    tests = {"tests/test_lock.py": 'GUARDS = ("userscripts/*", "tests/data/v.json")   # note\nx = 1\n',
             "tests/test_other.py": "import app\n"}
    assert merge_main.test_files(["userscripts/core.js"], ["userscripts/core.js"], tests) == (["tests/test_lock.py"], [])
    assert merge_main.test_files([], ["tests/data/v.json"], tests)[0] == ["tests/test_lock.py"]


def test_a_test_with_no_guards_line_or_no_match_does_not_run():
    tests = {"tests/test_lock.py": 'GUARDS = ("userscripts/*",)\n', "tests/test_x.py": "y = 2\n"}
    assert merge_main.test_files([], ["docs/A.md"], tests) == ([], [])
    assert merge_main.guards("y = 2\n") == []


def test_the_guarded_tests_run_also_when_many_tests_import_the_module():
    many = {f"tests/test_{i}.py": "import app\n" for i in range(40)}
    many["tests/test_lock.py"] = 'GUARDS = ("userscripts/*",)\n'
    run, rest = merge_main.test_files(["app.py", "userscripts/a.user.js"], [], many)
    assert run == ["tests/test_lock.py"] and len(rest) == 40
