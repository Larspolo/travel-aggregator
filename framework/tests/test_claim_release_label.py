"""framework/tools/claim.py --release removes the label `in-progress`, as the claim adds it (#3234): a released ticket is a
candidate again at once, and no run must take it over as stuck."""
import subprocess

import claim
import dashboard
import pytest


@pytest.fixture
def calls(monkeypatch):
    out = []
    monkeypatch.setattr(dashboard, "api", lambda path, method="GET", data=None: out.append((path, method, data)))
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    return out


def test_a_release_removes_the_label_after_the_release_commit(calls, monkeypatch):
    done = []
    monkeypatch.setattr(claim, "release", lambda number, remote="origin", word="Release": done.append(number) or "claim/7")
    assert claim.main(["7", "--release"]) == 0
    assert done == [7] and calls == [("issues/7/labels/in-progress", "DELETE", None)]


def test_a_failed_label_call_does_not_fail_the_release(monkeypatch, capsys):
    def gone(path, method="GET", data=None):
        raise subprocess.CalledProcessError(1, "gh", "HTTP 404: Label does not exist")
    monkeypatch.setattr(dashboard, "api", gone)
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "release", lambda number, remote="origin", word="Release": "claim/7")
    assert claim.main(["7", "--release"]) == 0
    assert "released claim/7" in capsys.readouterr().out


def test_no_label_call_with_no_own_claim(calls, monkeypatch):
    monkeypatch.setattr(claim, "release", lambda number, remote="origin", word="Release": None)
    assert claim.main(["7", "--release"]) == 0
    assert calls == []


def test_no_label_call_on_a_local_remote(calls, monkeypatch):
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": False)
    monkeypatch.setattr(claim, "release", lambda number, remote="origin", word="Release": "claim/7")
    assert claim.main(["7", "--release"]) == 0
    assert calls == []
