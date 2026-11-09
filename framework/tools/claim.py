"""Claim a ticket with a git ref, so that two runs cannot take the same ticket (#211).

A comment or a label never fails when another run was first. A push without force to a new ref fails when the
ref exists, so the ref `claim/N` decides who owns ticket N. The claim commit has no parent and a unique message:
a second push of another claim commit is never a fast-forward. Later claims of the same ticket use
`claim/N-2`, `claim/N-3` ...: the ref with the highest number owns the ticket.

    python3 framework/tools/claim.py N              # claim ticket N; exit 0: yours (it adds `in-progress` and "Started by",
                                          # and prints the ticket and its comments, #3459),
                                          # exit 1: it names the run that was first
    python3 framework/tools/claim.py N --or M K     # the same, and when another run has N, try M, then K, in this one call
    python3 framework/tools/claim.py N --release    # give your claim back (needs-human, blocked, hand-off); it removes
                                          # `in-progress` (#3234)
    python3 framework/tools/claim.py N --takeover   # take the ticket from a dead run (stale or released claim, #502)
    python3 framework/tools/claim.py N --show       # print the claim refs and the owner
    python3 framework/tools/claim.py N --beat       # show that the own run is alive (at least every 20 minutes)
    python3 framework/tools/claim.py N --adopt NAME # take over the claim that the pacer made as NAME for this run (its brief)
    python3 framework/tools/claim.py N --stale      # exit 0: the owner made no claim or beat for 30 minutes (stopped run),
                                          # 10 minutes when its PR has the label `conflict` (#1773)
    python3 framework/tools/claim.py 0 --stuck      # list the `in-progress` tickets of stopped runs (no beat for 30 minutes)
    python3 framework/tools/claim.py N --guard      # before each push: beat, and exit 1 when a PR of another branch closes N
                                          # or a union merge brought back LEARNINGS lines that main removed (#563)
    python3 framework/tools/claim.py N --guard --pr-branch B   # the same, but the open PR of branch B (taken over) is allowed
    python3 framework/tools/claim.py ID --comment   # lock owner comment ID (autopilot step 3); exit 1: another run handles it
    python3 framework/tools/claim.py E --refill     # lock the sub-issues of epic E (0: the whole queue refill, autopilot step 5;
                                              # a main run: only an epic without `lane:deep`, #1595)
    python3 framework/tools/claim.py 0 --fixmain --state SHA   # lock the "Fix main" ticket of the break in commit SHA (step 2)
    python3 framework/tools/claim.py 0 --review     # lock the process review after its gap of merged PRs (`improve` skill,
                                          # `[review]` of `steering/system/system.toml`; it prints the owner work since the last review)
    python3 framework/tools/claim.py 0 --reviewed change   # after the review: "change" or "none" sets the next gap
    python3 framework/tools/claim.py 0 --roadmap    # lock the review of steering/project/ROADMAP.md after 100 merged PRs (`roadmap` skill)
    python3 framework/tools/claim.py 0 --prune      # delete the refs of closed tickets and old locks (`claims.yml` only)

Two runs did one ticket (#288): one commented "Started by" and worked without the claim ref. So a claim also fails
when another branch commented "Started by" in the last 30 minutes or has an active PR for the ticket (#491), and `--guard` stops a run before its push when it does not own the claim or another branch has a PR for the ticket. The GitHub checks run only for a GitHub remote.

A usage limit stops all runs at about the same time, and a stopped run never continues (#231). Its last beat is
before the stop, so its ticket is stale at most 30 minutes after the limit resets. A live run beats again.

Three runs read one owner comment at the same time and made three copies of one epic (#320). So a run locks a
comment before it acts on it: `--comment` pushes `claim/comment-ID` once (no slots, no release).
Three runs refilled the queue of one epic within 2 minutes and made copies of tickets (#505). So a run locks the
refill before it makes tickets: `--refill` pushes `claim/refill-E-S` once. S is the state of the work: the number of
closed sub-issues of epic E (a new lock when a sub-issue closes), or the UTC hour and its 10-minute slot for E = 0
(the whole refill), for a ticket E with no sub-issue (#855) and for an epic E with all sub-issues closed (its count
cannot change any more, #3057). A slot lock `N-<slot>` also holds the count lock `N`: the first new sub-issue of
that run changes the state to N, and a second run made the same sub-issues again (#3454).
One break of main gave 8 "Fix main" tickets in 6 minutes (#3480). So a run locks the ticket before it makes it:
`--fixmain` pushes `claim/fixmain-SHA` once (SHA: the commit that broke main, default the head of `origin/main`). All
lanes use it: a red main stops all runs.

Parallel runs read the same `runs` counter of the status issue, so "every 5th run" lost 7 of 10 process reviews
(#898). So `--review` locks one review: `claim/review-<gap>pr-<last review>-<k>`, and only when `gap` PRs merged after
the last review (`last_review` in the state comment of #1). A review with no change doubles the gap (50, 100, 200
merged PRs), a change sets it back to 50 (`--reviewed`). `--roadmap` locks the roadmap review the same way, 100 merged
PRs after `last_roadmap` or its newest lock ref (#3352: a write of the body can be lost), 30 while the refill has no
source (#3741), or the merged count (at least 10, #5818) with no live run and no ready ticket (#851), or after 60 minutes with no merged PR.
With fewer than 10 merged PRs, an idle stretch (no ready ticket, no live run, starved refill) gets one review after 60 minutes (#491). A gap counts
merged PRs, not minutes: the speed of the project changes (#2039). The other times of this tool stay in seconds: a run that stopped
merges nothing, so only the clock finds it.

Exit 2: git failed for another reason (network, permission). The workflow `claims.yml` deletes the refs
of a closed ticket: the session proxy gives 403 for branch deletes. `--prune` does it with git and one API call (the
open issues): the workflow read each ref and each ticket by REST, about 60 calls a run and 44 runs an hour, and the
token of the workflows ran out of its hourly limit (2026-10-29). It also deletes the locks older than `LOCK_DAYS`.
"""
import argparse
import datetime
import functools
import json
import os
import re
import subprocess
import sys
import time
import uuid

import agent_config
from agent_config import CONFIG

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# The process review counts merged PRs, never hours (owner, 2026-10-29): `[review]` of `steering/system/system.toml`.
REVIEW_CONFIG = CONFIG.get("review", {})
REVIEW = REVIEW_CONFIG.get("gap", 80)            # the first gap, and the reset when the result of the reviews turns
REVIEW_MIN, REVIEW_MAX = REVIEW_CONFIG.get("min_gap", 10), REVIEW_CONFIG.get("max_gap", 640)   # halve, double between
REVIEW_MAX_MIN = REVIEW_CONFIG.get("max_min_gap", 40)   # the highest floor: the count of ready tickets, capped (#1597)
OWNER_GAP = REVIEW_CONFIG.get("owner_gap", 20)   # the gap when an owner session merged a PR since the last review
ROADMAP = 100               # merged PRs between two reviews of steering/project/ROADMAP.md (#2039)
ROADMAP_EARLY = 30          # the same while the refill has no source: R < N, each roadmap feature has an epic (#3741)
ROADMAP_IDLE = 60           # minutes with no merged PR (or no live run): then the merged count is the gap (no run merges)
ROADMAP_IDLE_MIN = 10       # the least merged count of that gap: 1 or 2 PRs change no feature (#5818: 5 reviews in 8 h)
STATUS = CONFIG["status"]["issue"]   # the status issue: its state comment holds the last reviews
# The times below find a run that stopped: a stopped run merges nothing, so they stay on the clock (#2039).
STALE = 30 * 60             # seconds without a claim or beat: the run stopped (usage limit, crash)
RECENT = 30 * 60            # seconds: a "Started by" comment of another branch owns the ticket for this time (#288)
CONFLICT = 10 * 60          # seconds: the stale time of a ticket whose PR has the label `conflict` (#1773)


LOCK_DAYS = {"comment": 1, "fixmain": 1, "review": 1, "roadmap": 1, "refill": 7}   # days that `--prune` keeps a lock
NS = "refs/travel-aggregator-prune"    # the local copies of the claim refs of `--prune`


def git(*args, check=True):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def fail(text):
    """Exit 2 on a git or GitHub error: `sys.exit(text)` exits 1, the code of "another run owns it" (#3064)."""
    print(text, file=sys.stderr)
    sys.exit(2)


def slot(number, k):
    return f"claim/{number}" if k == 1 else f"claim/{number}-{k}"


def refs(number, remote="origin"):
    """{k: sha} of the refs claim/N (k = 1) and claim/N-k on the remote."""
    out = git("ls-remote", remote, f"refs/heads/claim/{number}", f"refs/heads/claim/{number}-*").stdout
    found = {}
    for line in out.splitlines():
        sha, ref = line.split("\t")
        m = re.fullmatch(rf"refs/heads/claim/{number}(?:-(\d+))?", ref)
        if m:
            found[int(m.group(1) or 1)] = sha
    return found


def subject(ref, remote="origin"):
    """Subject of the tip commit of a remote ref ("Claim #N by ..." or "Release #N by ...")."""
    git("fetch", "-q", remote, f"refs/heads/{ref}")
    return git("log", "-1", "--format=%s", "FETCH_HEAD").stdout.strip()


def changed(ref, remote="origin"):
    """Commit time (Unix seconds) of the tip of a remote ref: the claim, the last beat or the release."""
    git("fetch", "-q", remote, f"refs/heads/{ref}")
    return int(git("log", "-1", "--format=%ct", "FETCH_HEAD").stdout.strip())


def owner(subject_line):
    """The branch of a claim, beat or release line ("Claim #N by <branch> (...)"), in backticks."""
    words = subject_line.split(" ")
    return f"`{words[3]}`" if len(words) > 3 else "another run"


def first(number, remote="origin"):
    """The run that holds ticket `number` and its last sign of life: the text of a lost claim."""
    found = refs(number, remote)
    if not found:
        return "another run"
    ref = slot(number, max(found))
    line = subject(ref, remote)
    return f"{owner(line)} (its last {line.split(' ')[0].lower()} {(time.time() - changed(ref, remote)) / 60:.0f} min ago)"


def start(number, by=None, note="", word="Started by"):
    """Add `in-progress` and the comment "Started by `<branch>`." after a won claim. A run that commented by hand
    without the claim worked on one ticket with another run (#288, #1749), so only the claim writes them.
    by: the name of the claim (the pacer claims for a run that has no branch yet); note: more text of the comment;
    word: "Taken over by" after a takeover of the pacer (#4356)."""
    from dashboard import FOOTER
    from dashboard import api as call
    by = by or who()
    try:
        call(f"issues/{number}/labels", "POST", {"labels": ["in-progress"]})
        call(f"issues/{number}/comments", "POST", {"body": f"{word} `{by}`.{note}{FOOTER}"})
        print(f"added in-progress and \"{word} `{by}`.\" to #{number}")
    except Exception as e:                              # the claim ref is the lock: the ticket is yours anyway
        print(f"the claim is yours, but the label or the comment failed ({e}): add them by hand")


def stop(number):
    """Remove `in-progress` after a release, as start() adds it: a run that released and left the label held 5
    tickets for 40 minutes (#3234). A failed call (the label is not there) does not fail the release."""
    from dashboard import api as call
    try:
        call(f"issues/{number}/labels/in-progress", "DELETE")
        print(f"removed in-progress from #{number}")
    except Exception as e:                              # the release commit is the lock
        print(f"released, but the label call failed ({e})")


def stale(subject_line, last, now, limit=STALE):
    """True when an open claim (not released) had no beat for `limit` seconds."""
    return not subject_line.startswith("Release") and now - last >= limit


def who():
    return git("symbolic-ref", "--short", "HEAD", check=False).stdout.strip() or "unknown"


def lane():
    """" lane NAME" when the run set `git config travel-aggregator.lane NAME` (a Haiku run, #1727), else "": the pacer
    counts the runs of each lane (`health.lane_claims`)."""
    name = git("config", "--get", "travel-aggregator.lane", check=False).stdout.strip()
    return f" lane {name}" if name else ""


def account():
    """" account NAME" when the run has an account (`agent_config.account()`, #4236), else "". It comes before the lane:
    the readers of the lane take ` lane NAME` at the end of a claim."""
    name = agent_config.account()
    return f" account {name}" if name else ""


def deep_lane():
    """True when this run may do the process review, the roadmap review and the queue refill: always, but only the
    runs of the deep lane while `reserved` in `[pacing]` of `steering/system/system.toml` names `deep` (owner, 2026-10-28): the main runs
    work at low effort, and these steps steer many later tickets."""
    return "deep" not in CONFIG.get("pacing", {}).get("reserved", ()) or lane() == " lane deep"


def main_check(issue):
    """True when a main run may lock the refill of `issue` (#1595): an epic (label `epic`) without `lane:deep`. The
    main lane does the epic check and its new sub-issues; a deep run does the close check (`lane:deep` on the epic: a
    main run found all criteria met), the split of a `size:L` ticket and the whole refill (E = 0). A wrong close is
    silent (no run checks a closed epic again), a missed gap is found at the next check."""
    names = {x["name"] if isinstance(x, dict) else x for x in (issue or {}).get("labels", [])}
    return "epic" in names and "lane:deep" not in names


def main_may_refill(epic, remote="origin"):
    """`main_check` of epic `epic` on GitHub; False for E = 0 (the whole refill) and with no GitHub remote."""
    return bool(epic) and on_github(remote) and main_check(api(f"issues/{epic}"))


def push(sha, ref, remote="origin"):
    """True: the remote took the push. False: the ref exists (another run). Exit 2 on any other error."""
    r = git("push", "--porcelain", remote, f"{sha}:refs/heads/{ref}", check=False)
    if r.returncode == 0:
        return True
    if "[rejected]" in r.stdout:                  # not a fast-forward: the ref exists
        return False
    # A push at the same time as the push of another run: "[remote rejected] (failed to update ref)", "cannot lock
    # ref". The ref then exists, with the commit of the run that was first.
    tip = git("ls-remote", remote, f"refs/heads/{ref}", check=False)
    if tip.returncode == 0 and tip.stdout.strip():
        return tip.stdout.split("\t")[0] == sha
    fail(f"git push failed:\n{r.stdout}{r.stderr}")


def claim(number, takeover=False, remote="origin", limit=STALE, by=None, tag=None):
    """Push a new claim commit to the next free slot. The slot is free only when there is no claim yet or the
    last claim was released. A takeover also takes a stale claim, but never a live one: three runs took over
    one hand-off in 15 seconds, and each pushed the next slot (#502). by, tag: the name and the ` lane NAME` of the
    claim, else the branch and the git config (the pacer claims for a run before it starts, `framework/tools/pacer.py`)."""
    found = refs(number, remote)
    top = max(found, default=0)
    if top:
        line = subject(slot(number, top), remote)
        if not line.startswith("Release") and not (takeover and stale(line, changed(slot(number, top), remote),
                                                                     time.time(), limit)):
            return None
    msg = f"Claim #{number} by {by or who()} ({uuid.uuid4().hex}){account() + lane() if tag is None else tag}"   # unique: two runs never push the same SHA
    sha = git("commit-tree", EMPTY_TREE, "-m", msg).stdout.strip()
    ref = slot(number, top + 1)
    return ref if push(sha, ref, remote) else None


def claim_comment(cid, remote="origin"):
    """Lock comment `cid`: True when this run pushed `claim/comment-ID` first."""
    sha = git("commit-tree", EMPTY_TREE, "-m", f"Claim comment {cid} by {who()} ({uuid.uuid4().hex})").stdout.strip()
    return push(sha, f"claim/comment-{cid}", remote)


def refill_state(epic, remote="origin", now=None):
    """The state part of the refill lock: closed sub-issues of the epic on GitHub, else the UTC hour and its 10-minute
    slot: the runs close about 25 tickets per hour, so one refill per hour, then per 15 minutes, left the queue empty
    (#609, #650). A ticket with no sub-issue gets the slot too: else the lock of a run that did not split it stays
    for ever (#855: #397 waited 5 hours). So does an epic with all sub-issues closed: its count cannot change any more
    (#3057)."""
    t = datetime.datetime.fromtimestamp(now or time.time(), datetime.timezone.utc)
    slot = t.strftime("%Y%m%d%H") + str(t.minute // 10)
    if epic and on_github(remote):
        s = api(f"issues/{epic}").get("sub_issues_summary") or {}
        done, total = s.get("completed", 0), s.get("total")
        return str(done) if total and done < total else f"{done}-{slot}"
    return slot


def claim_refill(epic, state, remote="origin"):
    """Lock the refill of epic `epic` in state `state`: True when this run pushed `claim/refill-E-S` first. A count
    state N is taken also by a slot lock `N-<slot>`: that run locked the epic with all N sub-issues closed, and its
    first new sub-issue turned the state into N (#3454: #3431 and #3432 were the same ticket)."""
    if epic and "-" not in state and git("ls-remote", remote, f"refs/heads/claim/refill-{epic}-{state}-*").stdout.strip():
        return False
    msg = f"Claim refill {epic}-{state} by {who()} ({uuid.uuid4().hex}){account()}{lane()}"   # `usage.refill_live`
    return push(git("commit-tree", EMPTY_TREE, "-m", msg).stdout.strip(), f"claim/refill-{epic}-{state}", remote)


def claim_fixmain(sha, remote="origin"):
    """Lock the "Fix main" ticket of the break in commit `sha`: True when this run pushed `claim/fixmain-SHA` first."""
    msg = f"Claim fixmain {sha} by {who()} ({uuid.uuid4().hex})"
    return push(git("commit-tree", EMPTY_TREE, "-m", msg).stdout.strip(), f"claim/fixmain-{sha}", remote)


def agent_state(body):
    """The JSON of the state comment `<!-- agent-state: {...} -->` of the status issue, or {}."""
    m = re.search(r"<!-- agent-state: (\{.*?\}) -->", body or "")
    return json.loads(m[1]) if m else {}


def pr_slot(last, gap, merged, again=None):
    """The lock key of a review that waits for `gap` merged PRs after the time `last` (ISO, or None: no review yet), or
    None when fewer PRs merged since then. merged: the PRs merged after `last`. The key holds `last` and a count: one
    run takes each review, and a review that a run did not finish opens again `again` merged PRs later (default `gap`).
    The process review gives at least REVIEW: at a gap of 10, a second review would start while the first one runs."""
    if merged < gap:
        return None
    return f"{gap}pr-{re.sub(r'[^0-9TZ]', '', last or '') or 'none'}-{1 + (merged - gap) // (again or gap)}"


@functools.cache
def merge_rows(last):
    """[(time, PR, message)] of the PRs merged after the ISO time `last`, newest first (`dashboard.merges`)."""
    from dashboard import merges
    try:
        return merges(since=datetime.datetime.fromisoformat(last.replace("Z", "+00:00")), messages=True)
    except Exception as e:                              # exit 2 like a git error, not 1 ("another run does it")
        fail(f"GitHub API failed for the merged PRs: {e}")


def merged_since(last, gap, remote="origin"):
    """The number of PRs merged after the ISO time `last`. With no last review, or without GitHub (the tests): `gap`,
    so the review starts."""
    if not last or not on_github(remote):
        return gap
    return len(merge_rows(last))


def idle_minutes(last, remote="origin"):
    """The minutes since the newest PR merged after the ISO time `last` (since `last` with none); 0 without GitHub."""
    if not last or not on_github(remote):
        return 0
    rows = merge_rows(last)
    newest = rows[0][0] if rows else datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
    return (time.time() - newest.timestamp()) / 60


def owner_since(last, remote="origin"):
    """[(PR, title)] of the owner work merged after `last` (`dashboard.owner_work`): PRs that no run made. Each one is
    a miss of the improve loop, so the process review comes after OWNER_GAP merged PRs, not after its full gap."""
    if not last or not on_github(remote):
        return []
    from dashboard import owner_work
    return owner_work(merge_rows(last))


def utc(now=None):
    return datetime.datetime.fromtimestamp(now or time.time(), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def with_state(body, state):
    """The body of the status issue with `state` in its state comment."""
    new = f"<!-- agent-state: {json.dumps(state)} -->"
    old = re.search(r"<!-- agent-state: \{.*?\} -->", body or "")
    return body.replace(old[0], new) if old else new + "\n" + (body or "")


def review_floor(ready):
    """The least gap after a review with a change (#1597, P9): the count of ready tickets of all lanes, between REVIEW_MIN
    and REVIEW_MAX_MIN. Many ready tickets: a review takes quota from them, so it comes later. Few: a review costs no
    ticket. ready None (GitHub cannot be read) counts as 0."""
    return min(max(REVIEW_MIN, ready or 0), REVIEW_MAX_MIN)


def next_gap(gap, changed, ready=0):
    """The gap after a review (owner, 2026-10-29). A change resets a gap above REVIEW to REVIEW and halves the others
    (at least review_floor(ready) merged PRs), so a review that finds work comes sooner. No change resets a gap below
    REVIEW to REVIEW and doubles the others (at most REVIEW_MAX). With 80, 10 and 640 and few ready tickets: a change
    each time gives 80, 40, 20, 10, 10 ...; no change each time gives 80, 160, 320, 640, 640 ... With 25 ready tickets
    a change gives 80, 40, 25, 25 ... The floor is read at `--reviewed`, not at the slot: the lock key holds the gap, and
    a gap that moves with the queue gives two keys and two reviews (#898)."""
    if changed:
        return REVIEW if gap > REVIEW else max(review_floor(ready), gap // 2)
    return REVIEW if gap < REVIEW else min(2 * gap, REVIEW_MAX)


def review_gap(state):
    """The gap of merged PRs before the next process review: `review_prs` of the state comment. A gap that next_gap
    cannot reach from REVIEW with any floor (the state of an earlier rule, for example 200) counts as REVIEW."""
    seen, todo = set(), [REVIEW]
    while todo:
        if (gap := todo.pop()) not in seen:
            seen.add(gap)
            todo += [next_gap(gap, True, r) for r in range(REVIEW_MIN, REVIEW_MAX_MIN + 1)] + [next_gap(gap, False)]
    return state["review_prs"] if state.get("review_prs") in seen else REVIEW


def reviewed(body, changed, now=None, ready=0):
    """The body of the status issue after a review: `review_prs` is the next gap (next_gap; ready: the count of ready
    tickets). The other keys of the state comment stay; `review_minutes` (the time slot before #2039) goes."""
    state = {k: v for k, v in agent_state(body).items() if k != "review_minutes"}
    return with_state(body, {**state, "last_review": utc(now),
                             "review_prs": next_gap(review_gap(state), changed, ready)})


def last_lock(kind, remote="origin"):
    """The ISO time of the newest lock `claim/<kind>-<gap>pr-<last>-<k>` (the commit time of its claim), or None. A ref
    push is atomic, but a write of the status issue body can overwrite another one: a lost `last_roadmap` delayed the
    roadmap review by 100 merged PRs (#3352). The newest lock has the largest (last, k); "none" is the oldest."""
    if not (newest := newest_lock(kind, remote)):
        return None
    git("fetch", "-q", remote, newest[1])
    return utc(int(git("log", "-1", "--format=%ct", "FETCH_HEAD").stdout))


def newest_lock(kind, remote="origin"):
    """(gap, ref) of the newest lock `claim/<kind>-<gap>pr-<last>-<k>` (the largest (last, k)), or None."""
    out = git("ls-remote", remote, f"refs/heads/claim/{kind}-*").stdout
    keys = [(m[2] != "none", m[2], int(m[3]), int(m[1]), ref) for line in out.splitlines()
            for ref in [line.split("\t")[1]]
            for m in [re.fullmatch(rf"refs/heads/claim/{kind}-(\d+)pr-([0-9TZ]+|none)-(\d+)", ref)] if m]
    return max(keys)[3:] if keys else None


def review_slot(kind, remote="origin", starved=None):
    """(lock key, gap) of the process review (`review`) or the roadmap review (`roadmap`); the key is None when the review
    is not due. For `--review`, `--roadmap` and `usage.due_reviews` (a due review is work of a deep run, #3560).
    starved: a function that is True when the refill has no source (default `starved`); the roadmap gap is then
    ROADMAP_EARLY, so that the queue does not run empty for 100 merged PRs (#3741). When no more PR merges
    (`nothing_merges`) the gap is the merged count (at least ROADMAP_IDLE_MIN): with no ready ticket no run merges, and the queue
    stopped at 27 of 30 (2026-10-31). It is read only in that window."""
    body = api(f"issues/{STATUS}")["body"] if on_github(remote) else ""
    state = agent_state(body)
    last, gap = (state.get("last_review"), review_gap(state)) if kind == "review" else \
        (state.get("last_roadmap"), ROADMAP)
    # The roadmap counts from the later of the state and its newest lock (#3352). The process review keeps the state
    # time: its lock comes before the review, and a review that no run finished must open again (pr_slot).
    if kind == "roadmap" and on_github(remote):
        last = max(filter(None, (last, last_lock(kind, remote))), default=None)
    merged = merged_since(last, gap, remote)
    if kind == "roadmap" and merged < gap:
        early = merged >= ROADMAP_EARLY or merged >= ROADMAP_IDLE_MIN and nothing_merges(last, remote)
        stretch = None if early or merged >= ROADMAP_IDLE_MIN else idle_stretch(last, merged, remote)
        if (early or stretch is not None) and (starved or refill_starved)():
            if early or stretch:
                gap = min(merged, ROADMAP_EARLY)
            else:
                HELD.add(kind)                          # it waits only for the clock of the stretch (health.idle_queue)
    if kind == "review" and OWNER_GAP <= merged < gap and owner_since(last, remote):
        gap = OWNER_GAP
    return pr_slot(last, gap, merged, max(gap, REVIEW) if kind == "review" else max(gap, 1)), gap


HELD = set()   # the reviews that review_slot held for the clock of an idle stretch: the pacer line names them (#491)


def idle_stretch(last, merged, remote="origin"):
    """For fewer than ROADMAP_IDLE_MIN merged PRs (#5818): None when the queue is not in an idle stretch that the
    roadmap review can end, True when the review of the stretch is due, False while it waits for the clock. A stretch:
    no ready ticket (0, not a read error), no live run, and no lock of a stretch review with no merge after it. With no
    ready ticket no PR merges, so the merged count never reached its minimum, and the queue stood idle 6.5 h on
    2026-11-07; a review then made 3 epics (#491). One review per stretch keeps the brake of #5818: the key of the
    stretch is `<merged>pr-<last>-1`, and its lock is the newest lock until a PR merges. The review waits ROADMAP_IDLE
    minutes after the last lock or merge: the review that just ran had the same input."""
    if live_runs(remote) != 0 or ready_tickets(remote) != 0:
        return None
    if merged == 0 and (newest := newest_lock("roadmap", remote)) and newest[0] < ROADMAP_IDLE_MIN:
        return None                                     # the review of this stretch ran: no new merge since its lock
    return idle_minutes(last, remote) >= ROADMAP_IDLE


def live_runs(remote="origin"):
    """The runs that hold a beating ticket claim now (`health.beating_claims`); None when git cannot read the claims."""
    import health  # health imports dashboard, which imports this module
    return health.beating_claims(datetime.datetime.now(datetime.timezone.utc), remote=remote)


def nothing_merges(last, remote="origin"):
    """True when no PR will merge soon: no run holds a beating claim, or ROADMAP_IDLE minutes passed with no merge after
    `last` (a run that stopped). Only the clock made the queue stand idle 13 times for about 1 h on 2026-11-01 and
    2026-11-02 while no run worked (lever 8 of the `improve` skill). A ready ticket counts as a live run (#851): the
    pacer starts its run in the same cycle, and its claim made the review not due for the deep run of that cycle (5
    of 47 deep runs found no work on 2026-11-03)."""
    return live_runs(remote) == 0 and not ready_tickets(remote) or idle_minutes(last, remote) >= ROADMAP_IDLE


def ready_tickets(remote="origin"):
    """The number of ready tickets of all lanes (`dashboard.candidates`), from one page of the open issues; None when
    GitHub cannot be read (then `nothing_merges` keeps its result from before #851)."""
    import dashboard
    try:
        return len(dashboard.candidates(api("issues?state=open&per_page=100"), reserved=()))
    except (Exception, SystemExit) as e:                # claim.fail exits 2 on a GitHub error
        print(f"ready tickets: {e}", file=sys.stderr)
        return None


def refill_starved():
    """True when fewer tickets are ready than the target runs and the refill has no source: no epic or release check, no
    roadmap feature with no epic, no fallback (`usage.refill_need`, #3741). Reads the quota and GitHub; an error: False."""
    import usage  # usage imports this module in due_reviews
    try:
        import dashboard
        usage_now, now = usage.read_usage(), time.time()
        burn, burn7 = usage.burns(usage.read_status()[0])
        target = usage.target_runs(usage_now, now, burn, burn7=burn7)
        issues = dashboard.pages("issues?state=open")
        ready = len(dashboard.candidates(issues, reserved=()))
        return target is not None and ready < target and \
            not usage.refill_need(ready, target, issues, usage.release_due, lambda: [], usage.free_sources,
                                 closing=usage.autoclosing)
    except Exception as e:                                         # a quota, GitHub or file error
        print(f"refill sources: {e}", file=sys.stderr)
        return False


def claim_lock(kind, key, remote="origin"):
    """Push `claim/<kind>-<key>` once: True when this run was first."""
    msg = f"Claim {kind} {key} by {who()} ({uuid.uuid4().hex})"
    return push(git("commit-tree", EMPTY_TREE, "-m", msg).stdout.strip(), f"claim/{kind}-{key}", remote)


def release(number, remote="origin", word="Release", by=None, adopt=None):
    """Add a release (or beat) commit on top of the own claim (a fast-forward of the top ref). by: the name of the
    claim, else the branch. adopt: the claim of the pacer for this run: the commit names the branch from now on and
    keeps the lane of the claim."""
    found = refs(number, remote)
    if not found:
        return None
    ref = slot(number, max(found))
    line = subject(ref, remote)
    if line.split(" ")[3:4] not in ([by or who()], [adopt]):  # "Claim #N by <branch> (...)", "Beat #N by <branch>"
        sys.exit(f"{ref} belongs to another run: {owner(line)} took #{number} over ({line}). Stop the work on #{number}"
                 f" now: no push, no comment, no release; pick the next ticket.")
    own = account() or (m[0] if adopt and (m := re.search(r" account \S+", line)) else "")   # the account of the brief
    tag = own + (re.search(r" lane \w+$", line)[0] if adopt and re.search(r" lane \w+$", line) else lane())
    sha = git("commit-tree", EMPTY_TREE, "-p", "FETCH_HEAD", "-m", f"{word} #{number} by {by or who()}{tag}").stdout.strip()
    return ref if push(sha, ref, remote) else None


def revived(path=CONFIG["docs"]["learnings"], base=f"origin/{CONFIG['branch']}"):
    """Lines of `path` that a `merge=union` merge of `base` brought back after `base` removed them (#563).

    M is the last merged state of `base` (the merge base). A line of HEAD that is not in M and that no own commit
    after M added came from an older version through the union merge."""
    m = git("merge-base", "HEAD", base, check=False).stdout.strip()
    if not m:
        return []
    old = set(git("show", f"{m}:{path}", check=False).stdout.splitlines())
    own = {line[1:] for line in git("log", "-p", "--no-merges", "--format=", f"{m}..HEAD", "--", path).stdout.splitlines()
           if line.startswith("+") and not line.startswith("+++")}
    head = git("show", f"HEAD:{path}", check=False).stdout.splitlines()
    return [line for line in head if line.strip() and line not in old and line not in own]


def foreign(number, base=f"origin/{CONFIG['branch']}"):
    """(M, commit) for each own commit of HEAD that closes another ticket M (`Closes #M`): such a branch ships two
    tickets (#4569). A merge of `base` adds nothing: `base..HEAD` leaves out its commits."""
    if git("rev-parse", "--is-shallow-repository", check=False).stdout.strip() == "true":
        # A shallow clone cuts off the merge bases: the commits of main then show as own commits (#4604).
        git("fetch", "--quiet", "--unshallow", base.split("/")[0], check=False)
    # A stale local ref of main shows the newer commits of main as own commits (#183): fetch it first.
    remote, _, branch = base.partition("/")
    git("fetch", "--quiet", remote, f"+refs/heads/{branch}:refs/remotes/{base}", check=False)
    out = []
    for commit in filter(None, git("log", "--no-merges", "--format=%h %B%x00", f"{base}..HEAD", check=False).stdout.split("\0")):
        for m in re.findall(r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s*:?\s+#(\d+)", commit, re.I):
            if int(m) != number:
                out.append((int(m), commit.strip().splitlines()[0]))
    return out


def prunable(tips, open_numbers, now, days=LOCK_DAYS):
    """The claim refs to delete, from {name: Unix time of its tip} (name: the part after `claim/`): the slots of a
    ticket that is not open, the refill locks of an epic that is not open, and the locks older than `days` of their
    kind. E = 0 of `refill-0-S` is the whole refill, never an issue."""
    out = []
    for name, t in sorted(tips.items()):
        m = re.fullmatch(r"(\d+)(?:-\d+)?", name)
        if m:
            if int(m[1]) not in open_numbers:
                out.append(name)
            continue
        kind, _, rest = name.partition("-")
        epic = rest.split("-")[0]
        if kind == "refill" and epic.isdigit() and epic != "0" and int(epic) not in open_numbers:
            out.append(name)
        elif kind in days and now - t > days[kind] * 86400:
            out.append(name)
    return out


def prune(remote="origin", now=None, open_numbers=None):
    """Delete the `prunable` claim refs with git (a fetch of the refs for their times, a push that deletes them). The
    open issues and PRs come from one API read; with no open issue (a failed or empty read) it deletes nothing: the
    status issue is always open. Returns the deleted names."""
    if open_numbers is None:
        from dashboard import pages
        found = pages("issues?state=open", limit=20)
        if not found or len(found) >= 2000:            # never delete the claims of live tickets on a partial read
            fail("prune: no open issue read: nothing deleted")
        open_numbers = {i["number"] for i in found}
    if git("fetch", "-q", "--depth", "1", "--prune", remote, f"+refs/heads/claim/*:{NS}/*", check=False).returncode:
        fail("prune: git fetch of the claim refs failed")
    lines = git("for-each-ref", NS, "--format=%(refname:lstrip=2) %(committerdate:unix)").stdout.split("\n")
    times = {n: int(t) for n, t in (x.split(" ") for x in lines if x.strip())}
    gone = prunable(times, open_numbers, now or time.time())
    for i in range(0, len(gone), 100):                  # one push deletes many refs
        part = [f"refs/heads/claim/{n}" for n in gone[i:i + 100]]
        r = git("push", "-q", remote, "--delete", *part, check=False)
        if r.returncode and "remote ref does not exist" not in r.stderr:
            fail(f"prune: git push --delete failed: {r.stderr.strip()[:500]}")
    return gone


def on_github(remote="origin"):
    """The comment and PR checks need the GitHub API: the tests use a local bare remote."""
    return "github.com" in git("remote", "get-url", remote, check=False).stdout


def api(path):
    from dashboard import api as get  # gh api in cloud sessions, else GITHUB_TOKEN
    try:
        return get(path)
    except Exception as e:                              # exit 2 like a git error, not 1 ("owned by another run")
        fail(f"GitHub API failed for {path}: {e}")


def ticket_text(issue, comments):
    """The title, body and comments of a won ticket (#3459): the run reads them next, so the claim prints them and saves
    one API call. The "Started by" comments of the claims are left out."""
    out = [f"#{issue.get('number', '')} {issue.get('title', '')}", (issue.get("body") or "").strip()]
    for c in comments:
        if not re.match(r"Started by `|Taken over by `", c.get("body") or ""):
            out += [f"--- comment of {(c.get('user') or {}).get('login')} ({c.get('created_at')}):",
                    (c.get("body") or "").strip()]
    return "\n".join(out)


def started_by_other(comments, me, now, limit=RECENT):
    """Branch of the last "Started by `X`." comment of another branch in the last `limit` seconds, else None."""
    for c in reversed(comments):
        m = re.match(r"Started by `([^`]+)`", c["body"])
        t = datetime.datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")).timestamp()
        if m and m.group(1) != me and now - t < limit:
            return m.group(1)
    return None


def closes(number):
    return re.compile(rf"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?) #{number}\b", re.I)


def prose(body):
    """The PR body without code blocks and code spans: GitHub closes no issue from a keyword in code (#536)."""
    return re.sub(r"```.*?(```|$)|`[^`\n]*`", "", body or "", flags=re.S)


def other_pr(pulls, number, me, taken=None, still_open=False):
    """Number of an open or merged PR of another branch whose body closes ticket `number`, else None.
    taken: the branch of a PR that this run took over (#361): its open PR is the run's own. A PR with `Part of #N`
    (ship_pr.py --part) leaves the ticket open, also when its prose says "does not close #N" (#4063).
    still_open: the ticket is open on GitHub, so no merged PR closed it (#4063: the body of #4633 quoted "does not
    close #4063" and had `Part of #4063` only in a code span)."""
    closes_n, part = closes(number), re.compile(rf"\bPart of #{number}\b")
    for p in pulls:
        own = p["head"]["ref"] == me or p["head"]["ref"] == taken and p["state"] == "open"
        text = prose(p["body"])
        live = p["state"] == "open" or p.get("merged_at") and not still_open
        if not own and live and closes_n.search(text) and not part.search(text):
            return p["number"]
    return None


def active_pr(pulls, number, me, now, limit=RECENT):
    """Number of an open PR of another branch that closes ticket `number` and changed in the last `limit` seconds,
    else None (#491): its run still works on it. A stalled PR does not count, so a takeover stays possible."""
    for p in pulls:
        t = datetime.datetime.fromisoformat(p["updated_at"].replace("Z", "+00:00")).timestamp()
        if p["head"]["ref"] != me and p["state"] == "open" and now - t < limit and closes(number).search(prose(p["body"])):
            return p["number"]
    return None


def conflict_pr(pulls, number, now, pushed, limit=CONFLICT):
    """Number of an open PR that closes ticket `number`, has the label `conflict` (Automerge could not merge it) and
    no new commit for `limit` seconds, else None. pushed(p): the Unix time of its head commit. Its run reported and
    went on to the next ticket, so its claim has no beat: 9 of 12 takeovers in 24 hours waited 30 minutes (#1773)."""
    for p in pulls:
        if p["state"] == "open" and "conflict" in [x["name"] for x in p.get("labels", [])] \
                and closes(number).search(prose(p["body"])) and now - pushed(p) >= limit:
            return p["number"]
    return None


def head_time(p):
    t = api(f"commits/{p['head']['sha']}")["commit"]["committer"]["date"]
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()


def stuck(tickets, tips, now, limit=STALE):
    """[(number, reason)] of the `in-progress` tickets whose run stopped: the claim had no beat for `limit` seconds,
    the run released it and left the label, or the ticket has no claim ref and no change for `limit` seconds.
    tickets: {number: Unix time of the last change}; tips: {number: (subject, Unix time) of its highest slot}.
    Only the claim decides, not the PR: Unconflict and Automerge merge main into the PR of a stopped run and
    comment on it, so #2160 and #2228 looked alive for 6 hours with red CI, and #2049 had no PR to find."""
    out = []
    for n, changed_at in sorted(tickets.items()):
        line, t = tips.get(n, (None, changed_at))
        if now - t >= limit and (line is None or line.startswith("Release") or stale(line, t, now, limit)):
            out.append((n, f"{(line or 'no claim').split(' by ')[0]}, {(now - t) / 60:.0f} min ago"))
    return out


AGENT_BRANCH = re.compile(r"^(agent/|claude/|ccr-)")   # the prefixes that Automerge merges (`automerge.yml`, #3383)


def stuck_lines(found, pulls, checks):
    """The `--stuck` lines of `stuck()` results. A PR that only waits for its quick CI or for Automerge
    (`pacer.ci_wait`, the rule of `pacer.stuck`) gives no line; a green PR that Automerge never merges (no agent
    branch, no label `automerge`) waits for the owner, not for a takeover (#5331). checks: sha -> its check runs."""
    import pacer
    out = []
    for n, reason in found:
        pr = next((p for p in pulls if closes(n).search(prose(p.get("body")))), None)
        try:
            wait = pr and pr["head"].get("sha") and pacer.ci_wait(pr, checks(pr["head"]["sha"]))
        except Exception:                               # no check runs: a takeover line as before
            wait = None
        labels = {lb["name"] for lb in (pr or {}).get("labels") or []}
        if wait == "green" and not AGENT_BRANCH.match(pr["head"]["ref"]) and "automerge" not in labels:
            out.append(f"#{n} PR #{pr['number']} waits for the owner (no agent branch, no label automerge)")
        elif not wait:
            out.append(f"#{n} {'PR #' + str(pr['number']) if pr else 'no PR'}: {reason}")
    return out


def tips(remote="origin"):
    """{ticket: (subject, Unix time)} of the highest claim slot of each ticket, with one ls-remote and one fetch."""
    top = {}
    for line in git("ls-remote", remote, "refs/heads/claim/*").stdout.splitlines():
        sha, ref = line.split("\t")
        m = re.fullmatch(r"refs/heads/claim/(\d+)(?:-(\d+))?", ref)
        if m and int(m.group(2) or 1) >= top.get(int(m.group(1)), (0, ""))[0]:
            top[int(m.group(1))] = (int(m.group(2) or 1), sha)
    if top:
        git("fetch", "-q", remote, *[f"refs/heads/{slot(n, k)}" for n, (k, _) in top.items()])
    out = {}
    for n, (_, sha) in top.items():
        t, _, line = git("log", "-1", "--format=%ct %s", sha).stdout.strip().partition(" ")
        out[n] = (line, int(t))
    return out


def stale_limit(number, remote="origin"):
    """CONFLICT seconds when a PR of ticket `number` waits on a merge conflict (`conflict_pr`), else STALE."""
    if not on_github(remote):
        return STALE
    pr = conflict_pr(api("pulls?state=open&per_page=100"), number, time.time(), head_time)
    return CONFLICT if pr else STALE


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("number", type=int, help="ticket number (--comment: the comment ID, --refill: the epic)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--release", action="store_true", help="give the own claim back")
    g.add_argument("--takeover", action="store_true", help="claim the next slot also when the open claim is stale")
    g.add_argument("--show", action="store_true", help="print the claim refs and their tip commits")
    g.add_argument("--beat", action="store_true", help="show that the own run is alive")
    g.add_argument("--stale", action="store_true", help="exit 0 when the open claim had no beat for 30 "
                   "minutes (10 when its PR has the label `conflict` and no new commit for 10 minutes)")
    g.add_argument("--stuck", action="store_true", help="list the in-progress tickets of stopped runs (number 0); "
                   "exit 1: none")
    g.add_argument("--guard", action="store_true", help="before a push: beat; exit 1 when another branch has a PR")
    g.add_argument("--adopt", metavar="NAME", help="take over the claim that the pacer made as NAME (the brief of the run)")
    g.add_argument("--comment", action="store_true", help="lock the owner comment with this ID")
    g.add_argument("--refill", action="store_true", help="lock the new sub-issues of this epic (0: the whole refill)")
    g.add_argument("--fixmain", action="store_true", help="lock the Fix main ticket of the break in --state SHA (number 0)")
    g.add_argument("--review", action="store_true", help="lock the process review after its gap of merged PRs (number 0)")
    g.add_argument("--reviewed", choices=("change", "none"), help="after the review: set the next gap")
    g.add_argument("--roadmap", action="store_true", help="lock the roadmap review after 100 merged PRs (number 0)")
    g.add_argument("--prune", action="store_true", help="delete the refs of closed tickets and old locks (number 0; "
                   "claims.yml: runs cannot delete refs)")
    ap.add_argument("--state", help="--refill: the state part of the lock (default: closed sub-issues, or the hour); "
                    "--fixmain: the commit that broke main (default: the head of origin/main)")
    ap.add_argument("--pr-branch", metavar="BRANCH", help="--guard: the branch of a PR that this run took over")
    ap.add_argument("--or", dest="more", type=int, nargs="+", default=[], metavar="N",
                    help="a claim: when another run has the ticket, try these tickets in this order (one call)")
    ap.add_argument("--remote", default="origin")
    a = ap.parse_args(argv)
    # A claim on a detached HEAD would be named `unknown`: the next beat of the run then calls its own claim a takeover (#155).
    writes = a.comment or a.refill or a.review or a.roadmap or not (
        a.release or a.show or a.beat or a.stale or a.stuck or a.guard or a.adopt or a.prune or a.fixmain or a.reviewed)
    if writes and who() == "unknown":
        print("detached HEAD: check out your branch first (`git checkout -B <branch> origin/main`)")
        return 2
    if a.prune:
        gone = prune(a.remote)
        print("\n".join(f"deleted claim/{n}" for n in gone) or "nothing to delete")
        return 0
    if a.comment:
        if claim_comment(a.number, a.remote):
            print(f"claimed comment {a.number}")
            return 0
        print(f"comment {a.number}: another run handles it")
        return 1
    if a.fixmain:
        sha = (a.state or git("rev-parse", f"{a.remote}/main", check=False).stdout.strip())[:7]
        if claim_fixmain(sha, a.remote):
            print(f"claimed fixmain {sha}")
            return 0
        print(f"fixmain {sha}: another run makes the ticket")
        return 1
    if not deep_lane() and (a.review or a.roadmap or a.refill and not main_may_refill(a.number, a.remote)):
        kind = ("process review" if a.review else "roadmap review" if a.roadmap
                else "queue refill" if not a.number else "close check or split")
        print(f"the deep lane does the {kind} (`reserved` in agent.toml names `deep`): skip it")
        return 1
    if a.review or a.roadmap:
        kind = "review" if a.review else "roadmap"
        key, gap = review_slot(kind, a.remote)
        if key and claim_lock(kind, key, a.remote):
            if a.roadmap and on_github(a.remote):         # the roadmap skill has no end step: count from its start
                from dashboard import api as call
                body = api(f"issues/{STATUS}")["body"]    # read again: other runs and the dashboard change it too
                call(f"issues/{STATUS}", "PATCH", {"body": with_state(body, {**agent_state(body), "last_roadmap": utc()})})
            mark_commits()                                # a deep run can do only the review: its PRs are run work
            print(f"claimed {kind} {key}")
            if a.review and on_github(a.remote):          # the misses of step 0 of the `improve` skill
                last = agent_state(api(f"issues/{STATUS}")["body"]).get("last_review")
                print("\n".join(f"owner work #{n}: {title}" for n, title in owner_since(last, a.remote))
                      or "owner work: none")
            return 0
        print(f"no {kind} now: fewer than {gap} PRs merged since the last one, or another run does it")
        return 1
    if a.reviewed:
        from dashboard import api as call
        body = reviewed(api(f"issues/{STATUS}")["body"], a.reviewed == "change", ready=ready_tickets(a.remote))
        call(f"issues/{STATUS}", "PATCH", {"body": body})
        print(agent_state(body))
        return 0
    if a.refill:
        state = a.state or refill_state(a.number, a.remote)
        key = f"{a.number}-{state}"
        if claim_refill(a.number, state, a.remote):
            mark_commits()
            print(f"claimed refill {key}")
            return 0
        print(f"refill {key}: another run makes the tickets")
        return 1
    if a.stuck:
        issues = api("issues?state=open&labels=in-progress&per_page=100")
        tickets = {i["number"]: datetime.datetime.fromisoformat(i["updated_at"].replace("Z", "+00:00")).timestamp()
                   for i in issues if "pull_request" not in i}
        pulls = api("pulls?state=open&per_page=100")
        import pacer
        lines = stuck_lines(stuck(tickets, tips(a.remote), time.time()), pulls, pacer.head_checks)
        if lines:
            print("\n".join(lines))
        return 0 if lines else 1
    if a.show or a.stale:
        found = refs(a.number, a.remote)
        for k in sorted(found):
            ref = slot(a.number, k)
            age = (time.time() - changed(ref, a.remote)) / 60
            print(ref, subject(ref, a.remote), f"({age:.0f} min ago)")
        if a.stale:
            ref = slot(a.number, max(found)) if found else None
            return 0 if ref and stale(subject(ref, a.remote), changed(ref, a.remote), time.time(),
                                      stale_limit(a.number, a.remote)) else 1
        return 0
    if a.beat:
        ref = release(a.number, a.remote, word="Beat")
        print(f"beat {ref}" if ref else "nothing to beat")
        return 0
    if a.adopt:
        return adopt(a.number, a.adopt, a.remote)
    if a.guard:
        ref = release(a.number, a.remote, word="Beat")      # exits with an error on the claim of another run
        if not ref:
            print(f"no claim of #{a.number}: stop")
            return 1
        issue = api(f"issues/{a.number}") if on_github(a.remote) else None
        if isinstance(issue, dict) and issue.get("state") == "closed":      # closed during the run (#4249)
            print(f"#{a.number} is closed: stop, release and pick no new work on it")
            return 1
        back = revived(base=f"{a.remote}/main")
        if back:
            print(f"docs/LEARNINGS.md keeps {len(back)} lines that main removed (union merge, #563): remove them")
            print("\n".join(back))
            return 1
        other = foreign(a.number, f"{a.remote}/main")
        if other:
            for m, commit in other:
                print(f"the branch carries commits of #{m} ({commit}): remove them from the branch")
            return 1
        pr = on_github(a.remote) and other_pr(api("pulls?state=all&per_page=30"), a.number, who(), a.pr_branch,
                                                isinstance(issue, dict) and issue.get("state") == "open")
        if pr:
            print(f"PR #{pr} of another branch closes #{a.number}: stop and release")
            return 1
        print(f"beat {ref}, no PR of another branch")
        return 0
    if a.release:
        ref = release(a.number, a.remote)
        print(f"released {ref}" if ref else "nothing to release")
        if ref and on_github(a.remote):
            stop(a.number)
        return 0
    for number in [a.number, *a.more]:              # --or: the next candidate in the same call (#3459: one call each)
        code = claim_ticket(number, a.takeover, a.remote)
        if code != 1:
            return code
    return 1


def adopt(number, name, remote="origin"):
    """The first beat of a run that the pacer started with a brief: the claim `name` of the pacer becomes the claim of
    this branch, and the lane of the claim becomes the lane of the run (git config, as `cycle_start.py --lane`).
    0: the ticket is yours; 1: the claim is not open with that name any more (a takeover after a late start)."""
    issue = api(f"issues/{number}") if on_github(remote) else None
    if isinstance(issue, dict) and issue.get("state") == "closed":      # closed after the pacer's claim (#4249)
        print(f"#{number} is closed: follow the skill without the brief")
        return 1
    found = refs(number, remote)
    line = subject(slot(number, max(found)), remote) if found else ""
    if line.startswith("Release") or line.split(" ")[3:4] not in ([name], [who()]):
        print(f"#{number}: no open claim of {name} ({line or 'no claim'}): follow the skill without the brief")
        return 1
    if m := re.search(r" lane (\w+)$", line):
        git("config", "travel-aggregator.lane", m[1])
    ref = release(number, remote, word="Beat", adopt=name)
    if ref:
        mark_commits()
    print(f"adopted {ref}: #{number} is yours" if ref else f"#{number}: the beat failed, follow the skill without the brief")
    return 0 if ref else 1


HOOK = """#!/bin/sh
# Written by framework/tools/claim.py: each commit of a run gets the trailer Agent-Run. A merge on main without it is the work of
# an owner session, a miss of the improve loop (dashboard.owner_work, owner 2026-10-29).
git interpret-trailers --in-place --if-exists doNothing --trailer "Agent-Run: {lane}" "$1"
"""


def mark_commits():
    """Install the `commit-msg` hook of HOOK in this clone (also its worktrees) after a claim, an adopt or a lock: each
    run makes one before it commits, an owner session does not. A hook of another tool stays."""
    path = git("rev-parse", "--git-path", "hooks/commit-msg", check=False).stdout.strip()
    if not path or os.path.exists(path) and "framework/tools/claim.py" not in open(path, encoding="utf-8").read():
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(HOOK.format(lane=git("config", "--get", "travel-aggregator.lane", check=False).stdout.strip() or "main"))
    os.chmod(path, 0o755)


def claim_ticket(number, takeover=False, remote="origin"):
    """Claim ticket `number` (a takeover with `takeover`): 0 and the ticket text when the claim is ours, 1 when another
    run has it or the ticket is closed."""
    issue = api(f"issues/{number}") if on_github(remote) else None
    if isinstance(issue, dict) and issue.get("state") == "closed":   # the candidate list was older (#2339)
        print(f"#{number} is closed: pick the next candidate")
        return 1
    comments = api(f"issues/{number}/comments?per_page=100") if on_github(remote) else []
    if not takeover and on_github(remote):
        other = started_by_other(comments, who(), time.time())
        if other:
            print(f"#{number} owned by another run: `{other}` was first (\"Started by\" less than 30 minutes ago). Pick"
                  " the next candidate, do not comment.")
            return 1
        pulls = api("pulls?state=open&per_page=100")
        pr = active_pr(pulls, number, who(), time.time())
        if pr:
            print(f"#{number} owned by another run: its PR #{pr} closes #{number} and changed less than 30 minutes ago."
                  " Pick the next candidate, do not comment.")
            return 1
    ref = claim(number, takeover, remote, stale_limit(number, remote) if takeover else STALE)
    if ref:
        mark_commits()
        print(f"claimed {ref}")
        if on_github(remote) and not takeover:
            start(number)
        if isinstance(issue, dict):
            print(ticket_text(issue, comments))
        return 0
    print(f"#{number} owned by another run: {first(number, remote)} was first. Pick the next candidate, do not comment.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:          # git(check=True): network, permission, a missing remote
        fail(f"git {' '.join(e.cmd[1:])} failed:\n{e.stdout or ''}{e.stderr or ''}")
