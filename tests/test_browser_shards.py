"""`pytest --shard K/N` (tests/shard.py, #1062): the 2 jobs `browser` of ci.yml each run one part of the slow tests.
The parts are whole files, they do not overlap, and together they are all the selected tests."""
import subprocess
import sys
from pathlib import Path

import pytest

from tests import shard

ROOT = Path(__file__).resolve().parent.parent


class Item:
    def __init__(self, nodeid):
        self.nodeid = nodeid


def test_the_parts_are_whole_files_and_give_each_test_once():
    items = [Item(f"tests/test_{f}.py::test_{n}") for f, size in zip("abcdefg", (9, 1, 4, 4, 2, 6, 3))
             for n in range(size)]
    parts = [shard.select(items, k, 3)[0] for k in (1, 2, 3)]
    assert sorted(i.nodeid for p in parts for i in p) == sorted(i.nodeid for i in items)
    files = [{i.nodeid.split("::")[0] for i in p} for p in parts]
    assert not (files[0] & files[1] or files[0] & files[2] or files[1] & files[2])
    assert sorted(len(p) for p in parts) == [9, 10, 10]   # 9 | 6+4 | 4+3+2+1


def test_the_split_is_the_same_in_each_job():
    counts = {f"tests/test_{n}.py": n % 5 + 1 for n in range(40)}
    assert shard.parts(counts, 2) == shard.parts(dict(reversed(counts.items())), 2)


@pytest.mark.parametrize("value", ["0/2", "3/2", "1", "a/b", "1/2/3"])
def test_a_wrong_shard_is_an_error(value):
    with pytest.raises(ValueError):
        shard.parse(value)


def test_the_two_parts_of_the_slow_tests_are_all_the_slow_tests():
    def collected(*args):
        out = subprocess.run([sys.executable, "-m", "pytest", "-m", "slow", "--collect-only", "-p", "no:xdist", *args],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return {line for line in out.splitlines() if "::" in line}
    every = collected()
    one, two = collected("--shard", "1/2"), collected("--shard", "2/2")
    assert one and two and not one & two
    assert one | two == every
