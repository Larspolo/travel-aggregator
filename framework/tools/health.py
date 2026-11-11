"""Numbers of the whole system for the `improve` skill: CI, environment, repository and scheduling (#242).

    python3 framework/tools/health.py              # the last 50 merged PRs (#2039)
    python3 framework/tools/health.py --hours 72   # a time window: the night runs, the quota
    python3 framework/tools/health.py --hours 24 --until 2026-10-26T05:15:00Z   # the 24 hours before a time (#489)
    python3 framework/tools/health.py --hours 6 --compare                        # the last 6 hours next to the 6 before (#1697)
    python3 framework/tools/health.py --prs 50 --compare   # the last 50 merged PRs next to the 50 before (#1909)
    python3 framework/tools/health.py --takeovers  # each takeover: the old run, its last report and the cause (#1703)

REST only (cloud sessions give 403 for GraphQL and `search/...`). Token and `gh` fallback as in
`framework/tools/dashboard.py`. The parsing functions take plain JSON, so the tests need no network.
"""
import argparse
import datetime
import difflib
import json
import math
import os
import re
import statistics
import subprocess
import sys
from collections import Counter

import numpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_config import CONFIG, first_account, owners  # noqa: E402
from dashboard import api, closes, merges, owner_work, start_after  # noqa: E402
from feedback import by_owner  # noqa: E402
from usage import STRETCH, epic_key  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CI_JOB_RUNS = 20                          # read the step times of this many CI runs (one API call each)
DENY = (".log", ".mca", ".png")           # suffixes that do not belong in git ...
DENY_OK = tuple(CONFIG.get("git", {}).get("png_ok", ("docs/", "samples/")))  # ... except .png here (#853)
BIG = 1 << 20
OWNER = CONFIG["owner"]                   # a reopen by an owner is rework (#899)
OWNERS = owners(CONFIG)                   # each login of `owners` (#4241)
STATUS = CONFIG["status"]["label"]
PRS = 50                                  # the default period: the last 50 merged PRs (#2039)
MISS_LABELS = {"cleanup", "process", "tooling"}   # an owner ticket of these kinds is a miss of the improve loop (#1909)


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def minutes(a, b):
    return (ts(b) - ts(a)).total_seconds() / 60


def med(xs):
    return statistics.median(xs) if xs else None


def ci_runs(runs, since):
    """{workflow: (count, median min, max min, failures)} of the completed runs that started after `since`."""
    by = {}
    for r in runs:
        if r.get("status") == "completed" and ts(r["run_started_at"]) >= since:
            by.setdefault(r["name"], []).append(r)
    out = {}
    for name, rs in sorted(by.items()):
        m = [minutes(r["run_started_at"], r["updated_at"]) for r in rs]
        out[name] = (len(rs), med(m), max(m), sum(r["conclusion"] == "failure" and not held(r) for r in rs))
    return out


def loop_gaps(runs, since, until):
    """(longest gap, sum of the gaps) in hours with no live run of `runs` between `since` and `until`: the pacer loop
    died quietly twice in 12 hours, and the owner started it by hand (#4647). A run that did not start (queued, held)
    counts as no run; a live run lasts to `until`."""
    spans = sorted((max(ts(r["run_started_at"]), since), min(until, ts(r["updated_at"]) if r.get("status") == "completed"
                    else until)) for r in runs if r.get("status") in ("completed", "in_progress") and r.get("run_started_at"))
    gaps, t = [], since
    for a, b in spans:
        if a > t:
            gaps.append((a - t).total_seconds() / 3600)
        t = max(t, b)
    if until > t:
        gaps.append((until - t).total_seconds() / 3600)
    return max(gaps, default=0.0), sum(gaps)


def idle_queue(cycles, until):
    """(longest, sum, no work) in hours of the idle stretches of the pacer `cycles` (dicts of `pacer/YYYY-MM-DD.jsonl`):
    the consecutive cycles with `target` > 0, no claim and no started run, from the first one to the next cycle that is
    not idle (or `until`). The queue stood still for hours on 2026-10-31 while the pacer loop ran (#5199). A paused
    project is not idle. "No work": the hours of the idle cycles with `ready` 0 and `refill` 0, each until the next
    cycle: the queue had no ticket and the refill no source (each ticket waited for the owner, 19.7 h on 2026-11-03,
    #854), so no fault of the pacer. A cycle whose roadmap review waits only for the clock of the idle stretch
    (`usage.STRETCH`, #491) is idle with work: the review can make new epics."""
    stretches, start, dry = [], None, 0.0
    rows = sorted(cycles, key=lambda c: c["at"])
    for i, c in enumerate(rows):
        idle = (c.get("target", 0) > 0 and not c.get("claims") and not sum((c.get("started") or {}).values())
                and "paused True" not in c.get("line", ""))
        if idle and start is None:
            start = ts(c["at"])
        elif not idle and start is not None:
            stretches.append((ts(c["at"]) - start).total_seconds() / 3600)
            start = None
        if idle and not c.get("ready") and not c.get("refill") and STRETCH not in c.get("line", ""):
            end = ts(rows[i + 1]["at"]) if i + 1 < len(rows) else until
            dry += max(0.0, (end - ts(c["at"])).total_seconds() / 3600)
    if start is not None:
        stretches.append(max(0.0, (until - start).total_seconds() / 3600))
    return max(stretches, default=0.0), sum(stretches), dry


def held(r):
    """GitHub held the run: it waits for an approval (#4645), or it is the pull_request run of a push of
    github-actions[bot] (Unconflict), which GitHub ends with 0 jobs (29 of 29 runs, #4988): no red CI."""
    return ("action_required" in (r.get("status"), r.get("conclusion")) or r.get("status") == "waiting"
            or r.get("event") == "pull_request" and (r.get("actor") or {}).get("login") == "github-actions[bot]"
            and r.get("conclusion") != "success")


AGENT_BRANCH = ("claude/", "agent/", "ccr-")   # the branches of agent PRs (`cycle_start.py`, #3382)


def run_rerun(r):
    """A run started this run again: a pull_request CI run on an agent branch (autopilot step 6.9: a flake gets one
    re-run of its failed jobs, #2349). GitHub gives the same actor for the owner and the runs."""
    return (r.get("name") == "CI" and r.get("event") == "pull_request"
            and (r.get("head_branch") or "").startswith(AGENT_BRANCH))


def held_runs(runs):
    """({workflow: runs that GitHub held}, {workflow: runs that a person started again}): a held run waits for an
    approval (#4645: GitHub held the pacer runs that read `toJSON(secrets)` as "may be malicious"); an attempt 2 or
    more is owner work (lever 9), but not the re-run of a flake by a run (`run_rerun`, #2349)."""
    held_ = Counter(r["name"] for r in runs if held(r))
    again = Counter(r["name"] for r in runs if r.get("run_attempt", 1) > 1 and not run_rerun(r))
    return dict(held_), dict(again)


def run_reruns(runs):
    """{workflow: runs that a run started again after a flake} (`run_rerun`, #2349)."""
    return dict(Counter(r["name"] for r in runs if r.get("run_attempt", 1) > 1 and run_rerun(r)))


def slow_steps(jobs, n=3):
    """[(median min, "job / step")] of the n slowest steps over all jobs (the `jobs` lists of several runs). The jobs of
    a matrix (`browser (1)`, `browser (2)`, #1062) count as one job."""
    times = {}
    for job in jobs:
        for s in job.get("steps", []):
            if s.get("started_at") and s.get("completed_at"):
                times.setdefault(f"{re.sub(r' [(].*[)]$', '', job['name'])} / {s['name']}", []).append(  # matrix jobs: one key
                    minutes(s["started_at"], s["completed_at"]))
    return sorted(((med(v), k) for k, v in times.items()), reverse=True)[:n]


def setup_minutes(comments):
    """The `setup <m> min` values of the `Metrics:` lines."""
    return [float(m) for c in comments for line in (c.get("body") or "").splitlines() if line.startswith("Metrics:")
            for m in re.findall(r"setup (\d+(?:\.\d+)?) min", line)]


def events(comments):
    """Counts of takeovers and merge conflicts in the issue and PR comments. A conflict counts only from
    the comments of the workflows: Automerge could not merge, or Unconflict solved it alone ("solved"). Run reports
    that only name a conflict counted 5 times too many (improve, run 145). No run comments "Released" now (a claim
    release is a commit on `claim/N`): only the release workflows do, so that is no count (#5649, `given_back`)."""
    bodies = [(c.get("body") or "").lstrip() for c in comments]
    return {"takeovers": sum(b.startswith("Taken over by") for b in bodies),
            "conflicts": sum(b.startswith("CI is green, but the merge failed") for b in bodies),
            "solved": sum(b.startswith("Merged `main` into the branch") for b in bodies)}


def claim_to_merge(prs, comments, since):
    """Minutes from the last "Started by" comment on the ticket to the merge, for PRs merged after `since`."""
    started = {}
    for c in comments:
        if (c.get("body") or "").startswith("Started by"):
            n = int(c["issue_url"].rsplit("/", 1)[1])
            started.setdefault(n, []).append(c["created_at"])
    out = []
    for pr in prs:
        if pr.get("merged_at") and ts(pr["merged_at"]) >= since:
            for n in closes(pr):
                before = [t for t in started.get(n, []) if t <= pr["merged_at"]]
                if before:
                    out.append(minutes(max(before), pr["merged_at"]))
    return out


def bad_files(files, png_ok=None):
    """[(path, bytes)] of the files over 1 MB or with a denied suffix. files: [(path, bytes)].

    A .png is allowed in the folders of `png_ok` (default: `png_ok` of `[git]` in `agent.toml`, #853)."""
    ok = DENY_OK if png_ok is None else tuple(png_ok)
    return [(p, size) for p, size in files if size > BIG
            or (p.endswith(DENY) and not (p.endswith(".png") and p.startswith(ok)))]


# `runs N` since #635 (claim beats); the older `claims N` lines counted too few runs, so they do not count.
SAMPLE = re.compile(r"^Usage: (\S+) · usage (\d+(?:\.\d+)?)% · resets (\S+) · runs (\d+)", re.M)


LANES = CONFIG.get("pacing", {}).get("weights", {"haiku": 0.25})   # start weight of a lane run in Opus runs (#1727)


def lane_runs(line):
    """{lane: runs} of the lane fields of a `Usage:` line (`· haiku 2`, #1727)."""
    return {k: int(v) for k, v in re.findall(r"· (\w+) (\d+)(?= ·|$)", line) if k in LANES}


ACCOUNT = re.compile(r" · account (\S+)")


def line_account(line):
    """The Claude account of a `Usage:` line (`· account NAME`, #4236); a line with no account word belongs to the
    first account of `[accounts]` (the lines before #4236)."""
    m = ACCOUNT.search(line)
    return m[1] if m else first_account()


def claim_account(subject):
    """The Claude account of a claim or beat message (` account NAME` before the lane, #4236), else the first account."""
    m = re.search(r" account (\S+)", subject)
    return m[1] if m else first_account()


def usage_lines(comments, account=None):
    """The `Usage:` lines of the comments; with `account`, only the lines of that account: each account has its own
    quota windows, so a pair of lines of two accounts gives no burn (#4236)."""
    return [line for c in comments for line in (c.get("body") or "").splitlines() if line.startswith("Usage:")
            and (account is None or line_account(line) == account)]


def raw_samples(comments, account=None):
    """[(time, 5-hour usage 0..1, reset time, all claims, {lane: claims})] of the `Usage:` lines (of one account), by
    time."""
    return sorted(((ts(m[1]), float(m[2]) / 100, ts(m[3]), int(m[4]), lane_runs(line))
                   for line in usage_lines(comments, account) for m in [SAMPLE.match(line)] if m),
                  key=lambda s: s[:4])                     # equal values: a dict has no order (#4434)


def lane_weights(comments, need=10):
    """({lane: weight}, {lane: "cost", "measured" or "start"}): the quota of one lane run in Opus runs. A lane with
    `need` runs with a `cost` (and as many Opus runs) gets the ratio of the median costs (#3457: the fit had an error
    of half its value), else the fit of lane_fit (#1727)."""
    weights, source = lane_fit(comments, need)[:2]
    costs = run_costs(comments)
    if len(costs.get("opus", ())) >= need and (base := numpy.median(costs["opus"])) > 0:
        for k in weights:
            if len(costs.get(k, ())) >= need:
                weights[k], source[k] = max(float(numpy.median(costs[k]) / base), 0.02), "cost"
    return weights, source


def lane_fit(comments, need=10):
    """({lane: weight}, {lane: "measured", "start" or "noisy, fit W"}, {lane: standard error}, pairs). Least squares of the
    5-hour usage rise of each interval on its Opus and lane claim-hours; a lane with fewer than `need` intervals with
    its runs keeps the start weight of `agent.toml` (#1727) and counts as that many Opus runs in the fit: else the
    usage of its runs goes to the other weights (#3137: 9 new deep runs moved the Haiku weight from 0.67 to 0.89). A fit whose standard error is larger than its weight keeps
    the start weight too ("noisy"): the weight of 50 PRs jumped from 0.40 to the clip 1.00 in 40 minutes (#2852)."""
    rows = []
    for a, b in zip(raw_samples(comments), raw_samples(comments)[1:]):
        h = (b[0] - a[0]).total_seconds() / 3600
        if abs((b[2] - a[2]).total_seconds()) < 600 and b[1] >= a[1] and h > 0:
            lane = {k: h * (a[4].get(k, 0) + b[4].get(k, 0)) / 2 for k in LANES}
            rows.append((b[1] - a[1], h * (a[3] + b[3]) / 2 - sum(lane.values()), lane))
    fit = [k for k in LANES if sum(r[2][k] > 0 for r in rows) >= need]
    weights, source, errors = dict(LANES), dict.fromkeys(LANES, "start"), {}
    if fit and sum(r[1] > 0 for r in rows) >= need:
        x = numpy.array([[r[1] + sum(w * r[2][k] for k, w in LANES.items() if k not in fit)] + [r[2][k] for k in fit]
                         for r in rows])
        y = numpy.array([r[0] for r in rows])
        b = numpy.linalg.lstsq(x, y, rcond=None)[0]
        dof = len(rows) - x.shape[1]
        if b[0] > 0 and dof > 0:
            cov = numpy.sum((y - x @ b) ** 2) / dof * numpy.linalg.pinv(x.T @ x)
            for i, k in enumerate(fit, 1):                                 # the error of b[i] / b[0] (delta method)
                g = numpy.zeros(len(b))
                g[0], g[i] = -b[i] / b[0] ** 2, 1 / b[0]
                w, errors[k] = b[i] / b[0], float(numpy.sqrt(max(g @ cov @ g, 0.0)))
                if errors[k] > abs(w):
                    source[k] = f"noisy, fit {w:.2f}"
                else:
                    weights[k], source[k] = min(max(w, 0.02), 1.0), "measured"
    return weights, source, errors, len(rows)


def opus_equivalent(claims, lanes, weights):
    """The claims of a sample in Opus runs: a lane run counts its weight."""
    return claims - sum(lanes.values()) + sum(weights.get(k, 1.0) * n for k, n in lanes.items())


def samples(comments, weights=None, account=None):
    """[(time, 5-hour usage 0..1, reset time, claims in Opus runs)] of the `Usage:` lines of the run reports (#462),
    by time; with `account`, only its lines (#4236: burn_pairs and burn_ratio then pair the lines of one account).
    A Haiku run counts its weight (#1727): else 2 hours of Haiku runs look like a plan upgrade (`ratio`)."""
    weights = weights or lane_weights(comments)[0]
    return [(t, u, r, opus_equivalent(k, lanes, weights)) for t, u, r, k, lanes in raw_samples(comments, account)]


def burn_pairs(samples, min_hours=0.25):
    """Share of the 5-hour quota that one run uses per hour, from each sample and the first later sample in the same
    window (the same reset time) at least `min_hours` later: the rise of the usage divided by the hours and the mean
    number of claims. Runs report a few minutes apart, so neighbours alone give almost no pairs (#571)."""
    out = []
    for i, a in enumerate(samples):
        b = next((b for b in samples[i + 1:] if abs((b[2] - a[2]).total_seconds()) < 600
                  and (b[0] - a[0]).total_seconds() >= min_hours * 3600), None)
        if b and b[1] >= a[1] and a[3] + b[3] > 0:
            out.append((b[1] - a[1]) / ((b[0] - a[0]).total_seconds() / 3600) / ((a[3] + b[3]) / 2))
    return out


def burn_ratio(samples, need=5):
    """Share of the 5-hour quota that one run uses per hour: the sum of the usage rises divided by the sum of the
    claim-hours (hours x mean claims) of consecutive samples in the same window, or None with fewer than `need` such
    intervals. Not a median of pairs: a pair with few claims gives a large value, because the runs between tickets
    and the other sessions also use the quota (0.111 against 0.059 on 2026-10-26, #582)."""
    out = []
    for a, b in zip(samples, samples[1:]):
        h = (b[0] - a[0]).total_seconds() / 3600
        if abs((b[2] - a[2]).total_seconds()) < 600 and b[1] >= a[1] and h > 0 and a[3] + b[3] > 0:
            out.append((b[0], b[1] - a[1], h * (a[3] + b[3]) / 2))
    return ratio(out, need)


DROP_HOURS = 2      # the period that shows a plan upgrade in the burn (#1706)


def ratio(intervals, need):
    """The sum of the rises divided by the sum of the claim-hours of the intervals [(end, rise, claim-hours)], or None
    with fewer than `need`. When the intervals of the last DROP_HOURS (at least `need`) give less than half of that,
    only they count: after a plan upgrade a run uses a smaller share of the larger quota at once, and the old intervals
    would keep the target too low for a day (#1706)."""
    def of(iv):
        return sum(r for _, r, _ in iv) / sum(c for _, _, c in iv) if len(iv) >= need else None
    whole = of(intervals)
    if whole:
        end = max(t for t, _, _ in intervals) - datetime.timedelta(hours=DROP_HOURS)
        last = of([i for i in intervals if i[0] > end])
        if last and last < whole / 2:
            return last
    return whole


WEEK_RUNS = re.compile(r"^Usage: (\S+) · .*?· runs (\d+) · week (\d+(?:\.\d+)?)%", re.M)


def weekly_burn(comments, now, hours=24, need=5, account=None):
    """Share of the 7-day quota that one run uses per hour (#1695): the sum of the rises of the 7-day usage of
    consecutive `Usage:` lines of the last `hours` (of one account, #4236), divided by their claim-hours, as
    burn_ratio. A drop is the 7-day reset. None with fewer than `need` intervals. A plan upgrade: `ratio`."""
    weights = lane_weights(comments)[0]                        # a Haiku run counts its weight (#1727)
    pts = sorted((ts(m[1]), opus_equivalent(int(m[2]), lane_runs(line), weights), float(m[3]) / 100)
                 for line in usage_lines(comments, account) for m in [WEEK_RUNS.match(line)] if m)
    pts = [p for p in pts if p[0] >= now - datetime.timedelta(hours=hours)]
    out = [(b[0], b[2] - a[2], (b[0] - a[0]).total_seconds() / 3600 * (a[1] + b[1]) / 2) for a, b in zip(pts, pts[1:])
           if b[2] >= a[2] and b[0] > a[0] and a[1] + b[1] > 0]
    return ratio(out, need) or None


def measured_burn(comments, now, hours=24, need=5, account=None):
    """The burn ratio of the samples of the last `hours` (of one account, #4236), or None when there are fewer than
    `need` intervals."""
    return burn_ratio([s for s in samples(comments, account=account) if s[0] >= now - datetime.timedelta(hours=hours)],
                      need)


PHASES = ("read", "claim", "code", "verify", "ci", "conflict", "report")    # the phase minutes of a Metrics line (#899)
WEEK = re.compile(r"^Usage: (\S+) · .*?· week (\d+(?:\.\d+)?)%(?: · release (\d+(?:\.\d+)?)%)?", re.M)


def phase_minutes(comments):
    """{phase: minutes} summed over the `phases read N · claim N ...` parts of the `Metrics:` lines. Old lines have no
    phases and add nothing."""
    out = dict.fromkeys(PHASES, 0.0)
    for c in comments:
        for line in (c.get("body") or "").splitlines():
            if line.startswith("Metrics:") and " phases " in line:
                for k, v in re.findall(r"\b([a-z]+) (\d+(?:\.\d+)?)\b", line.split(" phases ", 1)[1]):
                    if k in out:
                        out[k] += float(v)
    return out


def quota_rise(samples):
    """The rise of the 5-hour usage (0..1) over the samples, summed over consecutive samples in the same window."""
    return sum(b[1] - a[1] for a, b in zip(samples, samples[1:])
               if abs((b[2] - a[2]).total_seconds()) < 600 and b[1] >= a[1])


def quota_per_merge(samples, merged):
    """The rise of the 5-hour usage (0..1) per merged PR; None without merges or rises."""
    rise = quota_rise(samples)
    return rise / merged if merged and rise else None


def quota_per_dollar(samples, spent):
    """The rise of the 5-hour usage (0..1) per $ of the API list price of the runs; None without cost or rise (#1577).
    A rise of this number shows usage that the run reports do not explain: in one review the quota per merged PR went
    from 0.3 % to 1.0 %, but the run cost went up only 23 %."""
    rise = quota_rise(samples)
    return rise / spent if spent and rise else None


TOKENS = re.compile(r"^Tokens: (\d+(?:\.\d+)?)M eq · .*?· sinks (.*)$", re.M)


def token_lines(comments):
    """[(M eq, {sink: share 0..1})] of the `Tokens:` lines of the run reports (framework/tools/tokens.py, owner 2026-10-27)."""
    return [(float(m), {k: float(v) / 100 for k, v in re.findall(r"(\S.*?) (\d+)%(?:, |$)", sinks)})
            for c in comments for m, sinks in TOKENS.findall(c.get("body") or "")]


def token_sinks(lines, k=6):
    """[(sink, share of all eq)] of the k largest sinks over the `Tokens:` lines: the token bottleneck."""
    total, by = sum(m for m, _ in lines), {}
    for m, sinks in lines:
        for s, x in sinks.items():
            by[s] = by.get(s, 0) + m * x
    return sorted(((s, x / total) for s, x in by.items()), key=lambda kv: -kv[1])[:k] if total else []


VERIFY = re.compile(r"^Tokens: .*? · verify (.*?)(?: · force \d+)? · sinks ", re.M)


COST = re.compile(r"^Tokens: .*? · cost \$(\d+(?:\.\d+)?)", re.M)


def run_costs(comments):
    """{lane: [$ of each run]} of the `cost` fields of the `Tokens:` lines (framework/tools/tokens.py). The lane of a run is the
    `· lane NAME` of its `Metrics:` lines, else "opus" (as in `lanes`)."""
    out = {}
    for c in comments:
        body = c.get("body") or ""
        for cost in COST.findall(body):
            lane = re.search(r"^Metrics: .*?· lane (\w+)", body, re.M)
            out.setdefault(lane[1] if lane else "opus", []).append(float(cost))
    return out


def lane_shares(costs):
    """{lane: ($ sum, share of the $ of all lanes)} of `run_costs` (#1508). The median cost of a run hides the count of
    runs: the deep lane made 46 % of the cost of the runs in one period of 100 merged PRs, and 65 % in the next."""
    total = sum(map(sum, costs.values()))
    return {k: (sum(v), sum(v) / total if total else 0.0) for k, v in costs.items()}


FORCE = re.compile(r"^Tokens: .*? · force (\d+) · sinks ", re.M)


def refused_pushes(comments):
    """(refused force pushes, Tokens lines with a force field) of the run reports (framework/tools/tokens.py, #3461)."""
    found = [int(n) for c in comments for n in FORCE.findall(c.get("body") or "")]
    return sum(found), len(found)


def verify_minutes(comments):
    """{check kind: (minutes, count)} summed over the `verify` fields of the `Tokens:` lines (framework/tools/tokens.py, #1704)."""
    out = {}
    for c in comments:
        for field in VERIFY.findall(c.get("body") or ""):
            for k, m, n in re.findall(r"(\S.*?) (\d+(?:\.\d+)?)m (\d+)x(?:, |$)", field):
                a, b = out.get(k, (0.0, 0))
                out[k] = (a + float(m), b + int(n))
    return out


def weekly(comments):
    """[(time, 7-day usage %, release % or None)] of the `Usage:` lines that have the week (usage.py --sample), by time."""
    return sorted((ts(t), float(w), float(r) if r else None) for c in comments for t, w, r in WEEK.findall(c.get("body") or ""))


def release_per_week(points):
    """(release points per 1 % of 7-day quota, first release %, last release %) from weekly(), or None. The quota is
    the sum of the rises of the 7-day usage (a drop is its reset)."""
    pts = [p for p in points if p[2] is not None]
    used = sum(b[1] - a[1] for a, b in zip(pts, pts[1:]) if b[1] > a[1])
    return ((pts[-1][2] - pts[0][2]) / used, pts[0][2], pts[-1][2]) if len(pts) > 1 and used else None


RELEASE_MILESTONE = re.compile(r"v\d")


def milestone_per_week(issues, points):
    """(closed issues per 1 % of 7-day quota, closed issues, quota %, milestone titles) or None (#5552): the issues of a
    release milestone ("v0.1.0") that closed as done between the first and the last point of weekly(). The release bar
    stays at its level while the runs work only on the release focus, so this counts the work of the focus."""
    if len(points) < 2:
        return None
    used = sum(b[1] - a[1] for a, b in zip(points, points[1:]) if b[1] > a[1])
    done = [i for i in issues if "pull_request" not in i and i.get("closed_at") and i.get("state_reason") != "not_planned"
            and RELEASE_MILESTONE.match((i.get("milestone") or {}).get("title") or "")
            and points[0][0] <= ts(i["closed_at"]) <= points[-1][0]]
    return (len(done) / used, len(done), used, sorted({i["milestone"]["title"] for i in done})) if used else None


def features_per_week(issues, points):
    """(closed roadmap epics per 1 % of 7-day quota, closed epics, quota %) or None (#797): the issues with the label
    `epic` and a line "Roadmap: `key`" that closed as done between the first and the last point of weekly(). The
    release percent stays flat while each roadmap review adds features, so this counts the finished features."""
    if len(points) < 2:
        return None
    used = sum(b[1] - a[1] for a, b in zip(points, points[1:]) if b[1] > a[1])
    done = [i for i in issues if "pull_request" not in i and i.get("closed_at") and i.get("state_reason") != "not_planned"
            and "epic" in {lb["name"] for lb in i.get("labels", [])} and epic_key(i.get("body"))
            and points[0][0] <= ts(i["closed_at"]) <= points[-1][0]]
    return (len(done) / used, len(done), used) if used else None


def weak_spots(issues, events, prs, runs, since):
    """Counts that cost quality: issues that the owner reopened, bug tickets that name a PR merged since `since` and
    before the bug (rework: a PR that merged later is a blocked PR, not the cause, #5461), bug tickets that name a
    check ticket ("Check ..."), and failed night runs of CI."""
    new = [i for i in issues if "pull_request" not in i and ts(i["created_at"]) >= since]
    bugs = [i for i in new if "bug" in {lb["name"] for lb in i.get("labels", [])}]
    merged_at = {p["number"]: ts(p["merged_at"]) for p in prs if p.get("merged_at") and ts(p["merged_at"]) >= since}
    merged = lambda i: {n for n, t in merged_at.items() if t < ts(i["created_at"])}
    checks = {i["number"] for i in issues if i["title"].startswith("Check ")}
    named = lambda i: {int(n) for n in re.findall(r"#(\d+)", i.get("body") or "")}
    return {"reopened": sum(e["event"] == "reopened" and (e.get("actor") or {}).get("login") in OWNERS
                            and ts(e["created_at"]) >= since for e in events),
            "rework": sum(bool(named(i) & merged(i)) for i in bugs),
            "check bugs": sum(bool(named(i) & checks) for i in bugs),
            "red nights": sum(r["name"] == "CI" and r.get("event") == "schedule" and r.get("conclusion") == "failure"
                              and ts(r["run_started_at"]) >= since for r in runs)}


def lane_rework(issues, prs, comments, since):
    """{lane: (rework bug tickets, merged PRs)} (#5533): the rule of `rework` in weak_spots, by the lane of each PR. The
    lane of a PR is the lane of the first `Metrics:` line that names it (`· pr #N ·`, `· lane NAME`, else "opus")."""
    lane_of = {}
    for c in comments:
        for line in (c.get("body") or "").splitlines():
            m = re.match(r"Metrics: .*?· pr #(\d+) ·", line)
            if m:
                lane = re.search(r"· lane (\w+)", line)
                lane_of.setdefault(int(m[1]), lane[1] if lane else "opus")
    merged_at = {p["number"]: ts(p["merged_at"]) for p in prs if p.get("merged_at") and ts(p["merged_at"]) >= since
                 and p["number"] in lane_of}
    out = {k: [0, 0] for k in sorted({lane_of[n] for n in merged_at})}
    for n in merged_at:
        out[lane_of[n]][1] += 1
    for i in issues:
        if "pull_request" in i or ts(i["created_at"]) < since or "bug" not in {lb["name"] for lb in i.get("labels", [])}:
            continue
        hit = {int(n) for n in re.findall(r"#(\d+)", i.get("body") or "")} & \
            {n for n, t in merged_at.items() if t < ts(i["created_at"])}
        for k in {lane_of[n] for n in hit}:
            out[k][0] += 1
    return {k: tuple(v) for k, v in out.items()}


def misses(issues, since):
    """The numbers of the issues that the owner opened since `since` to change the system (a label of MISS_LABELS):
    each one is a change that the improve loop did not find itself (#1909). The agent writes with the owner's login
    too: its tickets have the footer, the GitHub App or the "## Goal" form of the `ticket` skill. The issue form of the
    owner starts with "### Goal"."""
    return sorted(i["number"] for i in issues if "pull_request" not in i and ts(i["created_at"]) >= since
                  and by_owner(i) and not (i.get("body") or "").lstrip().startswith("## Goal")
                  and MISS_LABELS & {lb["name"] for lb in i.get("labels", [])})


def time_waits(issues):
    """The open tickets whose "Start after:" line waits for a date, not for a count of merged PRs: a wait to measure a
    change must count work, because the speed of the project changes and a pause merges nothing (owner, 2026-10-29)."""
    return sorted(i["number"] for i in issues if "pull_request" not in i and i.get("state", "open") == "open"
                  and start_after(i))


def data_rows(path=None):
    """The (place, count) lines of the list of domain data that is still in the code (`[lint] data` of agent.toml,
    #1909; "#" starts a comment), or None when the project has no such list."""
    path = path or CONFIG.get("lint", {}).get("data")
    if not path or not os.path.exists(os.path.join(ROOT, path)):
        return None
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return [(p, int(n)) for p, n in (s.split() for s in f if s.strip() and not s.startswith("#"))]


def status_comments(hours=24, since=None):
    """The comments on the status issue of the last `hours` (or since `since`): the log on the branch `metrics`
    (`metrics_log.py`, #1983) and the API comments that changed after its newest one; the API alone without the log."""
    import metrics_log
    since = since or datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    stored = metrics_log.load(since)
    if stored is None:      # the run reports live only on the branch: the lines of the reports would read as 0
        print(f"warning: git cannot read the branch {metrics_log.BRANCH}: the run reports since {since:%Y-%m-%d %H:%M} "
              "are missing (Metrics, Tokens and Usage lines read as 0); run it again", file=sys.stderr)
    last = metrics_log.newest(stored or [])
    tail = metrics_log.api_comments(metrics_log.parse(last) if last else since)
    out = {c["id"]: c for c in (stored or []) + tail if c["created_at"] >= f"{since:%Y-%m-%dT%H:%M:%SZ}"}
    return sorted(out.values(), key=lambda c: (c["created_at"], c["id"]))


def count_beating(lines, now, minutes=25):
    """The tickets whose claim ref (top slot `N` or `N-k`) had a claim or beat in the last `minutes` and is not
    released. `lines`: "<slot> <commit time> <subject>" of the refs claim/<slot>."""
    return sum(count_lanes(lines, now, minutes).values())


def count_lanes(lines, now, minutes=25, account=None):
    """{lane: beating claims}: the lane is the ` lane NAME` at the end of the last claim or beat message, else
    "opus" (#1727). account: only the claims of that Claude account (` account NAME`; none: the first account, #4237)."""
    top = {}
    for line in lines:
        slot, t, subject = (line.split(" ", 2) + [""])[:3]
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", slot)
        if m and t.isdigit():
            n, k = int(m.group(1)), int(m.group(2) or 1)
            if n not in top or k > top[n][0]:
                top[n] = (k, int(t), subject)
    cut = now.timestamp() - minutes * 60
    out = {}
    for _, t, s in top.values():
        if t >= cut and not s.startswith("Release") and (account is None or claim_account(s) == account):
            name = re.search(r" lane (\w+)$", s)
            out[name[1] if name else "opus"] = out.get(name[1] if name else "opus", 0) + 1
    return out


def beating_claims(now, minutes=25, remote="origin"):
    """The runs that work now: runs beat at least every 20 minutes, also while they work long on one ticket and the
    issue does not change (#635). None when git cannot read the claim refs."""
    lanes = lane_claims(now, minutes, remote)
    return None if lanes is None else sum(lanes.values())


def claim_refs(remote="origin"):
    """The lines `<key> <unix time of the last beat> <subject>` of the claim refs, or None when git cannot read them."""
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT, timeout=60)
    try:  # a hung fetch (#3290) reads as a failed one
        if git("fetch", "-q", "--prune", remote, "+refs/heads/claim/*:refs/travel-aggregator-claims/*").returncode:
            return None
        out = git("for-each-ref", "refs/travel-aggregator-claims", "--format=%(refname:lstrip=2) %(committerdate:unix) %(subject)")
    except subprocess.TimeoutExpired:
        return None
    return out.stdout.splitlines() if out.returncode == 0 else None


def lane_claims(now, minutes=25, remote="origin"):
    """{lane: runs that work now} from the claim refs (#1727), or None when git cannot read them."""
    lines = claim_refs(remote)
    return None if lines is None else count_lanes(lines, now, minutes)


DROPPED = "dropped"                             # a lock that a later lock of its slot followed: the review did not finish (#3337)


def review_delays(lines, merged=None, since=None):
    """[(time, gap, PRs late, None or DROPPED)] of the review locks `review-<gap>pr-<last>-<k>` (framework/tools/claim.py --review,
    #898, #2039), by time. A review opens `gap` merged PRs after the review before it (#942): the PRs that merged after
    the last review `<last>` up to the lock, minus k gaps, are late, for example when no run reaches step 9 of the
    autopilot (a usage limit). The count starts at the lock before when `<last>` is none. merged: the merge times after
    `since`; None for the first lock and when the start is before `since` (the merge times do not cover it)."""
    at = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    slots = []
    for x in lines:
        k, t, *_ = x.split(" ", 2)
        m = re.match(r"review-(\d+)pr-([^-]*)-(\d+)$", k)
        if m:
            slots.append((at(int(t)), int(m[1]), m[2], int(m[3])))
    got = sorted(slots)
    out = []
    for i, (t, g, last, k) in enumerate(got):
        if any(g2 == g and last2 == last for _, g2, last2, _ in got[i + 1:]):
            out.append((t, g, DROPPED))             # a later lock of the same slot: this review was not finished
            continue
        try:
            start = datetime.datetime.strptime(last, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
        except ValueError:                          # none: the lock before (the first lock has no start)
            start = got[i - 1][0] if i else None
        out.append((t, g, None if merged is None or start is None or start < since else
                    sum(start < m <= t for m in merged) - k * g))
    return out


def late_text(late):
    """The "Review slots" value of a lock: its PRs late with a sign, `dropped`, or `-` (#3337)."""
    return "-" if late is None else late if isinstance(late, str) else f"{late:+d}"


def active_claims(now, minutes=30):
    """The runs that work now (rule 4 of the scheduled task): the claim beats, else the open tickets with
    `in-progress` that changed in the last `minutes`."""
    n = beating_claims(now)
    if n is not None:
        return n
    return sum(ts(i["updated_at"]) >= now - datetime.timedelta(minutes=minutes)
               for i in api("issues?state=open&labels=in-progress&per_page=100") if "pull_request" not in i)


def lanes(comments):
    """{lane: (runs, PRs, [minutes], [M eq])} of the run reports. The lane of a `Metrics:` line is its `· lane NAME`,
    else "opus"; the M eq is the `Tokens:` line of the same comment (#1715)."""
    out = {}
    for c in comments:
        body = c.get("body") or ""
        tok = TOKENS.search(body)
        for line in body.splitlines():
            m = re.match(r"Metrics: ticket #\d+ · [^·]* · ([^·]*?) · (\d+(?:\.\d+)?) min", line)
            if m:
                lane = re.search(r"· lane (\w+)", line)
                r = out.setdefault(lane[1] if lane else "opus", [0, 0, [], []])
                r[0] += 1
                r[1] += m[1].strip() == "merged" or m[1].startswith("pr #")
                r[2].append(float(m[2]))
                r[3] += [float(tok[1])] if tok else []
    return {k: tuple(v) for k, v in out.items()}


def next_effect(comments):
    """(runs that took a `next:` ticket, failed `next:` claims, M eq per first ticket, M eq per later ticket) of the run
    reports (#5308). A later ticket has `· source NAME` on its `Metrics:` line; the `Tokens:` eq of a report splits
    evenly over its tickets. The medians are None when no ticket of the kind has a `Tokens:` line."""
    took = failed = 0
    first, later = [], []
    for c in comments:
        body = c.get("body") or ""
        lines = re.findall(r"^Metrics: ticket #.*$", body, re.M)
        took += any(re.search(r"· source next\b", x) for x in lines)
        failed += sum(len(m.split()) for m in re.findall(r"^Next failed: (.*)$", body, re.M))
        if (tok := TOKENS.search(body)) and lines:
            for x in lines:
                (later if " · source " in x else first).append(float(tok[1]) / len(lines))
    return took, failed, med(first), med(later)


def given_back(comments):
    """{result: count} of the `Metrics:` lines whose ticket the run gave back with no PR (`none`, `blocked`,
    `needs-human`; `report.md`): the lost tickets of the runs (#5649). `ticket #0` is a deep run with no ticket (an
    epic check, a refill, a review): no lost ticket."""
    return dict(Counter(m[1] for c in comments for line in (c.get("body") or "").splitlines()
                        if (m := re.match(r"Metrics: ticket #[1-9]\d* · [^·]+ · (none|blocked|needs-human) ·", line))))


def back_causes(comments):
    """(checks, repeats) of the run reports (#5782): the `checked` results (a check put its findings on the ticket,
    which stays open by design, `report.md`), and {ticket: runs} of the tickets that 2 or more runs gave back or
    checked. 6 of 18 given-back runs of 100 PRs were one check ticket (#5604): a repeat is the cost to look at."""
    runs = Counter()
    checks = 0
    for c in comments:
        for line in (c.get("body") or "").splitlines():
            if m := re.match(r"Metrics: ticket #([1-9]\d*) · [^·]+ · (none|blocked|needs-human|checked) ·", line):
                runs[int(m[1])] += 1
                checks += m[2] == "checked"
    return checks, {n: k for n, k in sorted(runs.items(), key=lambda x: (-x[1], x[0])) if k > 1}


def pr_results(comments, prs):
    """The `pr #n` results of the `Metrics:` lines: (merged PRs, not merged PRs) by the present PR state (#902)."""
    merged = {p["number"] for p in prs if p.get("merged_at")}
    ns = sorted({int(n) for c in comments for line in (c.get("body") or "").splitlines() if line.startswith("Metrics:")
                 for n in re.findall(r"· pr #(\d+) ·", line)})
    return [n for n in ns if n in merged], [n for n in ns if n not in merged]


def fmt(x):
    return "-" if x is None else f"{x:.1f}"


def conflicted(comments):
    """The numbers of the PRs that Automerge could not merge because of a merge conflict (events)."""
    return sorted({int(c["issue_url"].rsplit("/", 1)[1]) for c in comments
                   if (c.get("body") or "").lstrip().startswith("CI is green, but the merge failed")})


def conflict_files(files_of, n=5, prefix=""):
    """The n files (names that start with prefix) that the most conflicted PRs change: where parallel tickets meet
    (files_of: PR -> file names)."""
    return Counter(f for fs in files_of.values() for f in set(fs) if f.startswith(prefix)).most_common(n)


RUN = re.compile(r"^(?:Started|Taken over) by [^`\n]*`([^`]+)`")   # also "by the pacer run (claim `B`)"
CAUSES = ("quota", "merge conflict", "long mc test", "red CI", "no report", "after the report")


def by_run(report, run):
    """True when `report` is a report of the run `run`: its name in backticks (a comment of the status issue), or the
    `branch` of a run record of the branch `metrics`, also with the suffix `-k` of a later ticket of the same session
    (the Run: line has no backticks: each takeover counted as "no report" before)."""
    base = lambda b: re.sub(r"-\d+$", "", b or "")
    return f"`{run}`" in (report.get("body") or "") or (bool(report.get("branch")) and base(report["branch"]) == base(run))


def takeovers(comments, status_comments, prs=(), since=None, full=0.95, runs=()):
    """[(time, item, old run, minutes since its last report or None, cause)] of the "Taken over by" comments (#1703).
    The old run: the last other "Started by" or "Taken over by" branch on the item, its ticket or its PR, else the
    PR branch. Its report: a report after its start that names its branch or a PR branch of the item (the `Run:`
    line has no backticks, and a run of the pacer starts as `pacer-r...`) or a ticket of the item (`Metrics:`, #4777:
    28 of 33 "no report" takeovers had one). The first rule that matches gives the cause: a `Usage:` line at `full` or
    more after the old run started (quota), an Automerge merge failure or "conflict" in the takeover text (merge
    conflict), `-m mc` in the last report of the old run (long mc test), a failure of the last CI run of a PR branch of
    the item in `runs` (red CI), no report of the old run after its start (the session ended in the ticket: no
    report), else the run reported and did not come back (after the report)."""
    num = lambda c: int(c["issue_url"].rsplit("/", 1)[1])
    by_pr = {p["number"]: p for p in prs}
    out = []
    for t in sorted((c for c in comments if (c.get("body") or "").lstrip().startswith("Taken over by")),
                    key=lambda c: c["created_at"]):
        when, item = t["created_at"], num(t)
        if since is not None and ts(when) < since:
            continue
        if not (m := RUN.match(t["body"].lstrip())):
            continue                                        # free text with no branch name: no run to count
        new = m[1]
        rel = {item} | closes(by_pr.get(item, {})) | {n for n, p in by_pr.items() if item in closes(p)}
        prior = [(c["created_at"], m[1]) for c in comments if num(c) in rel and c["created_at"] < when
                 for m in [RUN.match((c.get("body") or "").lstrip())] if m and m[1] != new]
        start, old = max(prior) if prior else (None, by_pr.get(item, {}).get("head", {}).get("ref", "?"))
        after = lambda c: c["created_at"] < when and (start is None or c["created_at"] >= start)
        heads = {old} | {p["head"]["ref"] for n, p in by_pr.items() if n in rel and p.get("head")}
        mine = re.compile("|".join([rf"`{re.escape(b)}`|\bbranch {re.escape(b)}(?:\s|$)" for b in heads]
                                   + [rf"\bticket #{n}\b" for n in rel]))
        reports = sorted((c for c in status_comments if after(c) and (mine.search(c.get("body") or "") or by_run(c, old))),
                         key=lambda c: c["created_at"])
        last = reports[-1] if reports else None
        ci = [r for r in runs if r.get("name") == "CI" and r.get("head_branch") in heads and after(r) and not held(r)]
        if any(s[1] >= full for s in raw_samples([c for c in status_comments if after(c)])):
            cause = "quota"
        elif "conflict" in t["body"] or any(num(c) in rel and after(c) and (c.get("body") or "").lstrip().startswith(
                "CI is green, but the merge failed") for c in comments):
            cause = "merge conflict"
        elif last and "-m mc" in last["body"]:
            cause = "long mc test"
        elif ci and max(ci, key=lambda r: r["created_at"]).get("conclusion") == "failure":
            cause = "red CI"
        else:
            cause = "after the report" if last else "no report"
        out.append((when, item, old, None if last is None else round(minutes(last["created_at"], when)), cause))
    return out


def takeover_lines(rows):
    """One line for each takeover and one line with the count of each cause."""
    k = Counter(r[4] for r in rows)
    return [f"  {w[:16].replace('T', ' ')} #{i} {old}: last report {'-' if m is None else f'{m} min'} before, {c}"
            for w, i, old, m, c in rows] + \
        ["Takeover causes: " + (", ".join(f"{c} {k[c]}" for c in CAUSES if k[c]) or "-")]


def report(since, runs, jobs, status_comments, comments, prs, files, files_of=None, issues=(), issue_events=(),
           unanswered=None, reviews=None, data_rows=None, owner=None, waits=None, loop=None, idle=None):
    out = [f"Health since {since:%Y-%m-%d %H:%M} UTC", "", "CI runs (count, median min, max min, failures):"]
    for name, (k, m, mx, fail) in ci_runs(runs, since).items():
        out.append(f"  {name}: {k}, {fmt(m)}, {fmt(mx)}, {fail}")
    if loop is not None:                        # a dead pacer loop starts no run (#4647): (longest, sum, hours)
        out.append(f"Pacer loop gaps (no live run, #4647): longest {loop[0]:.1f} h, sum {loop[1]:.1f} h of {loop[2]:.1f} h")
    if idle is not None:                        # the loop runs, but it starts nothing (#5199): (longest, sum, no work)
        out.append(f"Idle queue (target > 0, no claim, no start): longest {idle[0]:.1f} h, sum {idle[1]:.1f} h"
                   f" (no work: {idle[2]:.1f} h, #854)")
    held, again = held_runs(runs)
    out.append("Runs held by GitHub (#4645): " + (", ".join(f"{k} {v}" for k, v in sorted(held.items())) or "0")
               + " · started again by hand: " + (", ".join(f"{k} {v}" for k, v in sorted(again.items())) or "0"))
    out.append("CI re-runs of the runs (a flake, autopilot 6.9, #2349; no owner work): "
               + (", ".join(f"{k} {v}" for k, v in sorted(run_reruns(runs).items())) or "0"))
    out.append("Slowest CI steps (median min): " + "; ".join(f"{k} {fmt(m)}" for m, k in slow_steps(jobs)))
    setup = setup_minutes(status_comments)
    out.append(f"Setup (median min of {len(setup)} Metrics lines): {fmt(med(setup))}")
    ok, lost = pr_results(status_comments, prs)
    out.append(f"Metrics lines with pr #n: merged {len(ok)}, not merged {len(lost)}"
               + (f" ({', '.join(f'#{n}' for n in lost)})" if lost else ""))
    e = events(comments)
    back = given_back(status_comments)
    out.append(f"Takeovers {e['takeovers']}, given back {sum(back.values())}"
               + (f" ({', '.join(f'{k} {v}' for k, v in sorted(back.items()))})" if back else "")
               + f", merge conflicts {e['conflicts']} (solved by Unconflict {e['solved']})")
    checks, again = back_causes(status_comments)
    out.append(f"Checks with findings {checks} · tickets given back or checked 2+ times: "
               + (", ".join(f"#{n} {k}" for n, k in again.items()) or "0"))
    out.append(takeover_lines(takeovers(comments, status_comments, prs, since, runs=runs))[-1])
    if files_of:
        out.append(f"Files of the {len(files_of)} conflicted PRs (PRs): "
                   + "; ".join(f"{f} {k}" for f, k in conflict_files(files_of)))
        shared = [(f, k) for f, k in conflict_files(files_of, prefix="tests/") if k > 1]
        if shared:                                         # a count or a list of the data in a test (owner, #2008)
            out.append("Test files of 2 or more conflicted PRs (PRs): " + "; ".join(f"{f} {k}" for f, k in shared))
    s = [x for x in samples(status_comments) if x[0] >= since]
    b, r = burn_pairs(s), burn_ratio(s)
    out.append(f"Burn per run-hour (ratio of sums of {len(s)} Usage lines, used by usage.py): "
               f"{'-' if r is None else f'{r:.3f}'} · median of {len(b)} pairs: {'-' if not b else f'{med(b):.3f}'}")
    ph = phase_minutes(status_comments)
    total = sum(ph.values())
    out.append("Phases (min, share of the Metrics lines with phases): " + ("; ".join(
        f"{k} {fmt(v)} ({v / total:.0%})" for k, v in ph.items()) if total else "-"))
    merged = sum(1 for p in prs if p.get("merged_at") and ts(p["merged_at"]) >= since)
    q = quota_per_merge(s, merged)
    out.append(f"Quota per merged PR: {'-' if q is None else f'{q:.1%}'} of the 5-hour window ({merged} merged)")
    tl = token_lines(status_comments)
    out.append(f"Tokens per run (median of {len(tl)} Tokens lines): {fmt(med([m for m, _ in tl]))}M eq"
               + (f" · per merged PR {sum(m for m, _ in tl) / len(ok):.2f}M eq" if tl and ok else "")
               + " · largest sinks: " + ("; ".join(f"{s} {x:.0%}" for s, x in token_sinks(tl)) or "-"))
    vm = sorted(verify_minutes(status_comments).items(), key=lambda kv: -kv[1][0])
    out.append("Verify commands (min, count, of the Tokens lines with a verify field): "
               + ("; ".join(f"{k} {fmt(m)} ({n}x)" for k, (m, n) in vm) or "-"))
    out.append("Refused force pushes (of the {1} Tokens lines with a force field, #3461): {0}".format(
        *refused_pushes(status_comments)))
    costs = run_costs(status_comments)
    spent = sum(map(sum, costs.values()))
    out.append(f"API list price of the runs (the `cost` of {sum(map(len, costs.values()))} Tokens lines): ${spent:.0f}"
               + (f" · per merged PR ${spent / len(ok):.2f}" if spent and ok else ""))
    qd = quota_per_dollar(s, spent)
    out.append("Quota per $ of the run cost (usage that the runs do not explain, #1577): "
               + ("-" if qd is None else f"{qd:.2%} of the 5-hour window per $"))
    shares = lane_shares(costs)
    for name, (n, pr, mins, eq) in sorted(lanes(status_comments).items()):
        out.append(f"Lane {name}: {n} runs, {pr} PRs, median {fmt(med(mins))} min, median {fmt(med(eq))}M eq"
                   + (f", median ${med(costs[name]):.2f} per run, sum ${shares[name][0]:.0f}"
                      f" ({shares[name][1]:.0%} of the cost)" if costs.get(name) else ""))
    took, nfail, first, later = next_effect(status_comments)
    out.append(f"Next tickets (#5308): {took} runs took a next: ticket, {nfail} failed next: claims, M eq per ticket:"
               f" first {fmt(first)}, later {fmt(later)}")
    weights, source, errors, pairs = lane_fit(status_comments)
    out.append(f"Lane weights (a lane run in Opus runs, #1727; {pairs} pairs, ± standard error, #2852): " + ", ".join(
        f"{k} {w:.2f}{f' ± {errors[k]:.2f}' if k in errors else ''} ({source[k]})" for k, w in weights.items()))
    week = [p for p in weekly(status_comments) if p[0] >= since]
    rw = release_per_week(week)
    out.append("Release per 1 % of 7-day quota: " + ("-" if rw is None else
               f"{rw[0]:.2f} points ({rw[1]:g} % to {rw[2]:g} %)"))
    mw = milestone_per_week(issues, week)
    out.append("Release milestone per 1 % of 7-day quota (#5552): " + ("-" if mw is None else
               f"{mw[0]:.2f} closed issues ({mw[1]} closed in {', '.join(mw[3]) or '-'}, {mw[2]:g} % used)"))
    fw = features_per_week(issues, week)
    out.append("Features per 1 % of 7-day quota: " + ("-" if fw is None else
               f"{fw[0]:.2f} closed roadmap epics ({fw[1]} closed in {fw[2]:g} % used)"))
    w = weak_spots(issues, issue_events, prs, runs, since)
    out.append("Weak spots: " + ", ".join(f"{k} {v}" for k, v in w.items()))
    lr = lane_rework(issues, prs, status_comments, since)
    out.append("Rework per lane (bug tickets / merged PRs, #5533): " + (", ".join(
        f"{k} {b}/{n} ({b / n:.1%})" for k, (b, n) in lr.items()) or "-"))
    m = misses(issues, since)
    out.append(f"Misses (owner tickets for the system, improve step 0): {len(m)}"
               + (f" ({', '.join(f'#{n}' for n in m)})" if m else ""))
    if owner is not None:                       # the work of owner sessions: misses too (owner, 2026-10-29)
        out.append(f"Owner work (merged PRs with no run commit, improve step 0): {len(owner)}"
                   + (f" ({'; '.join(f'#{n} {t}' for n, t in owner)})" if owner else ""))
    if waits is not None:
        out.append(f"Time waits (open tickets with a date in Start after:): {len(waits)}"
                   + (f" ({', '.join(f'#{n}' for n in waits)})" if waits else ""))
    if data_rows is not None:                   # the list only gets shorter (#1909)
        out.append(f"Data in the code ([lint] data of agent.toml): {sum(n for _, n in data_rows)} literals "
                   f"in {len(data_rows)} places")
    if reviews is not None:                     # the self-improvement loop: each slot gets its review in time (#942)
        out.append("Review slots (taken UTC, gap PRs, PRs late): " + ("; ".join(
            f"{t:%m-%d %H:%M} {m} {late_text(late)}" for t, m, late in reviews if t >= since) or "-"))
    c2m = claim_to_merge(prs, comments, since)
    out.append(f"Claim to merge (median min of {len(c2m)} PRs): {fmt(med(c2m))}")
    bad = bad_files(files)
    out.append(f"Files that do not belong in git: {len(bad)}")
    out += [f"  {p} ({size // 1024} KiB)" for p, size in bad]
    if unanswered is not None:                  # a quality number: each owner comment gets an answer (#971)
        out.append(f"Owner comments without an answer (framework/tools/feedback.py): {len(unanswered)}")
    return "\n".join(out)


def git_files():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    paths = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, text=True,
                           check=True).stdout.split("\0")
    return [(p, os.path.getsize(os.path.join(root, p))) for p in paths if p and os.path.isfile(os.path.join(root, p))]


def quick_ci_runs(created, seen, pages=10):
    """The runs of the quick CI (`ci.yml`) in the time `created` that are not in `seen` (ids). The 10 pages of all
    runs end at about 1000 runs (the Dashboard runs fill 10 pages a day): on the window of 100 merged PRs, the CI runs
    of the first hours were cut, and 2 "red CI" takeovers counted as "after the report" (#1800)."""
    out = []
    for page in range(1, pages + 1):
        rs = api(f"actions/workflows/ci.yml/runs?per_page=100&page={page}&created={created}")["workflow_runs"]
        out += [r for r in rs if r["id"] not in seen]
        if len(rs) < 100:
            break
    return out


def fetch(since, until=None):
    iso = f"{since:%Y-%m-%dT%H:%M:%SZ}"
    created = f"{iso}..{until:%Y-%m-%dT%H:%M:%SZ}" if until else f">={iso}"   # the Dashboard runs fill 10 pages a day
    runs = []
    for page in range(1, 11):
        rs = api(f"actions/runs?per_page=100&page={page}&created={created}")["workflow_runs"]
        runs += rs
        if len(rs) < 100:
            break
    runs += quick_ci_runs(created, {r["id"] for r in runs})
    ci = [r for r in runs if r["name"] == "CI" and r.get("status") == "completed"][:CI_JOB_RUNS]
    jobs = [j for r in ci for j in api(f"actions/runs/{r['id']}/jobs")["jobs"]]
    # one day more: the "Started by" comment of a ticket that merged in the period can be older
    comments = api_pages(f"issues/comments?since={since - datetime.timedelta(days=1):%Y-%m-%dT%H:%M:%SZ}", COMMENT_PAGES)
    reports = status_comments(since=since)        # the log and the API (#1982, #1983)
    recent = [c for c in comments if c["created_at"] >= iso or c["body"].startswith("Started by")]
    prs = api_pages("pulls?state=closed&sort=updated&direction=desc", stop=lambda p: p["updated_at"] < iso)
    issues = api_pages(f"issues?state=all&since={iso}")
    events = api_pages("issues/events?", limit=event_pages(since), stop=lambda e: e["created_at"] < iso)
    return runs, jobs, reports, recent, prs, issues, events


def owner_and_waits(since, until=None):
    """The owner work merged in the period (`dashboard.owner_work`) and the time waits of the open tickets."""
    return owner_work(merges(since=since, until=until, messages=True)), time_waits(api_pages("issues?state=open"))


def clip(until, runs, status_comments, comments, prs, issues, events):
    """The items up to `until`: a period in the past ends there (--until, #489). A PR that closed later was open."""
    early = lambda t: t is not None and ts(t) < until
    return ([r for r in runs if early(r["created_at"])], [c for c in status_comments if early(c["created_at"])],
            [c for c in comments if early(c["created_at"])], [p for p in prs if early(p.get("closed_at"))],
            [i for i in issues if early(i["created_at"])], [e for e in events if early(e["created_at"])])


EVENT_PAGES_PER_DAY = 170   # 107 pages of issue events in 24 hours (2026-10-28, 22:56 UTC), newest first (#2005, #3433)


def event_pages(since, now=None):
    """The page limit of `issues/events?` from now back to since: EVENT_PAGES_PER_DAY for each 24 hours."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return max(5, math.ceil((now - since).total_seconds() / 86400 * EVENT_PAGES_PER_DAY))


COMMENT_PAGES = 100   # the repository has about 1100 comments a day: 20 pages cut the last hours of 2 days (#1717)


def api_pages(path, limit=20, stop=None):
    out = []
    for page in range(1, limit + 1):
        items = api(f"{path}&per_page=100&page={page}")
        out += items
        if len(items) < 100 or (stop and stop(items[-1])):
            break
    else:
        print(f"health: {path} stopped at {limit} pages: items of the period are missing", file=sys.stderr)
    return out


def utc(s):
    """An ISO time; a time without a zone is UTC (`--until 2026-10-27T01:00`, #1697)."""
    t = ts(s)
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def period(until, hours, past, only_takeovers=False):
    """The report of the `hours` before `until`; `past`: the period ends before now, so clip the items after it.
    `only_takeovers`: only the takeover lines (#1703)."""
    since = until - datetime.timedelta(hours=hours)
    runs, jobs, status_comments, comments, prs, issues, events = fetch(since, until if past else None)
    if past:
        runs, status_comments, comments, prs, issues, events = clip(until, runs, status_comments, comments, prs,
                                                                    issues, events)
    if only_takeovers:                          # the open PRs too: their branch and ticket
        return "\n".join(takeover_lines(takeovers(comments, status_comments,
                                                   prs + api("pulls?state=open&per_page=100"), since,
                                                   runs=runs)))
    files_of = {n: [f["filename"] for f in api(f"pulls/{n}/files?per_page=100")] for n in conflicted(comments)}
    from feedback import fetch as unanswered
    refs = claim_refs()
    merged = sorted(t for p in prs if p.get("merged_at") and (t := ts(p["merged_at"])) >= since)
    text = report(since, runs, jobs, status_comments, comments, prs, git_files(), files_of, issues, events,
                  unanswered(), None if refs is None else review_delays(refs, merged, since), data_rows(),
                  *owner_and_waits(since, until if past else None), loop=pacer_loop(since, until), idle=pacer_idle(since, until))
    return text.replace(" UTC", f" UTC until {until:%Y-%m-%d %H:%M} UTC", 1) if past else text


def pacer_loop(since, until):
    """(longest gap, sum of the gaps, hours of the period) of the runs of pacer.yml; None with no such workflow. One
    call: the runs that started up to 6 hours before `since` too (a loop lasts 5.5 hours)."""
    created = f"{since - datetime.timedelta(hours=6):%Y-%m-%dT%H:%M:%SZ}..{until:%Y-%m-%dT%H:%M:%SZ}"
    try:
        runs = api(f"actions/workflows/pacer.yml/runs?per_page=100&created={created}")["workflow_runs"]
    except Exception as e:                      # a project with no pacer workflow
        print(f"health: no runs of pacer.yml ({e})", file=sys.stderr)
        return None
    return (*loop_gaps(runs, since, until), (until - since).total_seconds() / 3600)


def pacer_idle(since, until):
    """`idle_queue` of the pacer cycles between `since` and `until` (the branch `metrics`, `pacer/`); None when git
    cannot read the branch."""
    import metrics_log
    if metrics_log.git("fetch", "-q", "--depth", "1", "origin", "+refs/heads/metrics:refs/remotes/origin/metrics").returncode:
        return None
    cycles, d = [], since.date()
    while d <= until.date():
        r = metrics_log.git("show", f"origin/metrics:pacer/{d:%Y-%m-%d}.jsonl")
        for line in r.stdout.splitlines() if r.returncode == 0 else ():
            try:
                c = json.loads(line)
            except ValueError:
                continue
            if since <= ts(c["at"]) <= until:
                cycles.append(c)
        d += datetime.timedelta(days=1)
    return idle_queue(cycles, until)


def merge_times(n, until):
    """The merge times of the newest n + 1 PRs on the default branch up to `until`, newest first (`dashboard.merges`)."""
    return [t for t, _ in merges(until=until, n=n + 1)]


def pr_hours(times, until, n):
    """The hours of the last n merged PRs before `until` and of the n PRs before them (`--prs`, #1909). `times`: the
    merge times, newest first. A window of PRs keeps its size when the speed of the project changes; a window of hours
    does not (about 350 merges a day on 2026-10-27). A young repository has fewer merges: the oldest one ends the
    period, with a warning that names the count (#3072)."""
    if not times:
        sys.exit(f"no merged PR up to {until:%Y-%m-%dT%H:%M:%SZ}: use --hours")
    if len(times) < 2 * n + 1:
        print(f"warning: only {len(times)} merge times up to {until:%Y-%m-%dT%H:%M:%SZ}, {2 * n + 1} needed: "
              "the oldest merge ends the periods", file=sys.stderr)
    a, b = times[min(n, len(times) - 1)], times[min(2 * n, len(times) - 1)]
    return (until - a).total_seconds() / 3600, (a - b).total_seconds() / 3600


def compare(last, before):
    """The lines of two reports next to each other (#1697): a line of the last period, and under it the line of the
    period before when it differs (`  before: ...`). Lines pair by their name (the text before the first colon, digit or
    parenthesis)."""
    a, b = last.splitlines(), before.splitlines()
    key = lambda line: re.split(r"[:\d(]", line)[0]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [key(x) for x in a], [key(x) for x in b],
                                                      autojunk=False).get_opcodes():
        if op == "equal":
            for x, y in zip(a[i1:i2], b[j1:j2]):
                out += [x] + [f"  before: {y.strip()}"] * (x != y)
        else:
            out += a[i1:i2] + [f"  before: {y.strip()}" for y in b[j1:j2]]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hours", type=float, help="a period of hours, not of merged PRs (the night runs, the quota)")
    ap.add_argument("--prs", type=int, help="the period of the last N merged PRs (default 50 without --hours, #1909)")
    ap.add_argument("--until", type=utc, help="the end of the period (ISO time, UTC, default now): compare two periods")
    ap.add_argument("--compare", action="store_true", help="also the period before, under each line that differs")
    ap.add_argument("--takeovers", action="store_true", help="one line for each takeover and its cause (#1703)")
    a = ap.parse_args(argv)
    until = a.until or datetime.datetime.now(datetime.timezone.utc)
    hours = before = a.hours
    if a.prs or not a.hours:                     # a count of merged PRs measures the same work at each speed (#2039)
        a.prs = a.prs or PRS
        hours, before = pr_hours(merge_times(2 * a.prs, until), until, a.prs)
        print(f"Period: the last {a.prs} merged PRs ({hours:.1f} h), before: the {a.prs} PRs before ({before:.1f} h)")
    text = period(until, hours, bool(a.until), a.takeovers)
    if a.compare and not a.takeovers:
        text = compare(text, period(until - datetime.timedelta(hours=hours), before, True))
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
