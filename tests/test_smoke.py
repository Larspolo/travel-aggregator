"""A first test, so that pytest finds one (no test: exit 5, CI red)."""
import tomllib


def test_agent_toml_has_the_repository():
    assert "/" in tomllib.load(open("agent.toml", "rb"))["repo"]
