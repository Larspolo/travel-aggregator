#!/bin/bash
# PreToolUse hook: block a force push, a history rewrite or a delete of main. The ruleset `Protect main` refuses
# them on GitHub too, but this hook stops the command before it runs (the agents use the owner's account).
# Exit 2 blocks the command and shows the message to the agent.
exec python3 -c '
import json, re, shlex, subprocess, sys
cmd = (json.load(sys.stdin).get("tool_input") or {}).get("command") or ""
MAIN = ("main", "refs/heads/main")
def bad_push(seg):
    try:
        args = shlex.split(seg)
    except ValueError:
        args = seg.split()
    args = args[args.index("push") + 1:]
    force = any(a in ("-f", "--force", "--mirror", "-d", "--delete") or a.startswith(("--force-with-lease", "--force-if-includes"))
                for a in args)
    if "--mirror" in args:
        return True
    specs = [a for a in args if not a.startswith("-")][1:]           # the first plain argument is the remote
    if not specs:                                                    # no refspec: the current branch
        head = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
        return force and head == "main"
    for s in specs:
        target = s.split(":")[-1] if ":" in s else s.lstrip("+")
        if target in MAIN and (force or s.startswith(("+", ":"))):
            return True
    return False
cmd = re.sub(r"<<-?\s*([\x27\x22]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", "", cmd, flags=re.S)   # heredoc bodies are text
for seg in re.split(r"&&|\|\||[;|\n]", cmd):
    if re.match(r"\s*(?:\(\s*)?git\s+(?:-C\s+\S+\s+)?push\b", seg) and bad_push(re.sub(r"^.*?\bgit\s+(?:-C\s+\S+\s+)?", "git ", seg)):
        break
    if re.match(r"\s*gh\s+api\b", seg) and re.search(r"git/refs/heads/main\b", seg) and \
            re.search(r"(-X|--method)\s*(PATCH|DELETE)|force=true", seg, re.I):
        break
else:
    sys.exit(0)
print("Blocked by .claude/hooks/guard-main.sh: no force push, history rewrite or delete of main. "
      "Push to your own branch and open a PR.", file=sys.stderr)
sys.exit(2)
'
