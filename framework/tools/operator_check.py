"""The checks of `framework/docs/OPERATOR.md` that need no session tools (#981): quota, ready tickets, CI on main, old PRs,
labels and owner comments without an answer.

The scheduled tasks need the app (claude.ai/code; the repository denies the session tools of
`mcp__claude-code-remote`): `framework/docs/OPERATOR.md` checks them and the runs of `pacer.yml`. This script checks the rest from GitHub and the quota.

    python3 framework/tools/operator_check.py          # one line per check: OK or PROBLEM; exit 1 when a check has a problem

The name is not `operator.py`: `tools/` is on `sys.path` in the tests, and that name hides the standard module.
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_config import CONFIG, ROOT  # noqa: E402

PR_MINUTES = 30          # an agent PR open longer than this waits for a fix or for Automerge (autopilot step 2); a
                         # time, not merged PRs: a stuck PR shows when nothing merges (#2039)
LABELS = os.path.join(ROOT, ".github", "labels.txt")


def ts(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def wanted_labels(text):
    """The label names of `.github/labels.txt` (`name|color|description`, `#` starts a comment)."""
    return [line.split("|", 1)[0].strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def missing_labels(wanted, have):
    """The labels of `labels.txt` that GitHub does not have (the Labels workflow did not run, #980)."""
    have = {h["name"] for h in have}
    return [w for w in wanted if w not in have]


def old_prs(prs, now, minutes=PR_MINUTES):
    """The open agent PRs (branch `claude/*`, `agent/*` or `ccr-*`) older than `minutes`: Automerge merges a green PR in a
    few minutes, so an older one is red, conflicted, on `hold` or waits for a stopped workflow."""
    return [p for p in prs if p["head"]["ref"].startswith(("claude/", "agent/", "ccr-"))
            and ts(p["created_at"]) < now - datetime.timedelta(minutes=minutes)]


def ci_check(name, runs):
    """(ok, text) of the last CI run in `runs` (`actions/workflows/ci.yml/runs`). A cancelled run is not red."""
    if not runs:
        return True, f"{name}: no run"
    r = runs[0]
    ok = r["conclusion"] in ("success", "cancelled", "skipped", None)
    return ok, f"{name}: {r['conclusion'] or r['status']} ({r['head_sha'][:7]}, {r['created_at']})"


def report(checks):
    """The lines of the report and the exit code: 1 when a check has a problem."""
    lines = [f"{'OK     ' if ok else 'PROBLEM'} {name}: {text}" for name, ok, text in checks]
    return lines, int(not all(ok for _, ok, _ in checks))


def account_checks(env, read=None, tasks=("main", "haiku", "deep")):
    """One check per Claude account of the secrets (`pacer.accounts`, #4240): its quota read (`read(token)`; None
    for the first account: the token of the process) and the tasks the pacer can fire for it (a dry run of
    `pacer.has_url`). A failed read is a problem: the pacer gives that account no run."""
    import pacer
    import usage
    read = read or (lambda token: usage.read_usage() if token is None else usage.read_usage(token=token))
    checks = []
    for i, (name, e) in enumerate(pacer.accounts(env)):
        fire = " ".join(t for t in tasks if pacer.has_url(e, t)) or "no task"
        try:
            u = read(None if i == 0 else e.get(pacer.TOKEN))
        except Exception as x:                          # a timeout or a bad token of one account
            u, why = None, f"{type(x).__name__}: {x}"
        else:
            why = "no usage from the CLI"
        text = " · ".join(f"{w} {v[0]:.0%}" for w, v in sorted(u.items())) if u else f"no quota read ({why})"
        checks.append((f"account {name}", bool(u), f"{text} · fires {fire}"))
    return checks


def run_checks(now):
    import dashboard
    import feedback
    import health
    import usage
    checks = []
    try:
        u, t, burn = usage.read_usage(), now.timestamp(), usage.measured_burn() or usage.BURN
        burn7 = usage.measured_burn7() or usage.BURN7                  # the 7-day budget, as --fire (#1695)
        target = usage.target_runs(u, t, burn, burn7=burn7) if u else None
        checks.append(("quota", bool(u), usage.describe(u, t, burn, burn7) if u else "no usage from the CLI"))
    except Exception as e:                                      # no CLI or no subscription
        target = None
        checks.append(("quota", False, f"{type(e).__name__}: {e}"))
    checks += account_checks(dict(os.environ))
    open_all = dashboard.pages("issues?state=open")
    paused = any({dashboard.STATUS, dashboard.PAUSED} <= set(dashboard.labels(i)) for i in open_all)
    checks.append(("paused", not paused, f"label {dashboard.PAUSED} on the status issue" if paused else "no"))
    ready = len(dashboard.candidates(open_all))
    claims = health.active_claims(now)
    checks.append(("runs", True, f"target {target} · claims {claims}"))
    checks.append(("ready tickets", ready > 0, f"{ready}" + " (the next run refills the queue)" * (ready == 0)))
    path = "actions/workflows/ci.yml/runs?branch=" + CONFIG["branch"]
    for name, query in (("CI on main", ""), ("night CI", "&event=schedule")):
        ok, text = ci_check(name, dashboard.api(f"{path}{query}&per_page=1")["workflow_runs"])
        checks.append((name, ok, text.split(": ", 1)[1]))
    old = old_prs(dashboard.api("pulls?state=open&per_page=100"), now)
    checks.append((f"PRs open > {PR_MINUTES} min", not old, " ".join(f"#{p['number']}" for p in old) or "none"))
    with open(LABELS) as f:
        missing = missing_labels(wanted_labels(f.read()), dashboard.pages("labels"))
    checks.append(("labels", not missing, " ".join(missing) or "all of .github/labels.txt"))
    late = feedback.fetch()
    checks.append(("owner comments without an answer", not late,
                   " ".join(f"#{n}" for n in dict.fromkeys(feedback.issue_number(c) for c in late)) or "none"))
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.parse_args(argv)
    lines, code = report(run_checks(datetime.datetime.now(datetime.timezone.utc)))
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
