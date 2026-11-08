"""A loop of pacer.yml that a person started also starts the next run when it ends with no error. The cron of the
repository fires a few times a day or not at all: on 2026-11-06 the loop that the owner started at 09:11 ended its
330 minutes at 14:51 and stopped with exit 1, and no run started for more than 40 minutes. A failed try of a person
still ends at once: the person sees the red run."""
import os
import subprocess

from test_pacer_exit import START, fake_python
from test_pacer_restart import WORKFLOW, calls, commit, loop_script, repo  # noqa: F401 (repo is a fixture)


def by_hand(run, bin_, tmp_path):
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp_path),
           "GITHUB_REPOSITORY": "o/r", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": "Larspolo"}
    return subprocess.run(["bash", "-e", "-c", loop_script()], cwd=run, env=env, capture_output=True, text=True,
                          timeout=60)


def test_a_loop_that_a_person_started_starts_the_next_run_at_its_end(repo, tmp_path):  # noqa: F811
    run, other, bin_, log = repo
    commit(other, WORKFLOW, "new text\n")                        # the loop ends with no error (as at its 330 minutes)
    r = by_hand(run, bin_, tmp_path)
    assert r.returncode == 0, r.stderr
    assert calls(log).count(START) == 1


def test_a_failed_try_of_a_person_starts_no_run(repo, tmp_path):  # noqa: F811
    run, _, bin_, log = repo
    fake_python(bin_, log, switch=0, cycle=1)
    r = by_hand(run, bin_, tmp_path)
    assert r.returncode == 1 and START not in calls(log) and "sleep 600" not in calls(log)
