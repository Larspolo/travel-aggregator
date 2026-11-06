"""Each exit of the loop of pacer.yml starts the next run, also a failed command; only the switch stops the loop. A loop
that died stayed dead for hours: the cron of the repository fires a few times a day (2026-10-29 22:31, a moved
[pacing]; 2026-10-30 10:50, a moved tools/pacer.py; both ended with a start by hand)."""
from test_pacer_restart import calls, loop, repo  # noqa: F401 (repo is a fixture)

START = "gh workflow run pacer.yml --repo o/r --ref main"


def fake_python(bin_, log, switch, cycle):
    """python3 that gives `switch` for --switch and `cycle` for the other calls."""
    f = bin_ / "python3"
    f.write_text(f'#!/bin/sh\necho "python3 $*" >> {log}\ncase "$*" in *--switch*) exit {switch};; esac\nexit {cycle}\n')


def test_a_failed_switch_starts_the_next_run_after_one_cycle(repo, tmp_path):  # noqa: F811
    run, _, bin_, log = repo
    fake_python(bin_, log, switch=2, cycle=0)
    r = loop(run, bin_, tmp_path)
    assert r.returncode == 2                                     # red: the owner sees it
    assert calls(log)[-2:] == ["sleep 600", START]


def test_a_failed_cycle_starts_the_next_run_after_one_cycle(repo, tmp_path):  # noqa: F811
    run, _, bin_, log = repo
    fake_python(bin_, log, switch=0, cycle=1)
    r = loop(run, bin_, tmp_path)
    assert r.returncode == 1
    assert calls(log)[-2:] == ["sleep 600", START] and calls(log).count(START) == 1


def test_the_switch_stop_starts_no_run(repo, tmp_path):  # noqa: F811
    run, _, bin_, log = repo
    fake_python(bin_, log, switch=3, cycle=0)
    r = loop(run, bin_, tmp_path)
    assert r.returncode == 0 and START not in calls(log)
