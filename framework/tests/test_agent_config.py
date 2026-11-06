"""The project values of the agent system come from agent.toml (#905)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))     # the bootstrap copy has no conftest: its tool tests need it

FAKE = """repo = "someone/other"
owner = "someone"
branch = "trunk"
[status]
issue = 7
label = "bot-status"
paused = "stop"
[commands]
lint = "flake8"
[docs]
learnings = "NOTES.md"
"""


def test_the_tools_read_another_config(tmp_path):
    (tmp_path / "agent.toml").write_text(FAKE)
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_REPOSITORY"}
    env["AGENT_CONFIG"] = str(tmp_path / "agent.toml")
    code = ("import inspect, claim, dashboard, health;"
            "print(dashboard.REPO, dashboard.STATUS, dashboard.PAUSED, sorted(dashboard.SKIP), claim.STATUS,"
            " health.OWNER, health.STATUS, inspect.signature(claim.revived))")
    out = subprocess.run([sys.executable, "-c", code], cwd=os.path.join(ROOT, "framework", "tools"), env=env,
                         capture_output=True, text=True, check=True).stdout.split()
    assert out[:3] == ["someone/other", "bot-status", "stop"]
    assert "'bot-status'," in out and "'agent-status'," not in " ".join(out)
    assert "7" in out and "someone" in out
    assert " ".join(out).endswith("(path='NOTES.md', base='origin/trunk')")


def test_no_tool_skill_or_workflow_names_the_repository():
    """Only agent.toml names it, and .claude/settings.json: permission rules cannot read a file. The copy of the
    owner's dashboard page (tools/dashboard_artifact, #982) is data of this project, not a tool."""
    found = subprocess.run(["git", "grep", "-l", "Larspolo/travel-aggregator", "--", ".claude", "tools", ".github",
                            ":!tools/dashboard_artifact"],
                           cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert found == [".claude/settings.json"]


def test_load_joins_the_system_file(tmp_path):
    import agent_config
    import pytest
    (tmp_path / "a.toml").write_text(FAKE)
    (tmp_path / "s.toml").write_text("[pacing]\nmax_runs = 3\n")
    config = agent_config.load(str(tmp_path / "a.toml"), str(tmp_path / "s.toml"))
    assert config["pacing"] == {"max_runs": 3} and config["status"]["issue"] == 7
    (tmp_path / "s.toml").write_text("[status]\nissue = 3\n")
    with pytest.raises(ValueError):
        agent_config.load(str(tmp_path / "a.toml"), str(tmp_path / "s.toml"))
