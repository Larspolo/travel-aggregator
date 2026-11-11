"""The deny list of `.claude/settings.json` stops the GitHub MCP tools that write around the guards (#2235).

`guard-main.sh`, the `commit-msg` hook (the `Agent-Run:` trailer) and the guard of `ship_pr.py` see only `Bash`. A
commit, branch or merge by an MCP tool passes none of them, so these tools stay denied. A denied tool that a skill or
a hook names is a contradiction: the run reads the instruction and the call fails.
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".claude" / "settings.json"
WRITES = ("create_branch", "create_or_update_file", "delete_file", "push_files", "merge_pull_request",
          "enable_pr_auto_merge", "disable_pr_auto_merge")


def deny():
    return set(json.loads(SETTINGS.read_text())["permissions"]["deny"])


def test_the_mcp_tools_that_commit_branch_or_merge_are_denied():
    missing = [n for n in WRITES if f"mcp__github__{n}" not in deny()]
    assert not missing, f"deny these MCP tools in .claude/settings.json (they pass no guard, #2235): {missing}"


def test_no_skill_or_hook_names_a_denied_tool():
    denied = {d for d in deny() if re.fullmatch(r"mcp__\w+", d)}
    hooks = json.loads(SETTINGS.read_text()).get("hooks", {})
    matchers = " ".join(h.get("matcher", "") for groups in hooks.values() for h in groups)
    places = [(str(p.relative_to(ROOT)), p.read_text()) for p in (ROOT / ".claude" / "skills").rglob("*.md")]
    places.append(("hook matchers", matchers))
    found = [(where, name) for where, text in places for name in sorted(denied)
             if re.search(re.escape(name) + r"\b", text)]
    assert not found, f"a skill or hook names a denied tool: {found}"
