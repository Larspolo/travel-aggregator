"""The pacer as a script (#3193): start the autopilot runs that the quota target misses, with no Claude session.

The old pacer session kept an old "cap of 4 per cycle" in its context and fired 4 Haiku runs for H = 8
(2026-10-28, #3147; removed in #3427). A script has no memory: `.github/workflows/pacer.yml` runs it every 10 minutes
while the key `pacer` in `[pacing]` of `steering/system/system.toml` is "workflow" (any other value stops the loop: a PR changes it).

    python3 framework/tools/pacer.py              # compute K and the lane runs (`usage.fire`), then start them
    python3 framework/tools/pacer.py --dry-run    # print the calls, send nothing
    python3 framework/tools/pacer.py --log F      # also add the record of the cycle to F, one JSON line (`record`)
    python3 framework/tools/pacer.py --switch     # exit 0 while the loop runs, 3 to stop it, 1 when the key is missing (`switch`)
    python3 framework/tools/pacer.py --secrets    # the JSON list of the secret names that pacer.yml reads (`secret_names`)

Each scheduled task has an API trigger (a URL and a token, made in the Claude app). The environment gives them:
`PACER_URL_MAIN` and `PACER_TOKEN_MAIN` for the main task, `PACER_URL_<LANE>` and `PACER_TOKEN_<LANE>` for each lane of
`weights` in `[pacing]` of `steering/system/system.toml`. A lane without a URL gets no runs: its tickets wait.
Several Claude accounts (#4237, `accounts`): another account NAME has `CLAUDE_CODE_OAUTH_TOKEN_<NAME>`,
`PACER_URL_<NAME>_<TASK>` and `PACER_TOKEN_<NAME>_<TASK>` (`secret_names`: pacer.yml reads them by name). Each account
gets its own quota read, target and claims (`account_targets`); the global limits of `usage.fire` cap the sum of the
missing runs, and `assign` gives each run to the account with the most missing runs. With one account the plan is the
same as before.
Exit 1 when a call fails: the workflow run goes red. HTTP 429 is no failure: a task takes at most 30 starts per hour,
an account 100 API starts per hour (the docs of the scheduled tasks, "Usage and limits"); the next cycle starts the
runs that the target still misses. No retry: each call that succeeds starts a run, so a retry can start two. When a
lane task is at its limit, the main task gets the blocked runs, up to the main runs of a new plan without that lane:
the Haiku lane got all 8 runs of each cycle, 48 an hour (2026-10-28).

The pacer also does steps 1 to 5 of the autopilot skill for the runs that it starts (owner, 2026-10-29: the runs
must do as little as possible). For each run it takes the next candidate of its lane in the pick order of
`dashboard.candidates`, claims it for the run (`claim.py` with the name `pacer-r<hex>`: the run has no branch yet),
and sends a brief in the `text` of the call: the ticket, its comments, the code places (`ticket_context.context`) and
the `Usage:` line of the report. The run adopts the claim with its first beat (`claim.py N --adopt NAME`) and starts at
step 6 (the `scheduled` skill). The brief is data in a `<routine-fire-payload>` block: the run takes only its
`ticket` and `claim` lines, and the claim ref in git proves them. The fire queues the brief as the second turn of a new
session, after the stored prompt: the first turn ends at once when it finds it (`tokens.py --queued`, #4550). A run with no candidate (a refill run), and all runs
while the flow brake is on or the last CI run on main is red, get no brief, and so does one main run while owner
comments wait (`feedback.py`: a briefed run skips step 3, and the answers waited, #294): they do steps 1 to 5 themselves. When a
call fails, the pacer releases the claim of its run.
A brief also names up to 2 next tickets (`next:`, #5076) beyond the runs of the cycle, related ones first: the run
claims one itself after its PR, so it skips a fresh start. The pacer does not claim them (the claims stay 1 per run).
A stuck ticket (`claim.py 0 --stuck`: its run stopped) comes before the candidates (autopilot step 2): the pacer takes
it over for one run (`claim.py N --takeover` with the run name) and adds a `takeover:` line with the branch of its PR.
Runs with no brief raced for the same stuck PRs, and each lost race cost a cycle start (#4356).
A stuck ticket whose PR only waits for its quick CI or for Automerge gets no takeover (`ci_wait`, #4932); a green
one starts the Automerge sweep: 10 of 14 takeovers "after the report" closed by the merge 0 to 18 minutes later.
The jobs of a `full` CI dispatch on the head do not count (`pr_checks`, as the sweep of `automerge.yml`, #5462).
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage  # noqa: E402

BETA = "experimental-cc-routine-2026-04-01"   # the header of the API trigger of a scheduled task


def calls(k, runs, env):
    """[(task, url, token)]: one call per run. The lane runs go to their lane task, the rest of K to the main task."""
    out = []
    for task, n in [*runs.items(), ("main", k - sum(runs.values()))]:
        url, token = env.get(f"PACER_URL_{task.upper()}"), env.get(f"PACER_TOKEN_{task.upper()}")
        out += [(task, url, token)] * (n if url and token else 0)
    return out


TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"   # the secret of the quota read of an account (`usage.read_usage`)


SLOTS = 35   # the `SECRET_<i>` lines of pacer.yml: the first account and 4 more, each with 3 tasks


def secret_names(config=None):
    """The names of the secrets that pacer.yml reads, padded with "" to `SLOTS` (`--secrets`): the first account and
    each other table of `[accounts]`, for the main task and each lane of `weights` in `[pacing]`. pacer.yml reads them
    one by one, not as `toJSON(secrets)`: GitHub held runs that read all secrets as "may be malicious" (2026-10-30)."""
    config = usage.CONFIG if config is None else config
    tasks = ["MAIN", *(lane.upper() for lane in config["pacing"]["weights"])]
    names = []
    for i, account in enumerate(config.get("accounts") or [None]):
        tag = "" if i == 0 else f"_{account.upper()}"
        names += [f"{TOKEN}{tag}", *(f"PACER_{kind}{tag}_{t}" for t in tasks for kind in ("URL", "TOKEN"))]
    if len(names) > SLOTS:
        raise ValueError(f"{len(names)} secrets, pacer.yml has {SLOTS} SECRET_<i> lines: add lines and raise SLOTS")
    return names + [""] * (SLOTS - len(names))


def accounts(env, config=None):
    """[(name, env)]: the Claude accounts of the secrets (#4237, docs/COLLABORATORS.md part 3). pacer.yml gives the
    secrets of `secret_names` as `SECRET_NAMES` (their JSON list) and `SECRET_<i>` (the value of name i); `ALL_SECRETS`
    (a JSON dict, for a local `operator_check.py`) adds to `env` too. The first account (the first table of `[accounts]`)
    has the present names (`CLAUDE_CODE_OAUTH_TOKEN`, `PACER_URL_<TASK>`, `PACER_TOKEN_<TASK>`). Another account NAME has
    `CLAUDE_CODE_OAUTH_TOKEN_<NAME>`, `PACER_URL_<NAME>_<TASK>` and `PACER_TOKEN_<NAME>_<TASK>`: its env gets them under the
    present names, so that each account reads the same way. A new account needs its secrets and its table."""
    import agent_config
    env = {**env, **json.loads(env.get("ALL_SECRETS") or "{}")}
    env |= {n: env[f"SECRET_{i}"] for i, n in enumerate(json.loads(env.get("SECRET_NAMES") or "[]"))
            if n and env.get(f"SECRET_{i}")}
    out = [(agent_config.first_account(config), env)]
    for name in sorted(k[len(TOKEN) + 1:] for k in env if k.startswith(f"{TOKEN}_") and env[k]):
        own = {TOKEN: env[f"{TOKEN}_{name}"]}
        for kind in ("PACER_URL_", "PACER_TOKEN_"):
            own |= {kind + k[len(f"{kind}{name}_"):]: v for k, v in env.items() if k.startswith(f"{kind}{name}_")}
        out.append((name.lower(), own))
    return out


def has_url(env, task):
    """True when `env` (of one account) has the URL and the token of the API trigger of `task`."""
    return bool(env.get(f"PACER_URL_{task.upper()}") and env.get(f"PACER_TOKEN_{task.upper()}"))


def assign(k, runs, missing, weights, has=lambda account, task: True):
    """[(task, account)]: the K runs of the plan (the lane runs first, then the main runs), one at a time to the account
    with the most missing runs left (the first one of `missing` on a tie) that has the task (`has`). A run takes its
    weight in Opus runs from the account. A task that no account has gets no run."""
    left, out = dict(missing), []
    for task in [t for t, n in [*runs.items(), ("main", k - sum(runs.values()))] for _ in range(max(n, 0))]:
        if fit := [a for a in left if has(a, task)]:
            a = max(fit, key=lambda a: left[a])
            out.append((task, a))
            left[a] -= weights.get(task, 1.0)
    return out


def missing_runs(targets, claims):
    """{account: missing Opus runs}: its target minus its claims, at least 0. An account with no target (a failed quota
    read) is not in it: it gets no run."""
    return {a: max(0.0, t - claims.get(a, 0.0)) for a, t in targets.items() if t is not None}


def account_targets(reads, comments, now, names, config=None):
    """(target, {account: missing}, weights): the target for `usage.fire` and the missing runs of each account (#4237).
    Each account with a quota read gets its own target (`usage.target_runs` with its usage, its burns and the `reserve`
    of its table in `[accounts]`) and its own claims (the ` account NAME` of the claim refs). The target of `fire` is
    the claims of all runs plus the sum of the missing runs, so the global limits of `fire` (`max_runs`, `max_fire`,
    the flow brake, the ready tickets) cap that sum."""
    import health
    t = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    refs, weights = health.claim_refs() or [], health.lane_weights(comments)[0]
    eq = lambda lanes: health.opus_equivalent(sum(lanes.values()), lanes, weights)
    tables, targets = (usage.CONFIG if config is None else config).get("accounts", {}), {}
    for name in [n for n in names if n in reads]:
        burn, burn7 = usage.burns(comments, account=name)
        r = (tables.get(name) or {}).get("reserve", 0)
        targets[name] = usage.target_runs(reads[name], now, burn, end=usage.END - r, mid=usage.MID - r, burn7=burn7)
    missing = missing_runs(targets, {n: eq(health.count_lanes(refs, t, account=n)) for n in names})
    return eq(health.count_lanes(refs, t)) + sum(missing.values()), missing, weights


HEAD = "travel-aggregator pacer brief"     # the first line of a brief: the `scheduled` skill looks for it
NEXT = 2                        # tickets of the `next:` line of a brief (#5076)
TEXT_MAX = 60000                # characters of a brief: the code places are cut first, then the ticket text
RED = ("failure", "timed_out")  # a CI run on main with this result: the runs fix main first (autopilot step 2)
CONTEXT = 120000                # the context up to which a run takes a next ticket (`more.md`: below it a next ticket
CONTEXT_HIGH = 160000           # is cheaper than a fresh run); higher while the task is near its hourly start limit
HOURLY = 30                     # starts per hour of one task (the docs of the scheduled tasks): above 80 % of it a
                                # fresh run may not start, so a run with a large context goes on (#4190)


def context_limit(task, hour):
    """The `context:` line of a brief: the limit of `more.md` for a run of `task`. `hour`: {task: runs} that the pacer
    started in the last 60 minutes (its log, no API call)."""
    return CONTEXT_HIGH if (hour or {}).get(task, 0) >= HOURLY * 0.8 else CONTEXT


def send(url, token, text=None, timeout=30):
    """Start one run of the task of `url`, with `text` as its fire payload. Raises on an HTTP error. Returns the JSON
    answer ({} when it does not parse): `claude_code_session_url` names the new session."""
    req = urllib.request.Request(url, data=json.dumps({"text": text} if text else {}).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "anthropic-beta": BETA, "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        try:
            return json.loads(r.read() or b"{}")
        except ValueError:
            return {}


def queues(open_all, refs, now, tasks):
    """{task: [issues]}: the candidates of each task in the pick order of autopilot step 5, without the tickets that
    a run holds (`dashboard.claimed`). The main task takes no ticket of a `reserved` lane (`dashboard.candidates`)."""
    import dashboard
    prs = [i["number"] for i in open_all if "pull_request" in i]
    busy = dashboard.work(open_all, {n: [f["filename"] for f in dashboard.pages(f"pulls/{n}/files", 3)] for n in prs})
    held = dashboard.claimed(refs or [], datetime.datetime.fromtimestamp(now, datetime.timezone.utc))
    return {t: [i for i in dashboard.candidates(open_all, busy, lane=None if t == "main" else t)
                if i["number"] not in held] for t in sorted(set(tasks))}


FAILED = ("action_required", "cancelled", "failure", "startup_failure", "timed_out")   # a check with this result is red


def pr_checks(checks):
    """The check runs of the PR's own CI: without the runs of a `full` CI dispatch (its job `slow` ran, #5462). The
    slow and server tests do not gate a PR (they run each night on main), but the red jobs of a dispatch on the head
    of a `hold` PR kept #5410 out of each Automerge sweep for 5 hours and gave its ticket 2 takeovers."""
    full = {c.get("check_suite", {}).get("id") for c in checks if c.get("name") == "slow" and c.get("conclusion") != "skipped"}
    return [c for c in checks if c.get("check_suite", {}).get("id") not in full]


def ci_wait(pr, checks):
    """"run" when the quick CI of the open PR still runs, "green" when it passed and no check failed, else None (red,
    the label `conflict`, no quick check: take the ticket over). checks: the check runs of its head. 10 of 14
    takeovers "after the report" closed by Automerge 0 to 18 minutes later (#4932); a green PR that Automerge cannot
    merge gets `conflict` (#4926), so this rule does not hide it."""
    import ship_pr
    if "conflict" in {lb["name"] for lb in pr.get("labels") or []}:
        return None
    checks = pr_checks(checks)
    quick = ship_pr.quick_run(checks)   # the parts `quick (1)` and `quick (2)` as one run (#1077)
    if not quick or any(c.get("conclusion") in FAILED for c in checks):
        return None
    if quick.get("status") != "completed":
        return "run"
    return "green" if quick.get("conclusion") == "success" else None


def head_checks(sha):
    import dashboard
    return dashboard.api(f"commits/{sha}/check-runs?per_page=100").get("check_runs", [])


def sweep():
    """Start the Automerge sweep (`workflow_dispatch`): it merges a green PR whose CI event it missed (#734)."""
    import dashboard
    try:
        dashboard.api("actions/workflows/automerge.yml/dispatches", "POST", {"ref": "main"})
    except json.JSONDecodeError:                        # the answer 204 has no body
        pass
    except Exception as e:                              # the cron of Automerge sweeps too: keep the takeovers
        print(f"no sweep: {e}", file=sys.stderr)


def stuck(open_all, refs, now, pulls, checks=None, start_sweep=sweep):
    """[(issue, takeover)] of the `in-progress` tickets whose run stopped (`claim.stuck`, as `claim.py 0 --stuck`).
    takeover: "PR #M BRANCH" of the open PR that closes the ticket, else "no PR". refs: the lines of
    `health.claim_refs`; None (git failed): no stuck ticket, else each ticket would look stuck. A PR that only waits
    for its quick CI or for Automerge (`ci_wait`) gives no takeover; a green one starts the sweep, once per call.
    checks: sha -> the check runs of the head (`head_checks`); start_sweep: None, no sweep (`--dry-run`)."""
    import claim
    if refs is None:
        return []
    top = {}
    for line in refs:
        key, t, subject = (line.split(" ", 2) + ["", ""])[:3]
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", key)
        if m and t.isdigit() and int(m[2] or 1) >= top.get(int(m[1]), (0,))[0]:
            top[int(m[1])] = (int(m[2] or 1), subject, int(t))
    import dashboard
    issues = {i["number"]: i for i in open_all if "pull_request" not in i and "in-progress" in dashboard.labels(i)}
    changed = {n: datetime.datetime.fromisoformat(i["updated_at"].replace("Z", "+00:00")).timestamp()
               for n, i in issues.items()}
    out, green = [], False
    for n, _ in claim.stuck(changed, {n: (s, t) for n, (_, s, t) in top.items()}, now):
        pr = next((p for p in pulls if claim.closes(n).search(claim.prose(p.get("body")))), None)
        try:
            wait = pr and pr["head"].get("sha") and ci_wait(pr, (checks or head_checks)(pr["head"]["sha"]))
        except Exception as e:                          # no check runs: take it over as before
            print(f"#{n}: no checks of PR #{pr['number']}: {e}", file=sys.stderr)
            wait = None
        if wait:
            print(f"#{n}: PR #{pr['number']} waits for {'its quick CI' if wait == 'run' else 'Automerge'}, no takeover",
                  file=sys.stderr)
            green = green or wait == "green"
            continue
        out.append((issues[n], f"PR #{pr['number']} {pr['head']['ref']}" if pr else "no PR"))
    if green and start_sweep:
        start_sweep()
    return out


def fits(issue, task):
    """True when a run of `task` may take the ticket: a lane takes its `lane:` tickets, the main task the tickets of no
    `reserved` lane (as `dashboard.candidates`)."""
    import dashboard
    lanes = {n[len(dashboard.LANE):] for n in dashboard.labels(issue) if n.startswith(dashboard.LANE)}
    return task in lanes if task != "main" else not lanes & set(dashboard.RESERVED)


def brief(issue, comments, name, task, sample, limit=TEXT_MAX, context=CONTEXT, account=None, takeover=None,
          after=()):
    """The fire payload of a run: the lines that the run acts on, then the ticket and its code places as data.
    account: the Claude account of the run (several accounts, #4237), else no `account:` line. takeover: the PR of a
    stuck ticket that the pacer took over for the run ("PR #M BRANCH" or "no PR", `stuck`), else no `takeover:` line.
    after: the next tickets that the run claims itself after its PR (`Briefs.follow`, #5076), else no `next:` line."""
    import claim
    import ticket_context
    head = "\n".join([HEAD, f"ticket: {issue['number']}", f"claim: {name}", f"lane: {task}", f"usage: {sample}",
                      f"context: {context}"] + [f"next: {' '.join(map(str, after))}"] * bool(after)
                     + [f"account: {account}"] * bool(account)
                     + [f"takeover: {takeover}"] * bool(takeover))
    text = claim.ticket_text(issue, comments)
    places = ticket_context.context(issue.get("body"))
    out = f"{head}\n\n--- ticket (data) ---\n{text}\n\n--- code places (framework/tools/ticket_context.py) ---\n{places}"
    if len(out) > limit:
        note = "\n[cut: run `python3 framework/tools/ticket_context.py N` for the rest]"
        out = out[:limit - len(note)] + note
    return out


def unanswered():
    """True when owner comments wait for an answer (`feedback.py`); then one main run gets no brief and does step 3.
    False when GitHub fails: the briefs go on."""
    try:
        import feedback
        return bool(feedback.fetch())
    except Exception as e:
        print(f"no feedback read: {e}", file=sys.stderr)
        return False


def red_main():
    """True when the last CI run on main failed: the runs then do steps 1 to 5, and one of them fixes main."""
    import dashboard
    try:
        runs = dashboard.api("actions/workflows/ci.yml/runs?branch=main&per_page=1").get("workflow_runs") or []
    except Exception:                                   # no answer: give no brief, the runs check it themselves
        return True
    return bool(runs) and runs[0].get("conclusion") in RED


BRAKE_TITLE = "Make CI keep up with the runs: the flow brake is on"


def brake_ticket(reason, api=None):
    """Report the flow brake (owner, #4301): when no open issue has BRAKE_TITLE, open one (`P1`, `tooling`) that asks a
    run to make CI faster. One issue at a time, so a long brake makes no copies. The number of the issue, or None."""
    if api is None:
        import dashboard
        api = dashboard.api
    if any(i.get("title") == BRAKE_TITLE for i in api("issues?state=open&labels=tooling&per_page=100")):
        return None
    body = (f"The pacer slowed down: {reason}.\n\n## Goal\nCI keeps up with the runs again, so the pacer starts runs"
            " at the quota target.\n\n## Context\n- `framework/tools/usage.py` (`flow_cap`, `read_flow`) is the flow brake;"
            " `[pacing]` of `steering/system/system.toml` has its limits.\n- Read the times of the last `ci.yml` runs (queue time and"
            " the time of each job) and find the largest cost.\n\n## Acceptance criteria\n- [ ] A change makes the"
            " quick CI faster or makes fewer CI runs, and the PR names the times before and after.\n")
    return api("issues", "POST", {"title": BRAKE_TITLE, "body": body, "labels": ["P1", "tooling", "size:M"]})["number"]


class Briefs:
    """Takes, claims and writes the ticket of each run that the pacer starts (None: no brief for any run)."""

    def __init__(self, todo, out, now, found, dry=False, hour=None, reads=None):
        self.todo, self.given, self.dry, self.hour = None, [], dry, hour or {}
        self.next = {}                                  # {ticket: its `next:` tickets} for `record` (#5308)
        self.stuck, self.takeovers, self.nexts, self.feedback = [], set(), set(), 0
        self.plan = [t for t, *_ in todo or ()]         # the tasks of the runs of this cycle that have no ticket yet
        if "open" not in out or out.get("flow") is not None or not todo or red_main():
            return
        try:
            self.todo = queues(out["open"], out.get("refs"), now, [t for t, *_ in todo])
        except Exception as e:                          # GitHub failed: the runs pick themselves, as before the briefs
            print(f"no briefs: {e}", file=sys.stderr)
            return
        self.taken, self.sample = set(), usage.sample_line(found, now, out.get("claims") or 0, None, out.get("lanes"))
        self.samples = {a: usage.sample_line(u, now, out.get("claims") or 0, None, out.get("lanes"), account=a)
                        for a, u in (reads or {}).items()}   # the `Usage:` line of each account (#4237)
        try:
            import dashboard
            self.stuck = stuck(out["open"], out.get("refs"), now, dashboard.pages("pulls?state=open"),
                               start_sweep=None if dry else sweep)
        except Exception as e:                          # the runs find the stuck tickets themselves (`cycle_start.py`)
            print(f"no takeovers: {e}", file=sys.stderr)
        self.feedback = 1 if unanswered() else 0       # one main run reads the owner comments (#294)

    def take(self, task, account=None):
        """(number, name, text, next) of the next free ticket of `task`, claimed for its run (of `account`), or None. A
        stuck ticket of the task comes first (autopilot step 2), taken over for the run. next: its `next:` tickets."""
        import claim
        import dashboard
        if self.todo is None:
            return None
        if task in self.plan:
            self.plan.remove(task)
        if self.feedback and task == "main":            # a run with a brief skips autopilot step 3 (feedback):
            self.feedback -= 1                          # owner comments waited for hours (#294)
            return None
        work = [(i, t) for i, t in self.stuck if fits(i, task)] + [(i, None) for i in self.todo.get(task, [])]
        work.sort(key=lambda w: w[0]["number"] in self.nexts)   # a `next:` ticket only when no other is free (stable)
        for issue, takeover in work:
            n = issue["number"]
            if n in self.taken:
                continue
            self.taken.add(n)
            name = f"pacer-r{uuid.uuid4().hex[:10]}"   # a letter first: `usage.pending` cuts a `-<digits>` end
            if self.dry:
                return n, name, "", self.follow(issue, task)
            try:
                tag = (f" account {account}" if account else "") + ("" if task == "main" else f" lane {task}")
                if not claim.claim(n, takeover=bool(takeover), by=name, tag=tag):
                    continue                            # a run claimed (or took over) it after the read
                if takeover:
                    self.takeovers.add(n)
                after = self.follow(issue, task)
                return n, name, brief(issue, dashboard.pages(f"issues/{n}/comments", 1), name, task,
                                         self.samples.get(account, self.sample), context=context_limit(task, self.hour),
                                         account=account, takeover=takeover, after=after), after
            except (Exception, SystemExit):             # git or GitHub failed (claim.fail exits): the runs claim
                self.todo = None                        # themselves; a claim that stays goes stale in 30 minutes
                self.drop(n, name)
                return None
        return None

    def ahead(self):
        """The tickets that the other runs of this cycle take (`plan`, in order, as `take`): no `next:` line gets them."""
        seen, out = self.taken | self.nexts, set()
        for task in self.plan:
            work = [i for i, _ in self.stuck if fits(i, task)] + self.todo.get(task, [])
            if issue := next((i for i in work if i["number"] not in seen), None):
                seen.add(issue["number"])
                out.add(issue["number"])
        return out

    def follow(self, issue, task):
        """The NEXT tickets of the `next:` line of the run of `issue`: the free tickets of the queue of `task` beyond the
        runs of this cycle, related ones first (`cycle_start.prefer`). The pacer does not claim them: the run claims one
        after its PR, so it skips a fresh start (#5076: 1-ticket runs cost 0.37M eq per PR, 3-ticket runs 0.19M)."""
        import cycle_start
        skip = self.taken | self.nexts | self.ahead()
        free = [i for i in self.todo.get(task, []) if i["number"] not in skip]
        out = [i["number"] for i in cycle_start.prefer(free, issue, None if task == "main" else task)][:NEXT]
        self.nexts.update(out)
        return out

    @staticmethod
    def drop(n, name):
        """Release the claim `name` of ticket n, if it was made."""
        import claim
        try:
            claim.release(n, by=name)
        except (Exception, SystemExit):
            pass

    def start(self, task, url, token, account=None):
        """Start one run of `task` (of `account`), with a brief when a ticket is free. Raises like `send`; then the
        claim goes back."""
        import claim
        got = self.take(task, account)
        if self.dry:
            print(f"POST {url} ({task}{f', account {account}' if account else ''})" + (f" #{got[0]}" if got else "")
                  + (f" next {' '.join(map(str, got[3]))}" if got and got[3] else ""))
            return
        try:
            answer = send(url, token, got[2] if got else None)
        except Exception:
            if got:
                self.drop(got[0], got[1])
                self.nexts.difference_update(got[3])   # no run reads its `next:` line
            raise
        if got:
            link = answer.get("claude_code_session_url")
            over = got[0] in self.takeovers               # `health.takeovers` counts this comment (#1703)
            claim.start(got[0], by=got[1], note=(" Stuck: its run stopped." if over else "")
                        + (f" Session: {link}" if link else ""), **({"word": "Taken over by"} if over else {}))
            self.given.append(got[0])
            if got[3]:
                self.next[got[0]] = list(got[3])


NUMBERS = {"target": r"target (\d+) runs", "claims": r"claims (\d+) ", "claims_opus": r"\(([\d.]+) Opus runs\)",
           "ready": r"ready (\d+) ", "refill": r"refill (\d+) "}


def github_limit(env=os.environ, timeout=20):
    """{limit, used, remaining, reset} of the REST calls of the token of the workflows (`/rate_limit` counts no call),
    or None. All workflows of the repository share this hourly limit, and it ran out at 14:22 on 2026-10-29
    ("API rate limit exceeded for installation"): the records show the use per hour and the real limit."""
    if not env.get("GITHUB_TOKEN"):
        return None
    req = urllib.request.Request("https://api.github.com/rate_limit", headers={
        "Authorization": f"Bearer {env['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            core = json.load(r)["resources"]["core"]
    except Exception:                                   # no limit in the record: the starts go on
        return None
    return {k: core.get(k) for k in ("limit", "used", "remaining", "reset")}


def record(at, found, burn, burn7, k, runs, started, line, problems=(), github=None, quota=None):
    """The JSON record of one cycle (`--log`, 2026-10-29): the quota, the burns, the planned and the started runs, the
    inputs of `usage.fire` and the REST budget of the workflow token (`github_limit`). Only the Actions log had them
    (no tool reads it, and it expires): with the starts and the `Run:` lines of the reports, a run that ends with no
    report shows. quota: {account: its 5-hour and 7-day usage and its missing runs} with several accounts (#4239)."""
    rec = {"at": f"{at:%Y-%m-%dT%H:%M:%SZ}", "k": k, "plan": runs, "started": started, "burn": burn, "burn7": burn7,
           "github": github, **({"quota": quota} if quota else {}),
           **{w: list(found[w]) for w in ("five_hour", "seven_day") if w in found}}
    for key, rx in NUMBERS.items():
        m = re.search(rx, line)
        rec[key] = None if m is None else float(m[1]) if "." in m[1] else int(m[1])
    return {**rec, "problems": list(problems), "line": line}


def recent_starts(path, now, minutes=usage.PENDING):
    """{task: runs} that the cycles of the log file `path` (`--log`) started in the last `minutes` before `now` (a Unix
    time): `usage.fire` counts those with no claim yet. An absent or broken log: none."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    at = datetime.datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                except (ValueError, KeyError, TypeError):
                    continue
                if at.timestamp() >= now - minutes * 60:
                    for task, n in (r.get("started") or {}).items():
                        out[task] = out.get(task, 0) + n
    except OSError:
        pass
    return out


def switch(config=None):
    """True while `pacer` in `[pacing]` is "workflow", False for another value. A missing key raises KeyError: the
    inline check of pacer.yml read a moved `[pacing]` as "stop", and no run started for 30 minutes (#4349)."""
    return (usage.CONFIG if config is None else config)["pacing"]["pacer"] == "workflow"


def main(argv=None, env=os.environ):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print the calls, send nothing")
    ap.add_argument("--log", metavar="FILE", help="add the record of this cycle to FILE (one JSON line)")
    ap.add_argument("--switch", action="store_true", help="exit 0 while the loop runs, 3 to stop it")
    ap.add_argument("--secrets", action="store_true", help="print the JSON list of the secret names of pacer.yml")
    a = ap.parse_args(argv)
    if a.secrets:
        print(json.dumps(secret_names()))
        return
    if a.switch:
        try:
            sys.exit(0 if switch() else 3)
        except KeyError as e:                           # a config error is red, not a quiet stop
            sys.exit(f"no key {e} in [pacing] (agent_config: agent.toml, steering/system/system.toml)")
    now, accts = datetime.datetime.now(datetime.timezone.utc).timestamp(), accounts(env)
    reads, unread = {}, []
    for i, (name, e) in enumerate(accts):              # one tiny CLI call per account (#4237)
        try:
            u = usage.read_usage() if i == 0 else usage.read_usage(token=e[TOKEN])
        except Exception:                               # a timeout of one account: the others go on
            u = None
        if u:
            reads[name] = u
        else:
            unread.append(f"no quota read: account {name}")
    if not reads:
        sys.exit("no rate_limit_event in the CLI output: start no run")
    found = next(iter(reads.values()))                 # the quota of the line of `fire`: the first account that read
    status = usage.read_status()                       # one read for both fire calls (#3069)
    burn, burn7 = usage.burns(status[0])
    started = recent_starts(a.log, now) if a.log else {}   # the runs of the last cycles that have no claim yet
    out, envs, many = {}, dict(accts), len(accts) > 1
    target, missing, weights = (account_targets(reads, status[0], now, list(envs)) if many
                                else (None, {accts[0][0]: math.inf}, {}))
    k, runs, line = usage.fire(found, now, burn, burn7, status=status, started=started, out=out, target=target)
    if many:
        line += " · accounts " + ", ".join(f"{n} missing {missing[n]:.1f}" if n in missing else f"{n} no read"
                                           for n in envs)
    has = lambda acct, task: has_url(envs[acct], task)
    todo = [(task, envs[acct][f"PACER_URL_{task.upper()}"], envs[acct][f"PACER_TOKEN_{task.upper()}"], acct)
            for task, acct in assign(k, runs, missing, weights, has)]
    hour = recent_starts(a.log, now, 60) if a.log else {}   # the starts of the last hour: the `context:` line
    briefs = Briefs(todo, out, now, found, a.dry_run, hour, reads if many else None)
    skipped = sorted({t for t, n in [*runs.items(), ("main", k - sum(runs.values()))]
                      if n and not any(has(acct, t) for acct in missing)})
    failed, limited, count = [], set(), {}             # limited: (account, task) at the hourly limit
    started = dict.fromkeys([*runs, "main"], 0)

    def go(task, url, token, acct):
        briefs.start(task, url, token, acct if many else None)
        started[task] += 1
        count[acct, task] = count.get((acct, task), 0) + 1

    for task, url, token, acct in todo:
        if a.dry_run:
            briefs.start(task, url, token, acct if many else None)
        elif (acct, task) not in limited:
            try:
                go(task, url, token, acct)
            except urllib.error.HTTPError as e:
                if e.code == 429:                       # the hourly limit: do not call this task again now
                    limited.add((acct, task))
                else:
                    failed.append(f"{task}: HTTP {e.code}")
            except Exception as e:                      # URLError, timeout
                failed.append(f"{task}: {e}")
    # The room of the blocked lane runs goes to the main task of the same account, up to the main runs of a new plan
    # without the limited lanes.
    blocked = {acct: n for acct in envs if (acct, "main") not in limited and (n := sum(
        1 for t, *_, x in todo if x == acct and t != "main" and (acct, t) in limited) - sum(
        c for (x, t), c in count.items() if x == acct and (x, t) in limited)) > 0}
    if blocked:
        skip = {t for _, t in limited}
        k2, runs2, _ = usage.fire(found, now, burn, burn7, skip=skip, status=status, started=started, target=target)
        room = k2 - sum(runs2.values())
        for acct, n in blocked.items():
            for task, url, token in calls(min(n, room), {}, envs[acct]):
                try:
                    go(task, url, token, acct)
                    room -= 1
                except urllib.error.HTTPError as e:
                    if e.code != 429:
                        failed.append(f"{task}: HTTP {e.code}")
                    break
                except Exception as e:
                    failed.append(f"{task}: {e}")
                    break
    if a.dry_run:
        started = {t: sum(1 for x, *_ in todo if x == t) for t in started}
    if out.get("flow") is not None and not a.dry_run:   # the brake slows the runs: report it and ask for a faster CI
        try:
            if n := brake_ticket(out.get("flow_reason", "flow brake")):
                print(f"flow brake: opened #{n}")
        except Exception as e:                          # the report never stops the starts
            print(f"no brake ticket: {e}", file=sys.stderr)
    at, gh = datetime.datetime.now(datetime.timezone.utc), github_limit(env)
    print(f"Pacer {at:%H:%MZ}: K={k}, "
          + ", ".join(f"{t} {n}" for t, n in runs.items())
          + f". {'Would start' if a.dry_run else 'Started'} " + json.dumps(started)
          + (f", no URL for {', '.join(skipped)}" if skipped else "")
          + (f", hourly limit: {', '.join(sorted({t for _, t in limited}))}" if limited else "")
          + (f", {'; '.join(unread)}" if unread else "")
          + (f", failed: {'; '.join(failed)}" if failed else "")
          + (f", briefs {' '.join(f'#{n}' for n in briefs.given)}" if briefs.given else "") + f". {line}"
          + (f" · GitHub API {gh['used']}/{gh['limit']} (reset {gh['reset']})" if gh else ""))
    if a.log and not a.dry_run:
        problems = ([f"no URL: {t}" for t in skipped] + unread
                    + [f"hourly limit: {t}" + (f" (account {x})" if many else "") for x, t in sorted(limited, key=str)]
                    + failed)
        try:                                            # the log never stops the starts
            with open(a.log, "a") as f:
                quota = {n: {"five_hour": u["five_hour"][0], "seven_day": u.get("seven_day", (None,))[0],
                             "missing": round(missing[n], 2) if n in missing else None}
                         for n, u in reads.items()} if many else None          # the quota of each account (#4239)
                f.write(json.dumps({**record(at, found, burn, burn7, k, runs, started, line, problems, gh, quota),
                                    "briefs": briefs.given, "next": {str(n): t for n, t in briefs.next.items()}}
                                   | ({"accounts": {x: sum(c for (y, _), c in count.items() if y == x) for x in envs}}
                                      if many else {})) + "\n")
        except OSError as e:
            print(f"no pacer log: {e}", file=sys.stderr)
    sys.exit(int(bool(failed)))


if __name__ == "__main__":
    main()
