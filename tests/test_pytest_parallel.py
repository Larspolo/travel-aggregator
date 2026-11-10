"""A pytest call with 3 or more test files and no -n runs in xdist workers (#1890: verify calls took 0.40 min)."""

from types import SimpleNamespace

from tests.conftest import parallel_workers

THREE = ["tests/test_a.py", "tests/test_b.py::test_x", "tests/test_c.py"]


def option(**kw):
    o = dict(numprocesses=None, dist="no", collectonly=False, usepdb=False, markexpr="not slow and not readme")
    o.update(kw)
    return SimpleNamespace(**o)


def test_three_files_get_one_worker_each():
    assert parallel_workers(option(), THREE) == 3
    assert parallel_workers(option(), THREE + ["tests/test_d.py", "tests/test_a.py::test_y"]) == 4


def test_one_or_two_files_stay_in_one_process():
    assert parallel_workers(option(), THREE[:2]) is None
    assert parallel_workers(option(), ["tests/test_a.py::test_x", "tests/test_a.py::test_y", "tests/test_a.py"]) is None


def test_an_explicit_option_wins():
    assert parallel_workers(option(numprocesses=0), THREE) is None       # -n 0
    assert parallel_workers(option(numprocesses=4), THREE) is None       # -n auto, after xdist reads it
    assert parallel_workers(option(dist="loadfile"), THREE) is None
    assert parallel_workers(SimpleNamespace(collectonly=False), THREE) is None   # -p no:xdist


def test_no_workers_for_collect_only_pdb_and_slow_tests():
    assert parallel_workers(option(collectonly=True), THREE) is None
    assert parallel_workers(option(usepdb=True), THREE) is None
    assert parallel_workers(option(markexpr="slow"), THREE) is None
    assert parallel_workers(option(markexpr="not slow"), THREE) == 3
