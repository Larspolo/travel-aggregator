"""Build the data files of the owner's dashboard (travel-aggregator Autopilot) from GitHub and the repository.

    python3 tools/dashboard_data.py OUT_DIR

Writes the files of DATASETS: the merged PRs, the tickets, the epics, the roadmap, the usage, the tokens, the accounts,
the spend and the reviews, and copies the setup list (written by hand: tools/dashboard_artifact/setup.json). The page
reads them as data files: `tools/dashboard_site.py` builds the GitHub Pages site with them. The page and this file
come from the dashboard of the project aoe2mc (Larspolo/aoe2mc), without its release bar.

With `DASHBOARD_CACHE` (a folder that `dashboard-site.yml` keeps with `actions/cache`), it reads only the issues and
PRs that changed since the last build (`cached`): all issues and all closed PRs were about 60 API pages in each build,
6 builds an hour, and the REST limit of the workflow token ran out (2026-10-29). Once a day it reads all again.
"""
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "framework", "tools"))
import health  # noqa: E402

DATASETS = {"merges": "travel-merged-prs.json", "tickets": "travel-tickets.json", "epics": "travel-epics.json",
            "roadmap": "travel-roadmap.json", "release_bar": "travel-release-bar.json", "usage": "travel-usage.json",
            "tokens": "travel-tokens.json", "reviews": "travel-reviews.json", "setup": "travel-setup.json",
            "accounts": "travel-accounts.json", "spend": "travel-spend.json"}
ROWS = re.compile(r"\s*\.(filter|find|some|every|forEach|map|flatMap|sort)\(\s*\(?\s*(\w+)(?:\s*,\s*(\w+))?\s*\)?\s*=>")

GOALS = {"1": "capture", "2": "rank", "3": "trip", "4": "host"}   # the sections "## N." of steering/project/ROADMAP.md
KEY = re.compile(r"Roadmap:\s*`([a-z0-9:-]+)`")


def pages(path):
    out, page = [], 1
    while True:
        part = health.api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        out += part
        if len(part) < 100:
            return out
        page += 1


def ts(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


FULL_HOURS = 24             # a cache older than this reads all issues and PRs again (deleted or missed items)
OVERLAP = 120               # seconds: the next read starts this much before the start of this read


def slim(item):
    """The fields of an issue or a PR that the data files use: a small cache. The body only for an epic (`KEY`)."""
    names = [label["name"] for label in item.get("labels") or []]
    out = {k: item.get(k) for k in ("number", "title", "state", "created_at", "closed_at", "merged_at", "updated_at",
                                    "sub_issues_summary", "parent_issue_url")}
    out["labels"] = [{"name": n} for n in names]
    out["body"] = (item.get("body") or "") if "epic" in names else ""
    if "pull_request" in item:
        out["pull_request"] = {}
    if "head" in item:
        out["head"] = {"ref": item["head"]["ref"]}
    return out


def cached(folder, now=None, read=None):
    """(issues, closed PRs) as `pages` gives them, from the cache in `folder` and the items that changed since its
    last read: `issues?since=` and the closed PRs by update time until an older one. No cache, or a cache older than
    FULL_HOURS: all of them. Writes the cache back."""
    now, read = now or dt.datetime.now(dt.timezone.utc), read or pages
    path = os.path.join(folder, "items.json")
    try:
        with open(path) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    start = f"{now - dt.timedelta(seconds=OVERLAP):%Y-%m-%dT%H:%M:%SZ}"
    full = not c or c.get("full_at", "") < f"{now - dt.timedelta(hours=FULL_HOURS):%Y-%m-%dT%H:%M:%SZ}"
    issues, pulls = ({}, {}) if full else (c["issues"], c["pulls"])
    if full:
        new_issues, new_pulls = read("issues?state=all"), read("pulls?state=closed")
    else:
        new_issues = read(f"issues?state=all&since={c['since']}&sort=updated&direction=asc")
        new_pulls, page = [], 1
        while True:                                 # newest update first: stop at the first one before `since`
            part = health.api(f"pulls?state=closed&sort=updated&direction=desc&per_page=100&page={page}")
            new_pulls += [p for p in part if p["updated_at"] >= c["since"]]
            if len(part) < 100 or part[-1]["updated_at"] < c["since"]:
                break
            page += 1
    issues.update({str(i["number"]): slim(i) for i in new_issues})
    pulls.update({str(p["number"]): slim(p) for p in new_pulls})
    os.makedirs(folder, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"since": start, "full_at": start if full else c["full_at"], "issues": issues, "pulls": pulls}, f)
    return list(issues.values()), list(pulls.values())


def merged_prs(pulls):
    rows = sorted((p for p in pulls if p.get("merged_at")), key=lambda p: p["merged_at"])
    return [dict(number=p["number"], title=p["title"], branch=p["head"]["ref"], created_at=p["created_at"],
                 merged_at=p["merged_at"], minutes_open=round((ts(p["merged_at"]) - ts(p["created_at"])).total_seconds() / 60, 1))
            for p in rows]


def parent(issue):
    """The number of the epic of a sub-issue, else None: the history of the progress needs it."""
    url = issue.get("parent_issue_url")
    return int(url.rsplit("/", 1)[1]) if url else None


def tickets(issues):
    def pick(names, options):
        return next((n for n in names if n in options), "")
    out = []
    for i in sorted((i for i in issues if "pull_request" not in i), key=lambda i: i["number"]):
        names = [label["name"] for label in i["labels"]]
        subs = i.get("sub_issues_summary") or {}
        out.append(dict(number=i["number"], title=i["title"], state=i["state"], created_at=i["created_at"],
                        closed_at=i["closed_at"] or "", priority=pick(names, ("P0", "P1", "P2", "P3")),
                        kind=pick(names, ("bug", "feature", "tooling", "design", "docs", "cleanup")),
                        size=pick(names, ("size:S", "size:M", "size:L")).replace("size:", ""),
                        epic="epic" in names, status_issue="agent-status" in names, needs_human="needs-human" in names,
                        in_progress="in-progress" in names, blocked="blocked" in names, muted="muted" in names,
                        process="process" in names, haiku="lane:haiku" in names, subs_done=subs.get("completed") or 0,
                        subs_total=subs.get("total") or 0, parent=parent(i)))
    return out


def epics(issues):
    """The epics with the roadmap key of their body; the roadmap lines name the other epics of a feature."""
    out = []
    for i in issues:
        if "pull_request" in i or "epic" not in {label["name"] for label in i["labels"]}:
            continue
        subs = i.get("sub_issues_summary") or {}
        m = KEY.search(i.get("body") or "")
        out.append(dict(number=i["number"], title=i["title"], state=i["state"], closed_at=i["closed_at"] or "",
                        key=m[1] if m else "", subs_done=subs.get("completed") or 0, subs_total=subs.get("total") or 0))
    return sorted(out, key=lambda e: e["number"])


def roadmap(text):
    out, goal, order = [], None, 0
    for line in text.splitlines():
        h = re.match(r"## (\d)\. ", line)
        if h or line.startswith("## "):
            goal = GOALS.get(h[1]) if h else None
            continue
        f = re.match(r"- \[([ x])\] `([a-z0-9:-]+)` (.*)", line)
        if goal and f:
            order += 1
            feature = re.sub(r"\s*\((?:epic )?#[^)]*\)", "", f[3]).replace("`", "").strip()
            out.append(dict(id=f[2], goal=goal, order=order, key=f[2], feature=feature, checked=f[1] == "x",
                            refs=" ".join(re.findall(r"#(\d+)", f[3]))))
    return out


WEEK = dt.timedelta(days=7)
WEEK_RESET = re.compile(r"^Usage: (\S+) · .*?· week resets (\S+)", re.M)
WEEK_SLACK = 0.10       # "behind" when more than this share of the week stays unused at the reset


def week_track(used, reset, now, rate):
    """The on-track text of the 7-day usage `used` (0..1) at `now`, with the 7-day reset `reset` and the measured
    rise per hour `rate` (#1696): "on track", "ahead: runs out <day hh:mm>" or "behind: <n> % unused at the reset"."""
    at = used + rate * (reset - now).total_seconds() / 3600
    if at > 1:
        return f"ahead: runs out {now + dt.timedelta(hours=(1 - used) / rate):%a %H:%M}"
    if at < 1 - WEEK_SLACK:
        return f"behind: {round((1 - at) * 100)} % unused at the reset"
    return "on track"


def week_rate(points, now, hours=24):
    """The rise of the 7-day usage per hour over the points [(time, used)] of the last `hours` up to `now` (a drop is
    the reset), or None with less than one hour of points."""
    pts = [p for p in points if now - dt.timedelta(hours=hours) <= p[0] <= now]
    span = (pts[-1][0] - pts[0][0]).total_seconds() / 3600 if pts else 0
    return sum(max(0, b[1] - a[1]) for a, b in zip(pts, pts[1:])) / span if span >= 1 else None


def usage(hours=168, comments=None):   # 7 days: the chart "Merges per point of 7-day usage" shows all of it
    """The `Usage:` lines: the 5-hour usage, all runs `runs` and the Haiku lane runs `haiku` (#1727), and the 7-day
    usage `week` with its reset `week_resets` and the on-track text `track` where the line has the week (#1696), else
    None. A line before #1696 has no 7-day reset: the reset of another line moved by whole weeks (the 7-day window is
    fixed)."""
    comments = health.status_comments(hours=hours) if comments is None else comments
    week = {t: w / 100 for t, w, _ in health.weekly(comments)}
    known = sorted({health.ts(r) for c in comments for _, r in WEEK_RESET.findall(c.get("body") or "")})
    points, rows = sorted(week.items()), []
    for t, u, r, k, lanes in health.raw_samples(comments):          # the runs, not the Opus runs of the pacing
        row = dict(at=f"{t:%Y-%m-%dT%H:%M:%SZ}", usage=u, resets=f"{r:%Y-%m-%dT%H:%M:%SZ}", runs=k,
                   haiku=lanes.get("haiku", 0), week=week.get(t), week_resets=None, track=None)  # each column (check)
        if t in week and known:
            reset = known[-1] - WEEK * ((known[-1] - t) // WEEK)
            rate = week_rate(points, t)
            row.update(week=week[t], week_resets=f"{reset:%Y-%m-%dT%H:%M:%SZ}",
                       track=None if rate is None else week_track(week[t], reset, t, rate))
        rows.append(row)
    return rows


TOKEN_LINE = re.compile(r"^Tokens: (\d+(?:\.\d+)?)M eq · calls (\d+) · .*?· peak (\d+)k(?: .*?sinks base (\d+)%)?", re.M)
RESULT = re.compile(r"^Metrics: ticket #\d+ · [^·]* · (merged|pr #\d+)", re.M)


def tokens(hours=168, comments=None):
    """The cost of each run report with a `Tokens:` line (framework/tools/tokens.py): its M eq, calls, peak context in k tokens,
    the share 0..1 of the sink `base` (None when not in the top sinks) and its PRs (the `Metrics:` lines with the
    result `merged` or `pr #N`). The chart "Usage per merged PR" divides the eq by the PRs (owner, 2026-10-29)."""
    comments = health.status_comments(hours=hours) if comments is None else comments
    rows = []
    for c in comments:
        body = c.get("body") or ""
        m = TOKEN_LINE.search(body)
        if m and c.get("created_at"):
            rows.append(dict(at=c["created_at"], eq=float(m[1]), calls=int(m[2]), peak=int(m[3]),
                             base=int(m[4]) / 100 if m[4] else None, prs=len(RESULT.findall(body))))
    return sorted(rows, key=lambda r: r["at"])


RUN_LINE = re.compile(r"^Run: .*$", re.M)
WEEK_USED = re.compile(r" · week (\d+(?:\.\d+)?)%")


def accounts(hours=168, comments=None):
    """One row per Claude account (#4239): its last 5-hour usage, 7-day usage and runs (the last `Usage:` line of the
    account), its merged PRs and tokens per merged PR. A `Run:` line names the account of its report (`health.line_account`:
    a line with no account word belongs to the first account). Values of an account with no line are None."""
    comments = health.status_comments(hours=hours) if comments is None else comments
    rows = {}
    for c in sorted(comments, key=lambda c: c.get("created_at") or ""):
        body = c.get("body") or ""
        run = RUN_LINE.search(body)
        owner = health.line_account(run[0]) if run else health.first_account()
        for line in body.splitlines():
            m = health.SAMPLE.match(line) if line.startswith("Usage:") else None
            if m:
                week = WEEK_USED.search(line)
                rows.setdefault(health.line_account(line), {}).update(
                    five_hour=float(m[2]) / 100, runs=int(m[4]), week=float(week[1]) / 100 if week else None)
        t = TOKEN_LINE.search(body)
        if t:
            acc = rows.setdefault(owner, {})
            acc["eq"], acc["prs"] = acc.get("eq", 0) + float(t[1]), acc.get("prs", 0) + len(RESULT.findall(body))
    return [dict(account=name, five_hour=r.get("five_hour"), week=r.get("week"), runs=r.get("runs"),
                 merged=r.get("prs", 0), tokens_per_pr=r["eq"] / r["prs"] if r.get("prs") else None)
            for name, r in sorted(rows.items(), key=lambda x: str(x[0]))]


RUN_LANE = re.compile(r"^Run: .*· lane (\S+)", re.M)
METRIC = re.compile(r"^Metrics: ticket #\d+ · ([^·]*?) · ([^·]*?) ·", re.M)
SINKS = re.compile(r"· sinks (.*)$", re.M)
SINK = re.compile(r"([^,]+?) (\d+)%")


def insights(hours=168, comments=None):
    """Where the usage goes (#4646), from the run reports: per lane its runs, M eq and merged PRs; per ticket size its
    tickets, merged PRs and M eq (a report with several tickets splits its eq evenly); the top sinks in M eq (the
    `sinks` shares of each `Tokens:` line times its eq)."""
    comments = health.status_comments(hours=hours) if comments is None else comments
    lanes, sizes, sinks = {}, {}, {}
    for c in comments:
        body = c.get("body") or ""
        t = TOKEN_LINE.search(body)
        eq = float(t[1]) if t else 0.0
        run = RUN_LANE.search(body)
        tickets = METRIC.findall(body)
        if not (t or tickets):
            continue
        lane = lanes.setdefault(run[1] if run else "opus", dict(runs=0, eq=0.0, merged=0))
        lane["runs"] += 1
        lane["eq"] += eq
        lane["merged"] += len(RESULT.findall(body))
        for size, result in tickets:
            row = sizes.setdefault(size.removeprefix("size:").strip() or "none", dict(tickets=0, merged=0, eq=0.0))
            row["tickets"] += 1
            row["merged"] += result == "merged" or result.startswith("pr #")
            row["eq"] += eq / len(tickets)
        line = SINKS.search(body[t.start():].split("\n", 1)[0]) if t else None
        for name, share in SINK.findall(line[1]) if line else ():
            sinks[name.strip()] = sinks.get(name.strip(), 0.0) + eq * int(share) / 100
    return dict(lanes=lanes, sizes=sizes, sinks=sorted(sinks.items(), key=lambda x: -x[1])[:5],
                days=activity(comments=comments))


TICKET = re.compile(r"^Metrics: ticket #(\d+) · ([^·]*?) ·", re.M)
COST = re.compile(r"· cost \$(\d+(?:\.\d+)?)")
RUN_EQ = re.compile(r"^Run: .*?· eq ((?:\w+ \d+(?:\.\d+)?M(?:, )?)+)", re.M)


def work_kind(number, size, process):
    """The type of the work on one ticket: `improve` for a ticket with the label `process` (the improvement jobs of
    the `improve` skill), else its size S, M or L, else `no size`."""
    if number in process:
        return "improve"
    size = size.removeprefix("size:").strip()
    return size if size in ("S", "M", "L") else "no size"


def parts(c, body, eq):
    """(phases, sinks) of one run report in M eq: the eq of each phase (the `Run:` line) and of each sink group (the
    `Tokens:` line, top 5; the run record has the top 10). The phases scale to the eq of the Tokens: line. The part of
    the eq that the listed sinks do not explain is `other`."""
    tok = c.get("tokens") if isinstance(c.get("tokens"), dict) else {}
    phases = {k: v / 1e6 for k, v in (tok.get("phases_eq") or {}).items()}
    if not phases and (m := RUN_EQ.search(body)):
        phases = {k: float(v) for k, v in re.findall(r"(\w+) (\d+(?:\.\d+)?)M", m[1])}
    total = sum(phases.values())
    phases = {k: eq * v / total for k, v in phases.items() if v} if total else {}
    shares = tok.get("sinks") or {}
    if not shares and (t := TOKEN_LINE.search(body)) and (m := SINKS.search(body[t.start():].split("\n", 1)[0])):
        shares = {k.strip(): int(v) / 100 for k, v in SINK.findall(m[1])}
    sinks = {k: eq * v for k, v in shares.items() if v}
    if eq and sum(shares.values()) < 0.999:
        sinks["other"] = eq * (1 - sum(shares.values()))
    return phases, sinks


def spend(hours=24 * 14, comments=None, process=()):
    """The usage of each run over time (owner, 2026-11-01): one row per run report with a `Tokens:` line and per type
    of its work (`work_kind`; a report with no ticket is a process `review` or `no ticket`), with its lane, M eq, cost
    in $ and the split of the eq by phase and by sink (`parts`). A report with several tickets splits its numbers
    evenly, as `insights` does: `runs` is the share of the run (1/tickets)."""
    comments = health.status_comments(hours=hours) if comments is None else comments
    process, rows = set(process), []
    for c in comments:
        body = c.get("body") or ""
        t = TOKEN_LINE.search(body)
        if not (t and c.get("created_at")):
            continue
        eq, cost = float(t[1]), COST.search(body)
        lane = c.get("lane") or ((m := RUN_LANE.search(body)) and m[1]) or "opus"
        work = [work_kind(int(n), s, process) for n, s in TICKET.findall(body)]
        work = work or ["review" if REVIEW.match(body) else "no ticket"]
        phases, sinks = parts(c, body, eq)
        k = len(work)
        for kind in work:
            rows.append(dict(at=c["created_at"], lane=lane, kind=kind, runs=round(1 / k, 4), eq=round(eq / k, 4),
                             cost=round(float(cost[1]) / k, 4) if cost else None,
                             phases={p: round(v / k, 4) for p, v in phases.items()},
                             sinks={s: round(v / k, 4) for s, v in sinks.items()}))
    return sorted(rows, key=lambda r: r["at"])


PHASE = re.compile(r"· phases ((?:\w+ \d+(?:\.\d+)?(?: · )?)+)")
WORK = {"read": "read and triage", "claim": "read and triage", "code": "tickets", "verify": "tickets",
        "ci": "CI fixes", "conflict": "conflicts", "report": "reports"}


def activity(hours=168, comments=None):
    """What the runs do per day (#4725), from the run reports: the runs, the merged PRs, the runs per merged PR, the
    kind of each run (`ticket`: a `Metrics:` line, `review`: a process review, `idle`: no ticket) and the minutes of
    the phases of its tickets, grouped by work (`WORK`). The newest day first."""
    comments = health.status_comments(hours=hours) if comments is None else comments
    days = {}
    for c in comments:
        body = c.get("body") or ""
        if not (c.get("created_at") and (TOKEN_LINE.search(body) or METRIC.search(body) or REVIEW.match(body))):
            continue
        row = days.setdefault(c["created_at"][:10], dict(runs=0, merged=0, kinds={}, work={}))
        row["runs"] += 1
        row["merged"] += len(RESULT.findall(body))
        kind = "review" if REVIEW.match(body) else "ticket" if METRIC.search(body) else "idle"
        row["kinds"][kind] = row["kinds"].get(kind, 0) + 1
        for line in PHASE.findall(body):
            for name, minutes in re.findall(r"(\w+) (\d+(?:\.\d+)?)", line):
                work = WORK.get(name, name)
                row["work"][work] = row["work"].get(work, 0.0) + float(minutes)
    return [dict(day=d, **days[d]) for d in sorted(days, reverse=True)]


REVIEW = re.compile(r"^\s*Process review", re.I)
CHANGE_PR = re.compile(r"\bPR #(\d+)")


def reviews(merges, hours=24 * 60, comments=None):
    """The process reviews of the `improve` skill (#4347): each report comment that starts with "Process review", its
    first paragraph (`text`, at most 400 characters), the PRs that it names (`changes`: "PR #N"),
    and the merged PRs between the review before it and this one (`prs`; None for the first review of the log): the
    real gap of the review algorithm of `framework/tools/claim.py`."""
    comments = health.status_comments(hours=hours) if comments is None else comments
    times = sorted(m["merged_at"] for m in merges)
    rows, last = [], None
    for c in sorted((c for c in comments if REVIEW.match(c.get("body") or "") and c.get("created_at")),
                    key=lambda c: c["created_at"]):
        at, body = c["created_at"], c["body"].strip()
        prs = None if last is None else sum(last < t <= at for t in times)
        text = body.split("\n\n")[0].strip()
        rows.append(dict(at=at, prs=prs, changes=sorted({int(n) for n in CHANGE_PR.findall(body)}),
                         text=text[:397] + "..." if len(text) > 400 else text))
        last = at
    return rows


def close(text, i):
    """The index after the parenthesis that closes the one before index i."""
    depth = 1
    while depth and i < len(text):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return i


def fields(body, rows):
    """The fields that the lambdas of `rows.filter((r) => ...)` (and the filters and sorts after it) read of a row."""
    out = set()
    for m in re.finditer(r"(?<![\w.])" + re.escape(rows) + r"(?=\.\w+\()", body):
        i, rest = m.end(), re.match(r"\.(concat|slice)\(", body[m.end():]) is not None  # keep the rows
        while (f := ROWS.match(body, i)):
            end = close(body, body.index("(", i) + 1)
            for v in filter(None, f.groups()[1:]):
                out |= set(re.findall(r"(?<![\w.])" + v + r"\.(\w+)", body[f.end():end]))
            rest, i = f[1] in ("filter", "sort"), end
            if not rest:
                break
        alias = re.search(r"const (\w+) = $", body[:m.start()])
        if rest and alias and alias[1] != rows:  # const open = tickets.filter(...): the rows of `open` too
            out |= fields(body, alias[1])
    return out


def page_columns(page):
    """{dataset: the columns that the dashboard page reads} for the data files (#1031): the inputs of `dash.calc`,
    `dash.data('NAME').data`, and the `data-field` heads of a table with `data-source`."""
    out = {name: set() for name in DATASETS}
    calcs = list(re.finditer(r"dash\.calc\('\w+',\s*\{\s*inputs:\s*\[([^\]]*)\].*?fn:\s*\(([^)]*)\)\s*=>", page, re.S))
    for m, after in zip(calcs, calcs[1:] + [None]):
        body = page[m.end():after.start() if after else len(page)]
        for name, param in zip(re.findall(r"\w+", m[1]), re.findall(r"\w+", m[2])):
            if name in out:
                out[name] |= fields(body, param)
    for m in re.finditer(r"const (\w+) = dash\.data\('(\w+)'\)", page):
        if m[2] in out:
            end = page.find("\n  function ", m.end())
            out[m[2]] |= fields(page[m.end():end if end > 0 else len(page)], m[1] + ".data")
    for m in re.finditer(r'<table[^>]*data-source="(\w+)".*?</table>', page, re.S):
        if m[1] in out:
            out[m[1]] |= set(re.findall(r'data-field="(\w+)"', m[0]))
    return out


def check(out_dir, page):
    """The columns that the page reads and a data file does not have: [(file, [column, ...])]."""
    missing = []
    for name, cols in page_columns(page).items():
        rows = json.load(open(os.path.join(out_dir, DATASETS[name])))
        have = set().union(*(r.keys() for r in rows)) if rows else cols
        if cols - have:
            missing.append((DATASETS[name], sorted(cols - have)))
    return missing


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    folder = os.environ.get("DASHBOARD_CACHE")
    issues, pulls = cached(folder) if folder else (pages("issues?state=all"), pages("pulls?state=closed"))
    merges = merged_prs(pulls)
    files = {
        "travel-merged-prs.json": merges,
        "travel-tickets.json": tickets(issues),
        "travel-epics.json": epics(issues),
        "travel-roadmap.json": roadmap(open(os.path.join(root, "steering", "project", "ROADMAP.md")).read()),
        # No release bar here (aoe2mc has steering/project/RELEASE.md): the page then counts each roadmap feature with
        # its epics as the full roadmap, with no release checks and no bug reserve.
        "travel-release-bar.json": [],
        "travel-usage.json": usage(),
        "travel-tokens.json": tokens(),
        "travel-accounts.json": accounts(),
        "travel-spend.json": spend(process=[i["number"] for i in issues
                                            if "process" in {label["name"] for label in i["labels"]}]),
        "travel-reviews.json": reviews(merges),
        "travel-setup.json": json.load(open(os.path.join(root, "tools", "dashboard_artifact", "setup.json"))),
    }
    for name, rows in files.items():
        with open(os.path.join(out_dir, name), "w") as f:
            json.dump(rows, f, ensure_ascii=False)
        print(f"{name}: {len(rows)} rows")
    missing = check(out_dir, open(os.path.join(root, "tools", "dashboard_artifact", "index.html")).read())
    for name, cols in missing:
        print(f"{name}: the page reads missing columns: {', '.join(cols)}")
    print("columns: missing" if missing else "columns: OK")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "out/dashboard"))
