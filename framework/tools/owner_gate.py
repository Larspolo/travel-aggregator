"""The owner gate of Automerge (#4241): a PR that changes `owners`, `owner` or `[accounts]` of `agent.toml` waits
until a login of `owners` (main's list) approves it. A run never adds a login by itself (decision #4229).

    python3 framework/tools/owner_gate.py PR SHA     # exit 0: the PR may merge; exit 1: it waits for an owner approval

Automerge copies this file and main's `agent.toml` to $RUNNER_TEMP (the job checks out PR branches). `gh api` reads
the PR (env R = owner/name)."""
import base64
import json
import os
import subprocess
import sys

import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_config import load, owners  # noqa: E402

KEYS = ("owner", "owners", "accounts")    # the values that decide who steers the agents


def steering(text):
    """The values of KEYS in an `agent.toml` text ({} for a missing file)."""
    data = tomllib.loads(text) if text else {}
    return {k: data.get(k) for k in KEYS}


def approved(reviews, logins):
    """True when the last review of a login of `logins` is an approval."""
    last = {}
    for r in reviews:
        if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            last[(r.get("user") or {}).get("login")] = r["state"]
    return any(last.get(name) == "APPROVED" for name in logins)


def gh(path):
    r = subprocess.run(["gh", "api", f"repos/{os.environ['R']}/{path}"], capture_output=True, text=True)
    return json.loads(r.stdout or "null") if r.returncode == 0 else None


def toml_at(ref):
    got = gh(f"contents/agent.toml?ref={ref}")
    return base64.b64decode(got["content"]).decode() if got and got.get("content") else ""


def main(argv=None):
    pr, sha = (argv or sys.argv[1:])[:2]
    if steering(toml_at(sha)) == steering(toml_at("main")):
        return 0
    if approved(gh(f"pulls/{pr}/reviews") or [], owners(load())):
        print(f"#{pr}: an owner approved the change of the owners")
        return 0
    print(f"#{pr}: it changes the owners or the accounts of agent.toml: it waits for an owner approval (#4241)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
