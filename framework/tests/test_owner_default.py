"""An `agent.toml` with only `owners` (no `owner`) works: `owner` is the first login of `owners` (main broke at
b26d79a: `KeyError: 'owner'`)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(ROOT, "framework", "tools")
sys.path.insert(0, TOOLS)

from agent_config import load, login, owners  # noqa: E402

ONLY_OWNERS = """repo = "someone/other"
owners = ["first", "second"]
branch = "trunk"
[status]
issue = 7
label = "bot-status"
paused = "stop"
"""


def test_owner_is_the_first_of_owners(tmp_path):
    (tmp_path / "agent.toml").write_text(ONLY_OWNERS)
    config = load(str(tmp_path / "agent.toml"))
    assert config["owner"] == "first"
    assert owners(config) == ["first", "second"]
    assert login("none", config) == "first"


def test_an_explicit_owner_stays(tmp_path):
    (tmp_path / "agent.toml").write_text(ONLY_OWNERS.replace("branch", 'owner = "second"\nbranch'))
    assert load(str(tmp_path / "agent.toml"))["owner"] == "second"


def test_the_tools_start_with_only_owners(tmp_path):
    (tmp_path / "agent.toml").write_text(ONLY_OWNERS)
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_REPOSITORY"}
    env["AGENT_CONFIG"] = str(tmp_path / "agent.toml")
    out = subprocess.run([sys.executable, "-c", "import feedback, health; print(feedback.OWNER, health.OWNER)"],
                         cwd=TOOLS, env=env, capture_output=True, text=True, check=True).stdout.split()
    assert out == ["first", "first"]
