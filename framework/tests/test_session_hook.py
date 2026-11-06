"""The SessionStart hook runs the specific file and the install command of agent.toml in a cloud session (#4801)."""
import os
import shutil
import subprocess

from conftest import ROOT

HOOK = os.path.join(ROOT, ".claude", "hooks", "session-start.sh")


def run_hook(tmp_path, remote, specific):
    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    (proj / "framework" / "tools").mkdir(parents=True)
    shutil.copy(os.path.join(ROOT, "framework", "tools", "merge_jsonl.py"), proj / "framework" / "tools")
    (proj / "agent.toml").write_text('[commands]\ninstall = "echo install >> log.txt"\n')
    (proj / "scripts" / "cloud-setup.sh").write_text("SETUP_VERSION=1\n")
    if specific:
        (proj / "scripts" / "session-setup.sh").write_text("echo specific >> log.txt\n")
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_ENV_FILE", "AGENT_ACCOUNT")}
    env.update(CLAUDE_PROJECT_DIR=str(proj), CLAUDE_CODE_REMOTE=remote)
    r = subprocess.run(["bash", HOOK], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    log = proj / "log.txt"
    return log.read_text().split() if log.exists() else []


def test_remote_runs_specific_then_install(tmp_path):
    assert run_hook(tmp_path, "true", True) == ["specific", "install"]


def test_remote_without_specific_file(tmp_path):
    assert run_hook(tmp_path, "true", False) == ["install"]


def test_local_session_installs_nothing(tmp_path):
    assert run_hook(tmp_path, "", True) == []
