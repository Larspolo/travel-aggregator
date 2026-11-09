"""Steps 1 to 5 of the `autopilot` skill in one call: it prints only what needs work (owner, 2026-10-28).

The start of a ticket took about 13 tool calls in each run (status issue, usage line, stuck tickets, each open PR, the
CI of main, owner feedback, triage, the pick list), 19 % of the calls of four runs on 2026-10-28. Each call reads the
whole context again. This tool reads all of it and prints one short section per step.

    python3 framework/tools/cycle_start.py                # at the start of a run and before each later ticket
    python3 framework/tools/cycle_start.py --lane haiku   # the pick list of the Haiku lane
    python3 framework/tools/cycle_start.py --last N       # a later ticket of the run: within a priority, the tickets of the
                                                # same epic or files as ticket N first

Sections: `Status` (exit 3 when the status issue has `paused`: stop; the time and the values of `agent.toml` that the
skill needs: repo, owner, branch), `Usage` (keep the line for the report of step 8),
`Stuck` (`claim.py 0 --stuck`), `Flow brake` (`usage.py --flow`), `PRs` (the open agent PRs that need work: red CI,
a conflict, a closed ticket, green and not merged after 10 minutes, a `hold` or no CI run that nothing ends),
`Main CI` (the last run and the last night run), `Feedback` (`feedback.py`), `Orphans` (`dashboard.orphans`: open
tickets that wait for nothing, #4553), `Triage` (open issues without a priority label), `Candidates` (the pick order of
`dashboard.py --next`, without the tickets that a run holds; the first 8 of the top priority group turned by the
branch name, so that parallel runs try other first picks, #3832; and the `claim.py N --or M ...` command of the first 5) and `Release checks` (only when a check can start and has
no ticket, `release.due()`), and `Deep work` (only for `--lane deep` with no candidate: the target, the claims and the
refill reason of `usage.py --fire` with the lock command of each kind of work, `deep_work`, #1377). The skill says
what to do with each line.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import zlib

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))   # the project tools: release.py (#4195)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
from agent_config import CONFIG  # noqa: E402

TOOLS = os.path.dirname(os.path.abspath(__file__))
AGENT = ("claude/", "agent/", "ccr-") # the branches of agent PRs (autopilot step 2)
WAITS = {"needs-human", "blocked"}     # a PR of such a ticket waits for the owner or another ticket
STALE, CONFLICT = 30, 10               # minutes without a beat: a stopped run (framework/tools/claim.py STALE, CONFLICT)
SWEEP = 10                             # minutes: a green PR that is still open needs the Automerge sweep (#734)
CLOSE = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)")
SHOW = 5                               # candidates to print
SPREAD = 8                             # the most runs that the pacer starts in one cycle (agent.toml max_fire)


def tool(*args):
    """(exit code, stdout + stderr) of a tool of this directory."""
    r = subprocess.run([sys.executable, os.path.join(TOOLS, args[0]), *args[1:]], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def beats(lines, now):
    """{ticket: (minutes since the last claim or beat, subject)} of the top claim slots ("<slot> <unix time> <subject>")."""
    top = {}
    for line in lines:
        slot, t, subject = (line.split(" ", 2) + ["", ""])[:3]
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", slot)
        if m and t.isdigit() and (int(m[1]) not in top or int(m[2] or 1) > top[int(m[1])][0]):
            top[int(m[1])] = (int(m[2] or 1), int(t), subject)
    return {n: ((now.timestamp() - t) / 60, s) for n, (_, t, s) in top.items()}


def pr_ticket(pr, held):
    """The ticket of an agent PR: the first closing line of its body, else the claim whose last beat names the PR branch
    (#4122: a run edited the body of PR #4061 and lost its "Closes #3909", so its live run looked stopped)."""
    if m := CLOSE.search(pr.get("body") or ""):
        return int(m[1])
    return next((n for n, (_, s) in held.items() if s.split(" ")[3:4] == [pr["head"]["ref"]]), None)


def quick_green(checks):
    """True when all parts of the job `quick` passed (`quick (1)` and `quick (2)`, #1077). checks: [(name, status,
    conclusion)]."""
    import ship_pr
    return ship_pr.quick_green([dict(name=n, status=s, conclusion=c) for n, s, c in checks])


def pr_work(pr, open_issues, checks, beat, now, me="", ticket=None):
    """The work that an open agent PR needs, or None. pr: an entry of /pulls; checks: [(name, status, conclusion)] of
    its head commit; beat: (minutes, subject) of its ticket claim, or None; me: the current branch; ticket: `pr_ticket`. The PRs of this run
    (`<session branch>` and `<session branch>-<k>`, autopilot `more.md`) are yours."""
    if not pr["head"]["ref"].startswith(AGENT):
        return None
    ticket = ticket or pr_ticket(pr, {})
    issue = open_issues.get(ticket)
    if ticket and issue is None:
        return "its ticket is closed: the Close workflow closes the PR"
    if issue and dashboard.labels(issue) & WAITS:
        return None
    idle = (now - dashboard.ts(pr.get("updated_at") or pr["created_at"])).total_seconds() / 60
    live = beat and not beat[1].startswith("Release") and beat[0] < STALE
    conflict = "conflict" in dashboard.labels(pr)
    red = [n for n, s, c in checks if s == "completed" and c in ("failure", "timed_out", "cancelled", "action_required")]
    if "hold" in dashboard.labels(pr):     # nothing removes `hold`: a run that stopped left it for ever (#4553)
        if live or idle < STALE:
            return None
        quick = quick_green(checks)
        state = "checks red: " + ", ".join(red) if red else "checks green" if quick else "checks not finished"
        if red or not quick:   # the auto mode denies a removal of `hold` on a PR of another run: the owner removes it (#581)
            return f"`hold`, no live claim, no change for {idle:.0f} min, {state}: add `needs-human` to #{ticket} with the reason"
        return (f"`hold`, no live claim, no change for {idle:.0f} min, {state}: add `needs-human` to #{ticket} and ask the "
                "owner to remove `hold` (`owner.md`; the auto mode denies a removal of `hold` on a PR of another run)")
    if not checks and not conflict and idle > STALE:   # no CI event (a push of GITHUB_TOKEN): Automerge waits for ever
        return f"no CI run on its head for {idle:.0f} min: start CI on its branch (`github.md`)"
    if not conflict and not red:
        age = (now - dashboard.ts(pr["created_at"])).total_seconds() / 60
        quick = quick_green(checks)
        done = all(s == "completed" for _, s, _ in checks)   # #606: Automerge can need other checks, so wait for every check
        return f"green and open {age:.0f} min: start the Automerge sweep (`github.md`)" if quick and done and age > SWEEP else None
    what = "conflict" if conflict else "red CI: " + ", ".join(red)
    base = re.sub(r"-\d+$", "", me)
    if me and re.fullmatch(re.escape(base) + r"(-\d+)?", pr["head"]["ref"]):
        return f"{what}; a PR of this run: fix it on its branch (`more.md`)"
    live = beat and not beat[1].startswith("Release") and beat[0] < (CONFLICT if conflict else STALE)
    owner = (beat[1].split(" ")[3:4] or ["?"])[0] if beat else None
    if live:
        return f"{what}; its run `{owner}` beat {beat[0]:.0f} min ago: leave it"
    return f"{what}; no live claim: take it over (`overlap.md`), then `merge_main.py --push {ticket} --pr-branch {pr['head']['ref']}` or fix at step 6.8"


def related(issue, last):
    """True when `issue` has the epic ("Part of #E") or a file or function name of `last`. A later ticket of a run on the
    code that the run already read costs less: 3 trigger tickets in one run cost $1.69 each, 2026-10-28."""
    epics = lambda i: set(re.findall(r"Part of #(\d+)", i.get("body") or ""))
    return bool(epics(issue) & epics(last) or dashboard.names(issue.get("body")) & dashboard.names(last.get("body")))


def group(i, lane=None):
    """The (lane, priority) group of a candidate: the first part of the rank of `dashboard.candidates`."""
    prio = next((k for k, p in enumerate(dashboard.PRIORITY) if p in dashboard.labels(i)), len(dashboard.PRIORITY))
    return lane is None and any(n.startswith(dashboard.LANE) for n in dashboard.labels(i)), prio


def prefer(picks, last, lane=None):
    """The pick order with the tickets related to `last` first within each priority (and lane group). The sort is
    stable: the order of `dashboard.candidates` stays inside each group."""
    return sorted(picks, key=lambda i: (group(i, lane), not related(i, last)))


def spread(items, me):
    """The first SPREAD items turned by a stable number of the run `me` (#3832): the runs that the pacer starts in
    one cycle get the same list, and all tried the same first item ("4 claims lost to other runs", #3579). The same
    run gets the same order each time; the items after the first SPREAD keep their place."""
    n = min(len(items), SPREAD)
    k = zlib.crc32(me.encode()) % n if n else 0
    return items[k:n] + items[:k] + items[n:]


def spread_top(picks, me, lane=None):
    """The candidates with only the top (lane, priority) group spread: a P1 ticket stays before all P2 tickets."""
    n = next((j for j, i in enumerate(picks) if group(i, lane) != group(picks[0], lane)), len(picks))
    return spread(picks[:n], me) + picks[n:]


def main_ci():
    """[(name, conclusion or status, short sha, start time)] of the last CI run on main and of the last night run."""
    out = []
    for name, query in (("last", "branch=main&per_page=1"), ("night", "branch=main&event=schedule&per_page=1")):
        runs = dashboard.api(f"actions/workflows/ci.yml/runs?{query}").get("workflow_runs") or []
        r = runs[0] if runs else {}
        out.append((name, r.get("conclusion") or r.get("status") or "-", (r.get("head_sha") or "-")[:7],
                    (r.get("created_at") or "-")[:16]))
    return out


RED = ("failure", "timed_out", "cancelled")


def merged_fix(log, closed):
    """The first commit of `log` (format `%s%x1f%b%x1e`) that closes a closed "Fix main" ticket or starts with "Fix main"."""
    for rec in log.split("\x1e"):
        subject, _, body = rec.strip().partition("\x1f")
        fixed = [int(n) for n in CLOSE.findall(body) if int(n) in closed]
        if fixed:
            return f"{subject} (#{fixed[0]})"
        if subject.startswith("Fix main"):
            return subject
    return ""


def fixed_after(closed, start):
    """The "Fix main" issues of `closed` that closed after `start` (a "YYYY-MM-DDTHH:MM" UTC time of a red run), as
    "#N title". A fix merged by a PR closes its ticket, so the Main CI line names it (#3225)."""
    return [f"#{i['number']} {i['title']}" for i in closed
            if i["title"].startswith("Fix main") and (i.get("closed_at") or "") > start]


def ci_line(ci, issues):
    """The `Main CI` line: the runs of `main_ci()` and, for a red run, the open "Fix main" tickets of `issues` and the
    fixes after the red run. The fixes come from all closed `P0` issues since the red run: the git log of a shallow
    clone can miss the fix commits, and the 100 last updated closed issues miss the tickets after some hours (#3305)."""
    fix = [f"#{n} {i['title']}" for n, i in issues.items() if "P0" in dashboard.labels(i) and i["title"].startswith("Fix main")]
    red = [c for c in ci if c[1] in RED]
    done, closed = "", []
    if red:
        since = min(t for *_, t in red)
        fixes = [i for i in dashboard.pages(f"issues?state=closed&labels=P0&since={since}:00Z")
                 if i["title"].startswith("Fix main")]
        log = subprocess.run(["git", "log", f"origin/{CONFIG['branch']}", f"--since={since}Z",
                              "--format=%s%x1f%b%x1e"], capture_output=True, text=True).stdout
        done = merged_fix(log, {i["number"] for i in fixes})
        closed = fixed_after(fixes, since)
    return " · ".join(f"{n} {c} ({sha}, {t})" for n, c, sha, t in ci) + (
        "" if not red else " → red: open P0 tickets \"Fix main\": " + ("; ".join(fix) or "none")
        + (f"; merged after the red run: {done}" if done else "")
        + (f"; closed after the red run: {'; '.join(closed)}" if closed else ""))


def due_checks():
    """The release checks that can start and have no ticket (`release.due()`, #3342), or [] when the read fails: a
    planning gap must not stop the run start."""
    try:
        import release
    except ImportError:                                     # a project with no tools/release.py has no release checks (#153)
        return []
    try:
        import release
        features, _, rows, epics = release.load()
        return release.due_lines(release.due(features, rows, epics))
    except Exception as e:                                  # a GitHub or file error: the other sections still print
        print(f"release checks: {e}", file=sys.stderr)
        return []


def status_line(number, state, now, lane=None):
    """The line of section `Status`: the state of the runs, the time and the values of `agent.toml` that the skill
    needs. Runs read the time with `date` and the values with `cat agent.toml` in more calls (2026-10-29)."""
    return (f"#{number} · last run {state.get('last_run', '-')} · runs {state.get('runs', '-')} · "
            f"now {now:%Y-%m-%dT%H:%M:%SZ} · repo {CONFIG['repo']} · owner {CONFIG['owner']} · branch {CONFIG['branch']}"
            + (f" · lane {lane} (git config travel-aggregator.lane)" if lane else ""))


def claim_lines(picks):
    """The one claim call for the candidates (--or); none with no candidate (an IndexError before)."""
    return [f"Claim: python3 framework/tools/claim.py {picks[0]['number']}"
            + (" --or " + " ".join(str(i["number"]) for i in picks[1:SHOW]) if len(picks) > 1 else "")] if picks else []


def deep_work(text):
    """The lines of the section `Deep work` from the stderr line of `usage.py --fire` (#1377). A refill run gets no brief
    of the pacer, so each deep run tried the locks one by one (`--refill`, a list of the epics, `--review`, `--roadmap`):
    28 of 133 runs were deep runs, and their phase `read` was about half of their tokens (2026-11-09). The pacer
    started the run for the reason of `usage.refill_need`; this names it and the lock of each kind of work."""
    m = re.search(r"target (\d+) runs · claims (\d+)", text)
    r = re.search(r" · refill (\d+) \((.*)\) · paused ", text)
    if not (m and r):
        return [f"- (no refill line in `usage.py --fire`: {text[-200:]})"]
    reason, out = r[2], [f"target {m[1]} · claims {m[2]} · refill {r[1]}: {r[2]}"]
    if e := re.match(r"epic check ((?:#\d+(?:, )?)+)", reason):
        out += [f"epic check: `python3 framework/tools/claim.py {n} --refill`, then `queue.md`, \"Epics and refill\""
                for n in re.findall(r"#(\d+)", e[1])]
    if re.search(r"process review (?:and roadmap review )?due", reason):
        out.append("process review: `python3 framework/tools/claim.py 0 --review`, then the `improve` skill")
    if "roadmap review due" in reason:
        out.append("roadmap review: `python3 framework/tools/claim.py 0 --roadmap`, then the `roadmap` skill")
    if re.match(r"rank |\d+ release checks|ready \d+ < target", reason):
        out.append("refill: `python3 framework/tools/claim.py 0 --refill`, then `queue.md`, \"Epics and refill\"")
    if len(out) == 1:
        out.append("no deep work: go to step 8 (report)")
    return out


def section(title, lines):
    print(f"{title}: " + ("none" if not lines else lines[0] if len(lines) == 1 else "\n  " + "\n  ".join(lines)))


def checkout(remote="origin", branch=None):
    """Move a clean session branch with no own commits to the newest `remote/branch` (#105).

    Returns (line, moved): line is None when HEAD is at the remote head. A branch with own commits or changes
    does not move: the line tells the run to update it.
    """
    branch = branch or CONFIG["branch"]
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True)
    if git("fetch", "-q", remote, branch).returncode:
        return f"Checkout: git fetch {remote} {branch} failed: check the checkout by hand", False
    up = f"{remote}/{branch}"
    behind = int(git("rev-list", "--count", f"HEAD..{up}").stdout.strip() or 0)
    if not behind:
        return None, False
    own = int(git("rev-list", "--count", f"{up}..HEAD").stdout.strip() or 0)
    me = git("branch", "--show-current").stdout.strip()
    if own or git("status", "--porcelain", "--untracked-files=no").stdout.strip() or not me:
        return f"Checkout: {behind} commits behind {up}: update before you work", False
    if git("checkout", "-q", "-B", me, up).returncode:
        return f"Checkout: {behind} commits behind {up}: update before you work", False
    sha = git("rev-parse", "--short", "HEAD").stdout.strip()
    return f"Checkout: moved to {sha} ({behind} commits behind)", True


OWNER_CHECK = re.compile(r"^\s*[-*]\s*After\s+((?:#\d+[,\s]*(?:and\s+)?)+):\s*(.+)$", re.I)


def owner_check_missing(issues, sub_issues_of):
    """Lines for the open epics with an `## Owner checks` line `- After #a, #b: ...` whose tickets are all closed
    (not in `issues`, the open issues) and that have no sub-issue with `needs-human` (#1342: `report.md`)."""
    out = []
    for n, i in sorted(issues.items()):
        if "epic" not in dashboard.labels(i):
            continue
        m = re.search(r"^##\s*Owner checks\s*$(.*?)(?=^##\s|\Z)", i.get("body") or "", re.M | re.S)
        if not m:
            continue
        ready = []
        for line in m[1].splitlines():
            c = OWNER_CHECK.match(line)
            if c and not any(int(t) in issues for t in re.findall(r"#(\d+)", c[1])):
                ready.append(line.strip().lstrip("-* ").strip())
        if not ready or any("needs-human" in dashboard.labels(s) for s in sub_issues_of(n) or []):
            continue
        out += [f"#{n} {i['title']}: no owner check ticket for \"{r}\": make it (`report.md`)" for r in ready]
    return out


def main(argv=None):
    if not os.environ.get("CYCLE_START_MOVED"):         # an old checkout runs old tools and skills (#105)
        line, moved = checkout()
        if line:
            print(line)
        if moved:                                       # run the new version of this tool once
            os.environ["CYCLE_START_MOVED"] = "1"
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__), *(sys.argv[1:] if argv is None else argv)])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lane", help="the pick list of this lane (haiku, #1715); sets `git config travel-aggregator.lane`")
    ap.add_argument("--last", type=int, help="the last ticket of this run: related tickets first")
    a = ap.parse_args(argv)
    now = datetime.datetime.now(datetime.timezone.utc)
    me = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
    if a.lane:                  # the claims and the report name the lane (#1727); one call less for each lane run
        subprocess.run(["git", "config", "travel-aggregator.lane", a.lane], capture_output=True)
    open_all = dashboard.pages("issues?state=open")                  # issues and PRs
    issues = {i["number"]: i for i in open_all if "pull_request" not in i}
    status = next((i for i in issues.values() if dashboard.STATUS in dashboard.labels(i)), None)
    if status is None:
        section("Status", ["no open issue with the label agent-status: make it (`report.md`)"])
    else:
        if CONFIG["status"]["paused"] in dashboard.labels(status):
            section("Status", [f"#{status['number']} has the label paused: stop now, do not comment"])
            return 3
        m = re.search(r"<!-- agent-state: (\{.*?\}) -->", status.get("body") or "")
        state = json.loads(m[1]) if m else {}
        section("Status", [status_line(status["number"], state, now, a.lane)])
    code, text = tool("usage.py", "--sample")
    section("Usage (keep it for step 8)", [text.splitlines()[-1] if code == 0 and text else f"- ({text[-200:]})"])
    code, text = tool("claim.py", "0", "--stuck")
    section("Stuck (`overlap.md`, \"Stuck tickets\")", text.splitlines() if code == 0 else [])
    code, text = tool("usage.py", "--flow")
    section("Flow brake", [f"ON: repair one PR or go to step 8, no new ticket ({text})"] if code == 1 else [])
    import health  # health imports dashboard
    held = beats(health.claim_refs() or [], now)
    prs = [p for p in dashboard.pages("pulls?state=open") if p["head"]["ref"].startswith(AGENT)]
    work = []
    for p in prs:
        checks = [(c["name"], c["status"], c["conclusion"]) for c in
                  dashboard.api(f"commits/{p['head']['sha']}/check-runs?per_page=100").get("check_runs", [])]
        t = pr_ticket(p, held)
        w = pr_work(p, issues, checks, held.get(t), now, me, t)
        if w:
            work.append(f"PR #{p['number']} (`{p['head']['ref']}`" + (f", #{t}" if t else "") + f"): {w}")
    take = [w for w in work if "take it over" in w]                 # two runs try other stuck PRs first (#3832)
    work = [w for w in work if w not in take] + spread(take, me)
    section(f"PRs ({len(work)} of {len(prs)} open agent PRs need work)", work)
    section("Main CI", [ci_line(main_ci(), issues)])
    code, text = tool("feedback.py")
    section("Feedback (lock each with `claim.py ID --comment`)", [t for t in text.splitlines() if re.match(r"\d+ #\d+ ", t)])
    section("Orphans (no run, workflow or owner list takes them up, #4553)",
            [f"#{n} {issues[n]['title']}: {why}" for n, why in dashboard.orphans(open_all)]
            + owner_check_missing(issues, lambda e: dashboard.pages(f"issues/{e}/sub_issues")))
    section("Triage (no priority label)", [f"#{n} {i['title']}" for n, i in sorted(issues.items())
                                           if not dashboard.labels(i) & (set(dashboard.PRIORITY) | {dashboard.STATUS})])
    pr_numbers = [i["number"] for i in open_all if "pull_request" in i]
    busy = dashboard.work(open_all, {n: [f["filename"] for f in dashboard.pages(f"pulls/{n}/files", 3)] for n in pr_numbers})
    hold = {n for n, (m, s) in held.items() if m < STALE and not s.startswith("Release")}
    picks = [i for i in dashboard.candidates(open_all, busy, lane=a.lane) if i["number"] not in hold]
    picks = spread_top(picks, me, a.lane)                            # parallel runs: other first picks (#3832)
    last = dashboard.api(f"issues/{a.last}") if a.last else None
    if last:
        picks = prefer(picks, last, a.lane)
    section(f"Candidates ({len(picks)} ready, pick order)", [
        f"#{i['number']} {i['title']} ({dashboard.tag(i, 'P')}, {dashboard.tag(i, 'size:')}, overlap "
        f"{len(dashboard.overlap(i, busy))}{', related' if last and related(i, last) else ''})" for i in picks[:SHOW]]
        + claim_lines(picks))
    if checks := due_checks():
        section("Release checks (no ticket, make them in the refill)", checks)
    if a.lane == "deep" and not picks:                  # the work of a refill run in one call (#1377)
        section("Deep work (act on it; no second `usage.py --fire`)", deep_work(tool("usage.py", "--fire")[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
