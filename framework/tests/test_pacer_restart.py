"""The loop of pacer.yml starts a new run when main changes pacer.yml: GitHub reads the text of a workflow once, at the
start of the run. On 2026-10-30 a PR moved tools/pacer.py to framework/tools/pacer.py, the live loop then called the
lost path and stopped with no next run."""
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/pacer.yml"
STEP = "- name: Start the runs every 10 minutes"


def loop_script():
    """The `run: |` text of the loop step of pacer.yml."""
    lines = (ROOT / WORKFLOW).read_text().splitlines()
    i = next(n for n, x in enumerate(lines) if x.strip() == STEP)
    i = next(n for n in range(i, len(lines)) if lines[n].strip() == "run: |")
    indent = len(lines[i]) - len(lines[i].lstrip())
    body = []
    for x in lines[i + 1:]:
        if x.strip() and len(x) - len(x.lstrip()) <= indent:
            break
        body.append(x)
    return textwrap.dedent("\n".join(body))


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def commit(d, path, text):
    p = d / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    git("add", "-A", cwd=d)
    git("commit", "-q", "-m", f"change {path}", cwd=d)
    git("push", "-q", "origin", "HEAD:main", cwd=d)


@pytest.fixture
def repo(tmp_path):
    """(the checkout of the run, a second clone that changes main, the bin directory with fake gh, python3, sleep)."""
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    run, other = tmp_path / "run", tmp_path / "other"
    for d in (run, other):
        git("clone", "-q", f"file://{remote}", str(d), cwd=tmp_path)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            git("config", k, v, cwd=d)
    commit(run, WORKFLOW, "old text\n")
    git("pull", "-q", "origin", "main", cwd=other)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "calls"
    for name, code in (("gh", "0"), ("sleep", "0"), ("python3", '$(case "$*" in (*--switch*) echo 3;; (*) echo 0;; esac)')):
        f = bin_ / name
        f.write_text(f'#!/bin/sh\necho "{name} $*" >> {log}\nexit {code}\n')
        f.chmod(0o755)
    return run, other, bin_, log


def loop(run, bin_, tmp_path):
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp_path),
           "GITHUB_REPOSITORY": "o/r"}
    return subprocess.run(["bash", "-e", "-c", loop_script()], cwd=run, env=env, capture_output=True, text=True,
                          timeout=60)


def calls(log):
    return log.read_text().splitlines() if log.exists() else []


def test_a_new_pacer_yml_on_main_starts_a_new_run_before_a_call_of_the_old_text(repo, tmp_path):
    run, other, bin_, log = repo
    commit(other, WORKFLOW, "new text\n")
    r = loop(run, bin_, tmp_path)
    assert r.returncode == 0, r.stderr
    assert [c for c in calls(log) if not c.startswith("sleep")] == ["gh workflow run pacer.yml --repo o/r --ref main"]


def test_another_change_on_main_keeps_the_loop(repo, tmp_path):
    run, other, bin_, log = repo
    commit(other, "README.md", "x\n")
    r = loop(run, bin_, tmp_path)
    assert r.returncode == 0, r.stderr                           # the fake switch says "not workflow": a quiet stop
    assert [c.split()[0] for c in calls(log)] == ["python3"] and "--switch" in calls(log)[0]
