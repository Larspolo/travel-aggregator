"""The quota usage of the Claude subscription, and the number of runs that uses it (owner request, 2026-10-26).

The aim (owner, 2026-10-26): 90 % of the 5-hour window used 2 hours before its reset, then slower to 98 % at the
reset, so that each window reaches the limit (#587).

    python3 framework/tools/usage.py              # five_hour 30% (resets 06:30 UTC, 2.0 h) · seven_day 30% ... · target 12 runs
    python3 framework/tools/usage.py --target     # only the number of runs (rule 4 of the scheduled task)
    python3 framework/tools/usage.py --json
    python3 framework/tools/usage.py --sample     # Usage: <now> · usage 30.0% · resets <time> · runs 9 · week 56.0% · release 61.2%
    python3 framework/tools/usage.py --fire       # the number of runs that the pacer starts now (`framework/tools/pacer.py`, #3193)
    python3 framework/tools/usage.py --flow       # exit 1 when the flow brake is on: the runs repair PRs, no new ticket

The flow brake (owner, 2026-10-27): the quota is not the only bottleneck. When CI, merge conflicts or anything else
stops the merges, the agent PRs build up, and a night of new PRs gives many conflicts. So `--fire` counts the open
agent PRs older than `pr_minutes` (they wait for something that is not the quota) and the queued runs of the quick CI (`ci.yml` only, #106). At
`max_waiting_prs` it starts at most 1 run per cycle, and that run only repairs PRs (autopilot step 2). At
`max_ci_queue` it starts no run: a run cannot make CI faster. While the brake is on, the pacer keeps one open `tooling` issue that
asks for a faster CI (`pacer.brake_ticket`, #4301). The limits are in `[pacing]` of `steering/system/system.toml`.

BURN and BURN7 (the same for the 7-day window, #1695) are the defaults. When the run reports on the status issue
have enough `Usage:` lines (at least 5 pairs in the last 24 hours), `framework/tools/health.py` measures the burns from them
and this tool uses those values (#462).

The CLI reports the usage of the subscription in a `rate_limit_event` of its stream-json output. One tiny Haiku
call reads it, about 1 s and a few tokens. All runs share one quota, so each run sees the same numbers.
The pure functions take plain values, so the tests need no network.
"""
import argparse
import datetime
import functools
import json
import math
import os
import re
import subprocess
import sys
import time

import agent_config
from agent_config import CONFIG

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))   # the project tools: release.py (#4195)

NEW_EPIC_WAIT = 10 * 60   # seconds: an epic made less than this ago is split by its run first (#328)
BURN = 0.03         # share of the 5-hour quota that one run uses per hour (16 runs used about 50 % per hour, 2026-10-25)
BURN7 = 0.005       # share of the 7-day quota that one run uses per hour (0.0053 measured on 2026-10-27, #1695)
MID, MID_LEFT = 0.90, 2.0   # aim: this share is used this many hours before the 5-hour window resets (#587)
END = 0.98          # aim: this share is used when the 5-hour window resets
LO, HI = 1, CONFIG.get("pacing", {}).get("max_runs", 16)   # bounds of the number of runs (`agent.toml`, #1706)
FREE7 = CONFIG.get("pacing", {}).get("week_free", 0.60)   # below this 7-day usage only the 5-hour window counts (owner, 2026-10-27)
WEEK_GUARD = CONFIG.get("pacing", {}).get("week_guard", True)   # false: the 7-day usage does not count (owner, 2026-10-28)
WAIT = CONFIG.get("pacing", {}).get("max_waiting_prs", 10)   # flow brake: open agent PRs older than PR_MINUTES
QUEUE = CONFIG.get("pacing", {}).get("max_ci_queue", 5)      # flow brake: queued CI runs (no runner yet)
PR_MINUTES = CONFIG.get("pacing", {}).get("pr_minutes", 30)  # Automerge merges a green PR in a few minutes
MAX_FIRE = CONFIG.get("pacing", {}).get("max_fire", 8)   # runs that the pacer starts per cycle: each run needs a few minutes to claim its ticket; the same as agent.toml (the pacer used an old 4, 2026-10-28)
REFILL = CONFIG.get("pacing", {}).get("refill_runs", 1)   # runs beyond the ready tickets: each refills one epic (#609, #650)
PENDING = 12                # minutes: a run that the pacer started and that has no claim yet counts as a claim
REFILL_GAP = CONFIG.get("pacing", {}).get("refill_gap", 60)   # minutes after a refill lock with no refill run
CALL = ["claude", "-p", "Reply with OK.", "--model", "claude-haiku-5-5", "--output-format", "stream-json", "--verbose"]


def parse(lines):
    """{window: (utilization 0..1, resets_at epoch s, status)} from the stream-json lines of the CLI, or {}."""
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "rate_limit_event":
            w = (d.get("rate_limit_info") or {}).get("unifiedWindows") or {}
            return {k: (float(v.get("utilization") or 0), int(v.get("resetsAt") or 0), v.get("status", "")) for k, v in w.items()}
    return {}


def read_usage(timeout=120, token=None):
    """The quota of the account of the process, or with `token` (its `CLAUDE_CODE_OAUTH_TOKEN`) of that account (#4237)."""
    env = None if token is None else {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": token}
    r = subprocess.run(CALL, capture_output=True, text=True, timeout=timeout, cwd="/tmp", env=env)
    return parse(r.stdout.splitlines())


def target_runs(usage, now, burn=BURN, end=END, lo=LO, hi=HI, mid=MID, mid_left=MID_LEFT, burn7=None, free7=FREE7,
                week=WEEK_GUARD):
    """The number of runs that uses `mid` of the 5-hour window `mid_left` hours before its reset, and `end` at the
    reset, with a guard for the 7-day window. burn7 (the share of the 7-day quota of one run-hour, measured): a week
    used ahead of the time gets at most the runs that its budget (1 - used) carries to the 7-day reset (#1695). This
    count can be 0, below `lo`: the week has no budget for a run now, and the budget per hour grows while the reset
    comes nearer. Without burn7 the count of a week ahead by more than 10 points is half. Below `free7` of the 7-day
    usage there is no guard: the runs hit the 5-hour limit, not the weekly pace (owner, 2026-10-27). With `week` false
    (`week_guard` of `agent.toml`) there is no guard at all (owner, 2026-10-28)."""
    if not usage or "five_hour" not in usage:
        return None
    used, reset, status = usage["five_hour"]
    if status == "rejected":
        return 0
    left = (reset - now) / 3600
    if left > mid_left and used < mid:                          # the first 3 hours: fast to `mid`
        aim, hours = mid, left - mid_left
    else:                                                       # the last 2 hours: slow to `end`
        aim, hours = end, left
    hours = max(hours, 0.25)                                    # the last quarter hour: use what is left
    n = round(max(aim - used, 0) / hours / burn)
    if week and "seven_day" in usage:                           # do not use the week faster than it passes
        used7, reset7, status7 = usage["seven_day"]
        if status7 == "rejected":
            return 0
        if used7 < free7:
            return max(lo, min(hi, n))
        elapsed = 1 - max(reset7 - now, 0) / (7 * 86400)
        if burn7 and used7 > elapsed:
            fit = max(1 - used7, 0) / max((reset7 - now) / 3600, 0.25) / burn7
            return min(max(lo, min(hi, n)), math.floor(fit))
        if used7 > elapsed + 0.10:
            n //= 2
    return max(lo, min(hi, n))


def week_line(usage, now):
    """The 7-day projection: the points ahead of the time, and when the quota runs out at the mean rate of the week
    so far (or that it lasts to the reset), for example `week ahead +38 pt · runs out Wed 10:00`. "" without it."""
    if "seven_day" not in usage:
        return ""
    used7, reset7, _ = usage["seven_day"]
    gone = 7 * 86400 - max(reset7 - now, 0)
    line = f"week ahead {(used7 - gone / (7 * 86400)) * 100:+.0f} pt"
    if used7 <= 0 or gone <= 0:
        return line
    out = now + (1 - used7) / (used7 / gone)
    at = datetime.datetime.fromtimestamp(out, datetime.timezone.utc)
    return line + (f" · runs out {at:%a %H:%M}" if out < reset7 else " · lasts to the reset")


def runs_to_start(target, claims, ready, paused, hi=MAX_FIRE, refill=REFILL):
    """The number of runs that the pacer starts now: the runs that the target misses, not more than the ready tickets
    and `refill` more: these refill the queue, one epic each, then take a new ticket (#609). One refill run left the
    queue at 3 ready tickets for 40 target runs (2026-10-28).
    Runs that the scheduled task starts cannot start other runs (no `fire_trigger`, #566)."""
    if paused or not target:
        return 0
    return max(0, min(target - claims, ready + refill, hi))


def refill_runs(issues, now, minutes=60, refill=REFILL):
    """`refill` when an open ticket is newer than `minutes` (the refills still find work), else 1: when the epics have
    no goal left, the refill runs find nothing and stop, and one run is enough to start the next epic (`roadmap`).
    issues: the open issues and PRs; now: Unix seconds."""
    new = any("pull_request" not in i and now - datetime.datetime.fromisoformat(
        i["created_at"].replace("Z", "+00:00")).timestamp() < minutes * 60 for i in issues)
    return refill if new else min(refill, 1)


def refill_recent(lines, now, minutes=REFILL_GAP):
    """True when a refill lock (`claim/refill-*`) is younger than `minutes`: a deep run refills now or did it a short
    time ago. The pacer then starts no refill run, unless fewer tickets are ready than half the target. 16 of 30 deep runs made no PR (2026-10-29): most found the refill lock taken or nothing to refill, and
    each cost about $1 to $2. lines: `health.claim_refs()`; now: Unix seconds."""
    return any(k.startswith("refill-") and t.isdigit() and int(t) >= now - minutes * 60
               for k, t, *_ in (x.split(" ", 2) for x in lines or ()))


def pending(started, lines, now, minutes=PENDING, refill_lane="deep"):
    """{task: runs} that the pacer started in the last `minutes` (`started`: {task: runs}, `pacer.py --log`) and that
    made no claim yet: the starts less the runs whose first claim in a claim ref is in that time (the run of a claim is
    its branch without a `-k` of a later ticket; a run with an older claim is not new). The lane of a claim is its
    ` lane NAME`; a refill, review or roadmap lock is the work of `refill_lane`. The claims counted only the runs that
    had claimed: the next cycle started runs for the same tickets, and about 20 Haiku runs found no free ticket in
    10 hours (2026-10-29). `lines`: `health.claim_refs()`."""
    cut, old, new = now - minutes * 60, set(), {}
    for line in lines or []:
        _, t, subject = (line.split(" ", 2) + ["", ""])[:3]
        by = re.search(r" by (\S+)", subject)
        if not (t.isdigit() and by):
            continue
        run = re.sub(r"-\d+$", "", by[1])
        if int(t) < cut:
            old.add(run)
        elif subject.startswith("Claim "):
            lane = re.search(r" lane (\w+)$", subject)
            new[run] = lane[1] if lane else "main" if subject.startswith("Claim #") or not refill_lane else refill_lane
    made = {}
    for run, lane in new.items():
        if run not in old:
            made[lane] = made.get(lane, 0) + 1
    return {task: n - made.get(task, 0) for task, n in started.items() if n - made.get(task, 0) > 0}


def refill_need(ready, target, issues, due=lambda: [], reviews=lambda: [], free=lambda: [], now=None, closing=lambda e: False):
    """The reason of the refill runs, or "" when they have no work (#3547): an open epic with no open sub-issue and no
    open "Part of #E" ticket (the epic check; a release epic with an open ticket in its milestone has work), the tickets with
    `rank` after a release (release.yml gives it to the next release epic too: the `roadmap` skill, "Release cycle"),
    a release check with no ticket, a due process or roadmap review (deep
    locks: with no deep run they never run, #3560), and only while R < N (`queue.md`) the other refill sources. 5 deep
    runs in one hour found none with R >= N (2026-10-29), and one with R < N found no source (#3560). issues: the open
    issues and PRs; due, reviews, free: the release checks with no ticket, the due reviews and the other sources
    (free_sources), read only when needed. An epic made less than 10 minutes ago gets no epic check: its run splits it
    itself (#328). now: Unix seconds (default: the time now). closing(E): True when close.yml closes the epic E by
    itself (`epic_autoclose.ready`, #835): its check run would only add the label `close`."""
    import dashboard
    epics = [n for n in epic_checks(issues, now) if not closing(n)]
    if epics:
        return "epic check " + ", ".join(f"#{n}" for n in epics)
    if rank := sum(dashboard.RANK in dashboard.labels(i) for i in issues if "pull_request" not in i):
        return f"rank {rank} tickets after the release"                  # and the next release epic (`roadmap` skill)
    if checks := due():
        return f"{len(checks)} release checks"
    if kinds := reviews():
        return " and ".join(kinds) + " due"
    return f"ready {ready} < target {target}: " + ", ".join(sources) if ready < target and (sources := free()) else ""


def epic_checks(issues, now=None):
    """The open epics that wait for an epic check (`refill_need`): no open sub-issue, no open "Part of #E" ticket and
    no release milestone ticket, no hold, older than NEW_EPIC_WAIT. now: Unix seconds (default: the time now)."""
    import dashboard
    work = {int(n) for i in issues if "pull_request" not in i for n in re.findall(r"Part of #(\d+)", i.get("body") or "")}
    work |= {i["number"] for i in issues if dashboard.RELEASE in dashboard.labels(i)
             and dashboard.release_scope(i, issues)[2]}             # a release epic with open milestone tickets has work
    subs = lambda i: (s := i.get("sub_issues_summary") or {}).get("total", 0) - s.get("completed", 0)   # open sub-issues
    now = time.time() if now is None else now
    made = lambda i: datetime.datetime.fromisoformat(i["created_at"].replace("Z", "+00:00")).timestamp() \
        if i.get("created_at") else 0                    # no time (a partial record): an old epic
    epics = [i["number"] for i in issues if "epic" in dashboard.labels(i) and i["number"] not in work and not subs(i)
             and not {dashboard.MUTED, dashboard.AFTER, dashboard.RANK, dashboard.CLOSE, "needs-human"} & dashboard.labels(i)
             and now - made(i) >= NEW_EPIC_WAIT]
    return epics


def autoclosing(epic):
    """True when close.yml closes the epic by itself (`epic_autoclose.ready`); a missing tool or an error: False."""
    try:
        import epic_autoclose  # not in an older bootstrap copy
    except ImportError:
        return False
    return bool(epic_autoclose.ready(epic))


def release_due():
    """The release checks with no ticket (`release.due`), or [] when the read fails: the pacer must still start runs."""
    try:
        import release  # not in a bootstrap copy (`framework/tools/bootstrap.py`)
    except ImportError:                                     # a project with no release tool has no release checks (#153)
        return []
    try:
        features, _, rows, epics = release.load()
        return release.due(features, rows, epics)
    except Exception as e:                                  # a GitHub or file error
        print(f"release checks: {e}", file=sys.stderr)
        return []


def due_reviews(remote="origin", starved=None):
    """The due reviews whose lock no run holds yet (`claim.review_slot`, #3560). A read error counts as due. starved:
    True when the refill has no source (the roadmap review is due earlier then, #3741; default `claim.refill_starved`)."""
    import claim
    out = []
    for kind, name in (("review", "process review"), ("roadmap", "roadmap review")):
        try:
            key, _ = claim.review_slot(kind, remote, starved=starved)
            taken = key and claim.git("ls-remote", remote, f"refs/heads/claim/{kind}-{key}").stdout.strip()
        except (Exception, SystemExit) as e:                # claim.fail exits 2 on a GitHub error
            print(f"{name}: {e}", file=sys.stderr)
            key, taken = True, False
        out += [name] * bool(key and not taken)
    return out


def held(numbers):
    """True when an open issue of `numbers` (of a roadmap line) is `after-release` or `muted`: the owner holds the
    feature, and the refill leaves it out (#5301: `convert:export` named the held owner ticket #4198, no epic)."""
    import dashboard
    return any((i := dashboard.api(f"issues/{n}"))["state"] == "open"
               and {dashboard.AFTER, dashboard.MUTED} & dashboard.labels(i) for n in sorted(numbers))


def roadmap_features(text):
    """{key: (goal, done, named)} of the feature lines "- [ ] `key` ..." under the "## N." goals of a roadmap (the
    `roadmap` skill): done for "[x]", named = the issue numbers on the line. A project with no tools/release.py (#153)."""
    out, goal = {}, 0
    for line in text.splitlines():
        if m := re.match(r"## (\d+)\.", line):
            goal = int(m[1])
        elif goal and (m := re.match(r"- \[([ xX])\] `([^`]+)`(.*)", line)):
            out[m[2]] = (goal, m[1] != " ", {int(n) for n in re.findall(r"#(\d+)", m[3])})
    return out


def epic_key(body):
    """The roadmap key of an epic body ("Roadmap: `key`", the `roadmap` skill), or None."""
    m = re.search(r"^Roadmap: `([^`]+)`", body or "", re.M)
    return m and m[1]


def free_sources(root=None, epics=None, holds=held):
    """The refill sources of R < N besides the checks and reviews (#3560): the `[ ]` features of the goals 1 to 3 with
    no epic (the `roadmap` skill) inside the release focus (`release.focus`), not held by the owner (`held`), and the
    fallbacks of docs/coverage.md (none without the file). A read error counts as a source. Without tools/release.py
    the roadmap of `agent.toml` and the epics of GitHub (`epics`: a test stub, #153), and no release focus."""
    try:
        try:
            import release
            features, _, rows, found = release.load()
            key, root = release.epic_key, root or release.ROOT
            wait = set(release.waiting(features, rows, release.focus(root)))     # outside the release focus
        except ImportError:
            root = root or agent_config.ROOT
            with open(os.path.join(root, CONFIG["docs"]["roadmap"])) as f:
                features = roadmap_features(f.read())
            if epics is None:
                import dashboard
                epics = lambda: dashboard.pages("issues?labels=epic&state=all")   # noqa: E731
            found, key, wait = epics(), epic_key, set()
        keys, numbers = {key(e.get("body")) for e in found}, {e["number"] for e in found}
        free = [k for k, (goal, done, named) in features.items() if goal < 4 and not done and k not in keys
                and k not in wait and not named & numbers and not holds(named)]
        coverage = os.path.join(root, "docs", "coverage.md")
        fallbacks = 0
        if os.path.exists(coverage):
            with open(coverage) as f:   # the totals: | Group | types | own | infantry | fallback |
                fallbacks = sum(int(m[1]) for m in re.finditer(r"^\| [A-Z][a-z ]+ \| \d+ \| \d+ \| \d+ \| (\d+) \|$", f.read(), re.M))
    except Exception as e:                                  # a GitHub or file error
        print(f"refill sources: {e}", file=sys.stderr)
        return ["read error"]
    return [f"{len(free)} roadmap features with no epic"] * bool(free) + [f"{fallbacks} fallbacks"] * bool(fallbacks)


def plan(target, claims, ready, lanes, paused, hi=MAX_FIRE, refill=REFILL, refill_lane=None):
    """(K, {lane: runs}): the runs that the pacer starts now and the runs of each lane among them (#1715, #1727).
    lanes: [(name, ready tickets of the lane, weight)] in the order of their start. The target and the claims are in Opus
    runs, and a lane run counts its weight. Each lane gets runs for its ready tickets while the room lasts;
    `refill_lane` (the deep lane, 2026-10-28) also gets the `refill` runs: the queue refill is its work. The Opus runs
    take the rest of the target: at most the other ready tickets, and the `refill` runs when no lane refills (#609).
    A lane run that counts more than one Opus run (deep: 4) starts also when the room holds only one: else the main
    runs fill each small room first, and its tickets wait for ever. Its claim then counts its weight."""
    if paused or not target:
        return 0, {name: 0 for name, *_ in lanes}
    room, left, rest, out = target - claims, hi, ready, {}
    for name, n, w in lanes:
        want = n + (refill if name == refill_lane else 0)
        fit = math.floor(room / w + 1e-9) or int(room >= 1)
        k = max(0, min(want, left, fit)) if room > 0 else 0
        out[name], room, left, rest = k, room - k * w, left - k, rest - min(k, n)
    o = max(0, min(math.floor(room + 1e-9), rest + (0 if refill_lane else refill), left))
    return o + sum(out.values()), out


def lane_plan(target, claims, ready, ready_haiku, weight, paused, hi=MAX_FIRE, refill=REFILL):
    """(K, H): `plan` with the Haiku lane alone."""
    k, lanes = plan(target, claims, ready, [("haiku", ready_haiku, weight)], paused, hi, refill)
    return k, lanes["haiku"]


def waiting_prs(prs, now, minutes=PR_MINUTES):
    """The open agent PRs (branch `claude/*`, `agent/*` or `ccr-*`) older than `minutes`, without `hold` (the owner holds
    those): each waits for a fix, a conflict merge or CI, not for the quota."""
    old = now - minutes * 60
    return [p for p in prs if p["head"]["ref"].startswith(("claude/", "agent/", "ccr-"))
            and "hold" not in {x["name"] for x in p.get("labels", [])}
            and datetime.datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")).timestamp() < old]


def flow_cap(waiting, queued, max_waiting=WAIT, max_queue=QUEUE):
    """(cap, reason): the most runs that the pacer starts now when the flow is the bottleneck, not the quota.
    cap None: no brake. Too many queued CI runs: 0 (a run cannot make CI faster). Too many waiting PRs: 1, a run that
    only repairs PRs (autopilot step 2), so that the open PRs go down before new PRs come."""
    if queued >= max_queue:
        return 0, f"brake: CI queue {queued} >= {max_queue}"
    if waiting >= max_waiting:
        return 1, f"brake: {waiting} waiting PRs >= {max_waiting}, repair only"
    return None, f"flow ok: {waiting} waiting PRs, CI queue {queued}"


QUEUE_PATH = "actions/workflows/ci.yml/runs?status=queued&per_page=1"   # the flow brake counts only the quick CI (#106)


def read_flow(now):
    """(cap, reason) from GitHub: the open PRs and the queued runs of the quick CI. Only ci.yml: the cron runs of
    the other workflows wait in their concurrency groups and counted as a CI queue of 31 while the quick CI started
    each run at once (#106)."""
    import dashboard
    prs = dashboard.pages("pulls?state=open")
    queued = dashboard.api(QUEUE_PATH)["total_count"]
    return flow_cap(len(waiting_prs(prs, now)), queued)


def read_status():
    """(comments, note): the status comments of `framework/tools/health.py`, read once for the burns and the lane weights of
    --fire (#3069: three reads, and a failed one changed the burn with no message). A failed read gives no comments,
    so the defaults BURN, BURN7 and the start weights, and a note for the stderr line."""
    try:
        import health
        return health.status_comments(), ""
    except Exception as e:                                      # no GitHub access, a 5xx
        return [], f" · status comments failed ({type(e).__name__}: {str(e)[:100]}): default burns, start weights"


def measured_burn7(comments=None, account=None):
    """The share of the 7-day quota of one run-hour that `framework/tools/health.py` measures from the `Usage:` lines (of one
    account, #4237), or None. comments: those of read_status, else it reads them."""
    try:
        import health
        comments = health.status_comments() if comments is None else comments
        return health.weekly_burn(comments, datetime.datetime.now(datetime.timezone.utc), account=account)
    except Exception:                                           # no GitHub access: the old guard
        return None


def measured_burn(comments=None, account=None):
    """The burn that `framework/tools/health.py` measures from the `Usage:` lines of the status issue (of one account, #4237), or
    None.
    comments: those of read_status, else it reads them."""
    try:
        import health
        comments = health.status_comments() if comments is None else comments
        return health.measured_burn(comments, datetime.datetime.now(datetime.timezone.utc), account=account)
    except Exception:                                           # no GitHub access: use the default
        return None


def burns(comments, burn=None, account=None):
    """(burn, burn7): `burn` (--burn), else measured from the comments of read_status (the lines of `account` only, when
    it is given), else BURN and BURN7."""
    return burn or measured_burn(comments, account) or BURN, measured_burn7(comments, account) or BURN7


def sample_line(usage, now, claims, release=None, lanes=None, account=None):
    """The `Usage:` line of a run report, which `framework/tools/health.py` reads: also the 7-day usage and the release percent
    of all goals (tools/release.py), for the release progress per quota (#899), and the account of the quota
    (`· account NAME` at the end, #4236; none: the first account)."""
    iso = lambda t: f"{datetime.datetime.fromtimestamp(t, datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ}"
    used, reset, _ = usage["five_hour"]
    line = f"Usage: {iso(now)} · usage {used * 100:.1f}% · resets {iso(reset)} · runs {claims}"
    if "seven_day" in usage:
        line += f" · week {usage['seven_day'][0] * 100:.1f}%" + ("" if release is None else f" · release {release:.1f}%")
        line += f" · week resets {iso(usage['seven_day'][1])}"                  # for the dashboard (#1696)
    line += "".join(f" · {k} {n}" for k, n in sorted((lanes or {}).items()) if k != "opus" and n)   # (#1727)
    return line + (f" · account {account}" if account else "")


def release_percent(root=None, epics=None):
    """The percent of milestone C over all goals (tools/release.py), or None without GitHub access. A project with no
    tools/release.py: `roadmap_release` (the release per quota of `health.py` was always "-" without it)."""
    try:
        import release
    except ImportError:
        return roadmap_release(root, epics)
    try:
        return release.total(release.current())
    except Exception:
        return None


def roadmap_release(root=None, epics=None):
    """The percent of the features of the goals 1 to 3 of the roadmap that are done: "[x]", or a closed epic with its
    key ("Roadmap: `key`") or named on the line. None on a read error. `epics`: a test stub of the GitHub list."""
    try:
        with open(os.path.join(root or agent_config.ROOT, CONFIG["docs"]["roadmap"])) as f:
            features = {k: v for k, v in roadmap_features(f.read()).items() if v[0] < 4}
        if epics is None:
            import dashboard
            epics = lambda: dashboard.pages("issues?labels=epic&state=all")   # noqa: E731
        closed = [e for e in epics() if e.get("state") == "closed"]
    except Exception as e:                                  # a GitHub or file error: no release field
        print(f"release: {e}", file=sys.stderr)
        return None
    keys, numbers = {epic_key(e.get("body")) for e in closed}, {e["number"] for e in closed}
    done = sum(d or k in keys or bool(named & numbers) for k, (_, d, named) in features.items())
    return 100 * done / len(features) if features else None


def describe(usage, now, burn=BURN, burn7=None):
    out = []
    for k, (used, reset, status) in sorted(usage.items()):
        at = datetime.datetime.fromtimestamp(reset, datetime.timezone.utc)
        out.append(f"{k} {used:.0%} (resets {at:%a %H:%M} UTC, {(reset - now) / 3600:.1f} h, {status})")
    week = week_line(usage, now) + (f" · burn7 {burn7:.4f}" if burn7 else "")
    return " · ".join(out + [week] * bool(week)) + f" · burn {burn:.3f} · max {HI} runs · target {target_runs(usage, now, burn, burn7=burn7)} runs"


def fire(usage, now, burn=BURN, burn7=None, skip=(), status=None, started=None, out=None, target=None, account=None):
    """(K, {lane: runs}, line): the runs that the pacer starts now, and the line of its inputs (`--fire`,
    `framework/tools/pacer.py`). Reads GitHub and the claim refs. `skip`: lanes that can start no run now (the hourly limit
    of their task): they count no ready tickets, so the main runs get the room. `status`: read_status() of the
    burns, else it reads the status comments. `started`: {task: runs} that the pacer started in the last PENDING
    minutes; those with no claim yet (`pending`) count as claims and take a ready ticket of their lane each.
    `out`: a dict that gets the reads that the pacer uses again (`open`: the open issues and PRs, `refs`: the claim
    refs, `flow`: the cap of the flow brake, `claims`, `lanes`: the beating claims), so that it reads GitHub once.
    `target`: the target in Opus runs in place of `target_runs(usage)` (the pacer with several accounts, #4237)."""
    comments, note = status or read_status()
    import dashboard
    import health
    open_all = dashboard.pages("issues?state=open")
    paused = any({dashboard.STATUS, dashboard.PAUSED} <= set(dashboard.labels(i)) for i in open_all)
    ready = len(dashboard.candidates(open_all, reserved=()))   # all lanes: lane_plan splits them
    t = datetime.datetime.now(datetime.timezone.utc)
    refs = health.claim_refs()
    lanes = None if refs is None else health.count_lanes(refs, t, account=account)
    claims = health.active_claims(t) if lanes is None else sum(lanes.values())
    if out is not None:
        out.update(open=open_all, refs=refs, claims=claims, lanes=lanes)
    weights, source = health.lane_weights(comments)
    eq = claims if lanes is None else health.opus_equivalent(claims, lanes, weights)   # in Opus runs (#1727)
    target = target_runs(usage, now, burn, burn7=burn7) if target is None else target
    reviews = functools.cache(lambda: due_reviews(starved=lambda: target is not None and ready < target
                                                  and not free_sources()))
    need = refill_need(ready, target, open_all, release_due, free=free_sources, reviews=reviews,
                       now=now.timestamp() if hasattr(now, "timestamp") else now, closing=autoclosing)   # reviews after checks
    only_review = False
    if need and refill_recent(refs, now) and ready >= target // 2:
        # A refill runs now or ran; a near-empty queue refills at once. A due review skips the gap (owner, 2026-10-29):
        # its lock lets one run take it, and `pending` counts the started run until it claims.
        kinds = reviews()
        need, only_review = (" and ".join(kinds) + " due", True) if kinds else ("", False)
    refill = (1 if only_review else refill_runs(open_all, now)) if need else 0   # #3547: no refill run with no work
    refill_lane = "deep" if "deep" in dashboard.RESERVED else None
    wait = pending(started or {}, refs, now, refill_lane=refill_lane)
    eq += sum(n * weights.get(t, 1) for t, n in wait.items())
    lanes = [(n, 0 if n in skip else len(dashboard.candidates(open_all, lane=n)), weights[n]) for n in weights]   # agent.toml order
    extra = wait.get(refill_lane or "main", 0) - next((c for n, c, _ in lanes if n == refill_lane), 0) if refill_lane else 0
    refill = max(0, refill - max(0, extra))             # a pending run beyond the ready tickets of its lane refills
    lanes = [(n, max(0, c - wait.get(n, 0)), w) for n, c, w in lanes]
    k, runs = plan(target, eq, max(0, ready - sum(wait.values())), lanes, paused, refill=refill, refill_lane=refill_lane)
    cap, flow = read_flow(now)
    if out is not None:
        out["flow"], out["flow_reason"] = cap, flow
    if cap is not None:                                     # the flow is the bottleneck: Opus runs repair the PRs
        k, runs = min(k, cap), dict.fromkeys(runs, 0)
    line = (f"{describe(usage, now, burn, burn7)} · claims {claims} ({eq:.2f} Opus runs) · ready {ready} · "
            + (f"pending {json.dumps(wait)} · " if wait else "")
            + f"refill {refill} ({need or f'ready {ready}, target {target}: no refill source or a refill lock < {REFILL_GAP} min'}) · "
            f"paused {paused} · {flow} · max_fire {MAX_FIRE} · weights "
            + ", ".join(f"{n} {w:.2f} ({source[n]})" for n, w in weights.items()) + note)
    return k, runs, line


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", action="store_true", help="print only the number of runs")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sample", action="store_true", help="print the Usage: line for the run report")
    ap.add_argument("--burn", type=float, help="share of the 5-hour quota per run-hour (default: measured, else BURN)")
    ap.add_argument("--fire", action="store_true", help="print the number of runs that the pacer starts now")
    ap.add_argument("--flow", action="store_true", help="exit 1 when the flow brake is on (repair PRs, no new ticket)")
    a = ap.parse_args(argv)
    if a.flow:                                                  # no quota call: autopilot step 2 asks only this
        cap, reason = read_flow(datetime.datetime.now(datetime.timezone.utc).timestamp())
        print(reason)
        sys.exit(int(cap is not None))
    usage, now = read_usage(), datetime.datetime.now(datetime.timezone.utc).timestamp()
    if not usage:
        sys.exit("no rate_limit_event in the CLI output (no subscription, or the CLI changed)")
    if a.sample:
        import health
        t = datetime.datetime.now(datetime.timezone.utc)
        print(sample_line(usage, now, health.active_claims(t), release_percent(), health.lane_claims(t),
                          agent_config.account()))     # the quota of this run's own account (#4236)
        return
    status = read_status()
    burn, burn7 = burns(status[0], a.burn)
    if a.fire:
        k, runs, line = fire(usage, now, burn, burn7, status=status, account=agent_config.account())
        k, runs, line = 0, dict.fromkeys(runs, 0), "pacer.yml starts the runs: the session starts no run · " + line   # #3193, #3427
        print(k)
        for n, r in runs.items():
            print(f"{n} {r}")
        print(line, file=sys.stderr)
    elif a.target:
        print(target_runs(usage, now, burn, burn7=burn7))
    elif a.json:
        print(json.dumps({"usage": usage, "burn": burn, "burn7": burn7, "target": target_runs(usage, now, burn, burn7=burn7)}))
    else:
        print(describe(usage, now, burn, burn7))


if __name__ == "__main__":
    main()
