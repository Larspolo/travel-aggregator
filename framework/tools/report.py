"""The run report of autopilot step 8 with one command (#1701): the text, the release bar (`release.py`), the `Usage:`
line of the run start (the release bar only when the project has `release.py`), one `Metrics:` line per ticket, the `Tokens:`, `Calls:` and `Run:` lines (`tokens.py`). `framework/tools/health.py` parses it.

    python3 framework/tools/report.py --usage "$(cat USAGE)" --text "What I did. Next: ..." \\
        --ticket 1701 --size S --result "pr #1770" --setup 2 --checks 1 --checks-min 4 --sinks none \\
        --phases read=8,claim=1,code=18,verify=9,ci=0,conflict=5,report=4 [--ticket ...] [--post]

Repeat the ticket options for each ticket of the run, in the same order. `--minutes` defaults to the sum of the
phases. Without `--phases` a ticket gets the phases that `tokens.py --phases` measures in the transcript. `--post` adds the report to the
branch `metrics` (`runs/`, `metrics_log.post`, 2026-10-29: no comment on the status issue; a comment only when no push
goes through) and sets `last_run` and `runs` of the state comment of the status issue (label `agent-status`), else it
prints the report. Then it gives back the own claim of each reported ticket that no open PR closes (`handoffs`, #5462):
the next run takes the ticket at once, not with a takeover 30 minutes later.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_config  # noqa: E402
import claim  # noqa: E402
import metrics_log  # noqa: E402
from claim import agent_state, utc, with_state  # noqa: E402
from dashboard import FOOTER, STATUS, api, pages  # noqa: E402
from health import PHASES  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def phases(text):
    """{phase: minutes} of `read=8,code=18,...`; a phase that is not named is 0."""
    out = dict.fromkeys(PHASES, 0.0)
    for part in filter(None, text.split(",")):
        k, _, v = part.partition("=")
        if k.strip() not in out:
            raise ValueError(f"unknown phase {k!r}: use {', '.join(PHASES)}")
        out[k.strip()] = float(v)
    return out


def num(x):
    return f"{x:g}"


RESULTS = "merged, pr #N, closed, checked, blocked, needs-human, none"


def result(text):
    """The result of a `Metrics:` line in one of the forms of `RESULTS`, or None. `health.py` counts only these: the
    main lane wrote "PR #N", "pr" and "merged-pending", and 35 of its 43 runs counted as no PR (2026-10-31)."""
    t = " ".join(text.strip().lower().split())
    m = re.fullmatch(r"pr ?#(\d+)", t)
    return f"pr #{m[1]}" if m else t if t in ("merged", "closed", "checked", "blocked", "needs-human", "none") else None


def metrics(ticket, size, result, minutes=None, setup=0, checks=0, checks_min=0, sinks="none", phase="", lane=None,
            source=None):
    """One `Metrics:` line in the format of autopilot step 8."""
    p = phases(phase)
    minutes = sum(p.values()) if minutes is None else minutes
    size = size if size.startswith("size:") else f"size:{size}"
    return (f"Metrics: ticket #{ticket} · {size} · {result} · {num(minutes)} min · setup {num(setup)} min · "
            f"checks {checks} · checks {num(checks_min)} min · time sinks: {sinks or 'none'} · phases "
            + " · ".join(f"{k} {num(v)}" for k, v in p.items()) + (f" · lane {lane}" if lane else "")
            + (f" · source {source}" if source else ""))


SOURCES = ("next", "cycle_start")   # where a run got a ticket after its first (#5308)


def next_failed(numbers):
    """The line of the failed claims of `next:` tickets (`health.next_effect` parses it), or None."""
    return f"Next failed: {' '.join(f'#{n}' for n in numbers)}" if numbers else None


def git_lane():
    """The lane of the run: `git config travel-aggregator.lane` (the Haiku lane sets it, #1727), else None (#1982)."""
    r = subprocess.run(["git", "config", "--get", "travel-aggregator.lane"], capture_output=True, text=True)
    return r.stdout.strip() or None


def git_account():
    """The Claude account of the run (`agent_config.account()`, #4236), else None: the `Run:` line gets no account."""
    return agent_config.account()


def tool(*args):
    """The output of another tool of this directory, without its trailing newline; "" when the project has no such
    tool or it fails (a new project has no `release.py`, #1963)."""
    path = next((p for p in (os.path.join(HERE, args[0]), os.path.join(HERE, "..", "..", "tools", args[0]))
                 if os.path.exists(p)), "")                 # a generic tool, or a tool of the project (#4195)
    if not path:
        return ""
    r = subprocess.run([sys.executable, path, *args[1:]], capture_output=True, text=True)
    return r.stdout.rstrip("\n") if r.returncode == 0 else ""


def measured():
    """{ticket: "read=8,claim=1,..."} of this session (`tokens.py --phases`): the phases of a ticket without `--phases`.
    The key "None" holds the time of a run with no won claim."""
    return {m[1]: m[2] for m in re.finditer(r"^#(\d+|None): (\S+)$", tool("tokens.py", "--phases"), re.M)}


def report(text, usage, lines, release=None, tokens=None, calls=None, run=None, lane=None, account=None):
    """The comment: text, release bar (none when it is empty), `Usage:`, `Metrics:`, `Tokens:`, `Calls:` and `Run:`
    lines, footer. The `Run:` line ends with the lane of the run (`opus` when the run set none, as in `health.lanes`)
    and the account of the run, when it has one (#4236)."""
    release = tool("release.py") if release is None else release
    tokens = (tool("tokens.py").splitlines() or [""])[-1] if tokens is None else tokens
    calls = tool("tokens.py", "--calls-line") if calls is None else calls
    run = tool("tokens.py", "--run-line") if run is None else run
    lane = git_lane() if lane is None else lane
    account = git_account() if account is None else account
    run = run and f"{run} · lane {lane or 'opus'}" + (f" · account {account}" if account else "")
    return "\n".join([text.strip(), "", *([release, ""] if release else []), usage.strip(), *lines, tokens,
                      *([calls] if calls else []), *([run] if run else [])]) + FOOTER


def numbers():
    """All numbers of this session (`tokens.py --json`), or {} when the tool has no transcript."""
    try:
        return json.loads(tool("tokens.py", "--json") or "{}")
    except ValueError:
        return {}


def fields(text, usage, tickets, lane, numbers):
    """The named fields of the run record (`metrics_log.run_record`): the text, the `Usage:` line, one dict per ticket
    (the values of its `Metrics:` line), the lane and all numbers of `tokens.py --json`."""
    return {"session": numbers.get("session"), "branch": numbers.get("branch"), "lane": lane or "opus",
            "text": text.strip(), "usage": usage.strip(), "tickets": tickets, "tokens": numbers}


def counted(body, now=None):
    """The body of the status issue after one more run: `last_run` now, `runs` + 1, the other state keys stay."""
    state = agent_state(body)
    return with_state(body, {**state, "last_run": utc(now), "runs": state.get("runs", 0) + 1})


def handoffs(tickets, claims, pulls, me):
    """The tickets of the report that run `me` still claims ({N: subject of its top claim slot}) while no open PR in
    `pulls` closes them: the run reported and leaves them, so `--post` gives the claims back (a hand-off, #5462). A
    held claim waited 30 minutes for `claim.py 0 --stuck` and a takeover: #5228 and #5413 on 2026-10-31 (a `Part of`
    PR merged, the ticket stayed open). A ticket whose open PR closes it waits for Automerge, which ends its claim."""
    return [n for n in dict.fromkeys(tickets) if (line := claims.get(n)) and not line.startswith("Release")
            and line.split(" ")[3:4] == [me] and not any(claim.closes(n).search(claim.prose(p.get("body"))) for p in pulls)]


def hand_off(tickets):
    """Release the claims of `handoffs` and remove `in-progress`. A failure only prints: the report is posted."""
    try:
        claims = {}
        for n in dict.fromkeys(tickets):
            if found := claim.refs(n):
                claims[n] = claim.subject(claim.slot(n, max(found)))
        for n in handoffs(tickets, claims, pages("pulls?state=open"), claim.who()):
            if claim.release(n):
                claim.stop(n)
                print(f"released #{n}: the run reported it and no open PR closes it (a hand-off, #5462)")
    except (Exception, SystemExit) as e:                # claim.release exits when another run took the ticket over
        print(f"no hand-off: {e}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--text", required=True, help="what the run did and what is next")
    ap.add_argument("--usage", help="the Usage: line of the run start (usage.py --sample); default: a new sample")
    for name, kind in (("ticket", int), ("size", str), ("result", str), ("minutes", float), ("setup", float),
                       ("checks", int), ("checks-min", float), ("sinks", str), ("phases", str), ("lane", str),
                       ("source", str), ("next-failed", int)):
        ap.add_argument(f"--{name}", type=kind, action="append", default=[])
    ap.add_argument("--post", action="store_true", help="comment the report on the status issue")
    a = ap.parse_args(argv)
    n = len(a.ticket)
    for name in ("size", "result"):
        if len(getattr(a, name)) != n:
            ap.error(f"give --{name} once for each --ticket")
    bad = [r for r in a.result if result(r) is None]
    if bad:
        ap.error(f"--result {bad[0]!r}: give one of {RESULTS} (the PR number of an open PR)")
    a.result = [result(r) for r in a.result]
    if len(a.source) > n or any(x not in SOURCES for x in a.source):
        ap.error(f"give --source for each ticket after the first of the run, in order: one of {SOURCES}")

    def at(values, i, default):
        return values[i] if i < len(values) else default

    lane, nums = git_lane(), numbers()
    got = measured() if len(a.phases) < n else {}
    setup = round(nums.get("setup") or 0)               # measured: the runs need no `date` call (2026-10-29)
    own = lambda t: got.get(str(t)) or (got.get("None", "") if n == 1 else "")    # measured, not guessed (2026-10-28)
    tickets = [dict(ticket=t, size=a.size[i], result=a.result[i], minutes=at(a.minutes, i, None), setup=at(a.setup, i, setup if i == 0 else 0),
                    checks=at(a.checks, i, 0), checks_min=at(a.checks_min, i, 0), sinks=at(a.sinks, i, "none"),
                    phases=at(a.phases, i, own(t)), lane=at(a.lane, i, lane),
                    source=at(a.source, i, None)) for i, t in enumerate(a.ticket)]
    lines = [metrics(d["ticket"], d["size"], d["result"], d["minutes"], d["setup"], d["checks"], d["checks_min"],
                     d["sinks"], d["phases"], d["lane"], d["source"]) for d in tickets]
    usage = a.usage or (tool("usage.py", "--sample").splitlines() or [""])[-1]
    lines += [x for x in [next_failed(a.next_failed)] if x]
    body = report(a.text, usage, lines)
    if not a.post:
        print(body)
        return 0
    for d in tickets:
        d["phases"] = phases(d["phases"])
        d["minutes"] = sum(d["phases"].values()) if d["minutes"] is None else d["minutes"]
        if d["source"] is None:                                 # the record names only a later ticket's source
            del d["source"]
    path = metrics_log.post(metrics_log.run_record(body, fields(a.text, usage, tickets, lane, nums)))
    status = next(i for i in pages(f"issues?state=open&labels={STATUS}") if "pull_request" not in i)
    if path:
        print(f"{path} on the branch {metrics_log.BRANCH}")
    else:                                                       # no push went through: the old way, no report lost
        print(api(f"issues/{status['number']}/comments", "POST", {"body": body})["html_url"])
    fresh = api(f"issues/{status['number']}")["body"]          # other runs change the body too: read it just before
    api(f"issues/{status['number']}", "PATCH", {"body": counted(fresh)})
    hand_off(a.ticket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
