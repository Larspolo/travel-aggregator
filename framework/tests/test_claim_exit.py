"""framework/tools/claim.py: a git or GitHub error exits 2, not 1 (exit 1 means "another run owns it", #3064)."""
import os
import subprocess
import sys

import claim
import pytest

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools", "claim.py")


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def test_missing_remote_exits_2(tmp_path):
    git("init", "-q", "-b", "run-0", str(tmp_path), cwd=tmp_path)
    git("remote", "add", "origin", str(tmp_path / "missing.git"), cwd=tmp_path)
    r = subprocess.run([sys.executable, TOOL, "7"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "missing.git" in r.stderr


def test_api_error_exits_2(monkeypatch, capsys):
    import dashboard

    def fail(path):
        raise OSError("HTTP 502")
    monkeypatch.setattr(dashboard, "api", fail)
    with pytest.raises(SystemExit) as e:
        claim.api("issues/1")
    assert e.value.code == 2
    assert "HTTP 502" in capsys.readouterr().err


def test_push_error_exits_2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    git("init", "-q", str(tmp_path), cwd=tmp_path)
    with pytest.raises(SystemExit) as e:
        claim.push("0" * 40, "claim/1", str(tmp_path / "missing.git"))
    assert e.value.code == 2
