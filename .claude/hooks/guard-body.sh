#!/bin/bash
# PreToolUse hook of the MCP tools that write an issue, a comment or a PR: block a body that is only a file path
# (#4250, #4458: GitHub stores "@/path/t.md" as the text) and a new issue with no spec (#4555, the ticket skill).
# Exit 2 blocks the call and shows the message to the agent.
exec python3 -c '
import json, re, sys
data = json.load(sys.stdin)
args = data.get("tool_input") or {}
body = args.get("body") or ""
first = next((line for line in body.splitlines() if line.strip()), "")
why = None
if re.fullmatch(r"\s*@\S+\s*", first) or re.search(r"(?<![\w.])/tmp/\S", body):
    why = ("the body is a file path, not its text (#4458). Read the file and pass its text, "
           "or use gh api ... -F body=@file.md.")
elif (data.get("tool_name", "").endswith("issue_write") and args.get("method") == "create"
      and not ("## Goal" in body and "## Acceptance criteria" in body)):
    why = "a new issue needs the sections ## Goal and ## Acceptance criteria (.claude/skills/ticket/SKILL.md)."
if why:
    print("Blocked by .claude/hooks/guard-body.sh: " + why, file=sys.stderr)
    sys.exit(2)
'
