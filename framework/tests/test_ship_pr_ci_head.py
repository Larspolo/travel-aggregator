"""ship_pr.py --ci waits for the pushed head when the PR head of GitHub is stale (#2338)."""
import subprocess

import ship_pr as ship


def run(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commits(tmp_path, monkeypatch):
    run("init", "-q", cwd=tmp_path)
    shas = []
    for k in range(3):
        run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", str(k), cwd=tmp_path)
        shas.append(run("rev-parse", "HEAD", cwd=tmp_path))
    monkeypatch.chdir(tmp_path)
    return shas


def test_a_stale_github_head_waits_for_the_pushed_head(tmp_path, monkeypatch):
    old, _, new = commits(tmp_path, monkeypatch)
    run("update-ref", "refs/remotes/origin/b", new, cwd=tmp_path)
    assert ship.ci_head(old, "b") == new


def test_a_newer_github_head_stays(tmp_path, monkeypatch):
    _, mid, new = commits(tmp_path, monkeypatch)
    run("update-ref", "refs/remotes/origin/b", mid, cwd=tmp_path)
    assert ship.ci_head(new, "b") == new
    assert ship.ci_head(mid, "b") == mid
    assert ship.ci_head(new, "none") == new
