"""framework/tools/new_repo.py sets the noreply email before the first commit (#4796)."""
import subprocess

import new_repo

NOREPLY = "11822478+Larspolo@users.noreply.github.com"


def fake(monkeypatch, email):
    """A fake git and gh: the email of `git config user.email` is `email`; no commit exists yet. Returns the gh calls."""
    gh_calls = []

    def run(cmd, **k):
        out = ""
        if cmd[:2] == ["gh", "api"]:
            gh_calls.append(cmd)
            out = "11822478\nLarspolo\n"
        elif cmd[-2:] == ["config", "user.email"]:
            out = email + "\n"
        rc = 1 if "rev-parse" in cmd else 0
        return subprocess.CompletedProcess(cmd, rc, out, "")

    monkeypatch.setattr(new_repo.subprocess, "run", run)
    return gh_calls


def test_a_private_email_is_replaced_by_the_noreply_address_before_the_commit(monkeypatch, tmp_path):
    gh_calls = fake(monkeypatch, "me@private.example")
    calls = [c for c, _ in new_repo.git_calls(str(tmp_path), "main")]
    assert gh_calls
    assert ["git", "-C", str(tmp_path), "config", "user.email", NOREPLY] in calls
    assert ["git", "-C", str(tmp_path), "config", "user.name", "Larspolo"] in calls
    commit = calls.index(["git", "-C", str(tmp_path), "commit", "-q", "-m", "Set up the agent system"])
    assert calls.index(["git", "-C", str(tmp_path), "config", "user.email", NOREPLY]) < commit


def test_a_noreply_email_already_set_costs_no_extra_call(monkeypatch, tmp_path):
    gh_calls = fake(monkeypatch, NOREPLY)
    calls = [c for c, _ in new_repo.git_calls(str(tmp_path), "main")]
    assert gh_calls == []
    assert not any("config" in c for c in calls)
    assert "init" in calls[0] and len(calls) == 3
