# Autopilot: triage of large tickets, epics and the queue refill

Read this file in step 4 when a ticket has `size:L`, in step 5 before the pick (the epic check, at most 3 epics),
when fewer tickets are ready than the target number of runs (the refill), and in a haiku lane run. Part of the `autopilot` skill (#1700).

## Haiku lane (step 5)

When the argument names `lane haiku` (the scheduled task "travel-aggregator autopilot haiku"), run
`python3 framework/tools/cycle_start.py --lane haiku` first: it sets `git config travel-aggregator.lane haiku` (the claims then tell the
pacer that this run is cheap, #1727). Pick only from its section `Candidates`, skip the epic check, the queue refill, the roadmap review and the
process review, and stop when no `lane:haiku` ticket is ready. Do one ticket per run: stop after its report,
also with the argument `max` (a Haiku call costs 5 times more above 100k prompt tokens, and the Haiku runs
reached 91k to 200k; the pacer starts a fresh run with a 65k context for the next ticket, 2026-10-28). A ticket that is not as clear as its label says: release
the claim, remove `lane:haiku`, comment why in one line, and take the next one. Write the report with `framework/tools/report.py` (`report.md`): it adds `· lane haiku` from the git config (#1982).

## Deep lane (step 5)

The main runs work at low effort (owner, 2026-10-28). The scheduled task "travel-aggregator autopilot deep" runs at high
effort for the work where the thinking matters more than the typing (`ticket` skill, "Model lanes"). When the argument
names `lane deep`, run `python3 framework/tools/cycle_start.py --lane deep` first: it sets `git config travel-aggregator.lane deep` (the
claims and the report then name the lane). Pick from its section `Candidates`. With no candidate, it prints the section `Deep work` (#1377): the target, the
claims and the reason of the pacer for this run, with the lock of each kind of work. Do that work (no second
`usage.py --fire`, no lock of another kind); "no deep work": go to step 8. A deep run does the epic check and the queue refill of step 5, the roadmap
review and the process review: while `reserved` in `[pacing]` of `steering/system/system.toml` names `deep`, `claim.py` gives those
locks (`--review`, `--roadmap`, `--refill`) only to deep runs, and the other runs skip them. Stop when no `lane:deep`
ticket is ready and the refill is done, or at 120k context (`more.md`): the main runs take the other tickets for less.

## Large tickets (step 4)

If the size is L, split it into S or M sub-issues with the `ticket` skill. Give the parent label `epic`.
If the top candidate of step 5 has `size:L`, split it now (`ticket` skill), then pick again.
While `reserved` in `agent.toml` names `deep`, only a deep run splits (`claim.py E --refill` exits 1 in the other
runs): give the ticket `lane:deep` and pick the next one.

## Epics and refill (step 5)

Epics first: an epic is never a candidate, so its rest of the work needs sub-issues. Before you claim a ticket, look
at the open epics (label `epic`, not `needs-human`, not `muted` or `after-release`, any priority) with no open sub-issue, at most 3 per run. The
priority does not matter here: a check of `P2` and `P3` epics was skipped, and six finished epics stayed open (#799).
For each one, lock it first: `python3 framework/tools/claim.py E --refill` (E = the epic). Exit 1: another run checks or
refills it, skip the epic (#505, #371: two runs checked epic #354 at once, and the second check was waste). Only after the
lock, read its acceptance criteria and all its comments. An owner comment after the last agent comment comes
first: handle it as in step 3 (lock, answer). Do not post a request that the epic already has (#820: two runs asked
the same thing, and no run answered the owner's question between them). An epic without a criterion that checks that the
whole goal is covered (owner rule, #820: never only "All sub-issues are closed") gets one first (`ticket` skill, "Split
an L ticket"). Check that criterion against the full scope (for "all X": the full list, for example a wiki of the original) and
name each missing item. When `steering/project/PRINCIPLES.md` has the section "Try a feature", do what it says first
(for example a `needs-human` test ticket, or a build); the epic waits for it. Close the epic with a comment only when all criteria are met
(name the evidence for each, then the label `close`: `owner.md`, "Close an issue", #1740). When the epic waits only for open agent
tickets (all other criteria met), end the check comment with the line `Close this epic when #N merges.` (more tickets:
`Close this epic when #N and #M merge.`, #617): when each closes as completed by a merged PR, `close.yml` adds the evidence comment and the label `close`
(`framework/tools/epic_autoclose.py`; an open owner check with `needs-human` does not stop it, #922), and the pacer starts no epic check for it. When an open criterion waits only for
an open ticket of another epic, add a line "Part of #E" to the body of that ticket: else the pacer starts a deep run
for the epic check of E in each cycle (`usage.refill_need`). The lock of the check (above) covers the close and the new sub-issues of the epic: do not lock it a second time
in the same run (#371). Then make one sub-issue (same priority)
for the criteria that an agent can do. A criterion that needs the owner stays on the epic. Then pick again (#176, #155 waited while P3 tickets ran).
Release checks: when `cycle_start.py` prints the section "Release checks (no ticket, make them in the refill)", a deep
run makes a check ticket for each listed check (`roadmap` skill, "Release checks"), also when the open epics have work
left, and writes its number in the `ticket` column of `steering/project/RELEASE.md` (a PR). Lock it first:
`python3 framework/tools/claim.py 0 --refill` (exit 1: another run makes them, #3342).
Refill the queue when fewer candidates are ready than the target number of runs, so that parallel runs always find
work: N = the target and R = the ready tickets of `python3 framework/tools/usage.py --fire` (its stderr line). Refill only when
R < N, and make at most 2 × N − R tickets, so the queue stays at most twice the target (owner, #664: when fewer runs work
again, a large queue only waits). Do this at most once per run, in about 10 minutes.
Lock it first: `python3 framework/tools/claim.py 0 --refill` (one run per 10 minutes). Exit 1: another run makes the whole
refill; then refill one open epic instead (the first one with open goals that an agent can do, under its lock of the epic check above):
up to 10 sub-issues (within the cap) for its open goals, then pick again. The pacer starts refill runs from the
tickets that the queue misses (`usage.refill_count`, owner, 2026-11-06): one run for each `refill_tickets` of N − R, at
least 1, less the live refill runs (a refill lock younger than `refill_minutes`, `usage.refill_live`). At most
`refill_runs` (`[pacing]` of `steering/system/system.toml`) and one run per refill source with work (the whole refill
when it has a source, and each epic that waits for its check, `usage.refill_sources`, #378), and only 1 when no open ticket is less than 60 minutes old (`usage.new_ticket`): an empty refill run costs quota.
It starts none when R >= N and no epic or release check waits (`usage.refill_need`, #3547), and none when R < N and the
refill has no source: no such check, no roadmap feature with no epic and no fallback (#3560). A due process or roadmap
review starts one too (deep locks), also while refill runs are live: a review has its own lock (owner, 2026-10-29).
Give each new ticket its lane (`ticket` skill, "Model lanes"). Make all tickets of the refill (an epic and its
sub-issues too) in one call: `python3 framework/tools/new_tickets.py FILE.md` (`ticket` skill).
The lock of the epic check (above) covers its tickets too: do not lock the epic a second time (#371).
A `muted` or `after-release` ticket or epic (the owner holds it until later, 2026-10-26, #4175) is out of all these steps: no split, no check, no
new sub-issues, no `needs-human`. Still answer an owner comment on it (step 3).
Release focus (owner, 2026-11-01, `steering/project/RELEASE.md`; skip it and the release epic rule when the project has
no such file): before you make tickets for an open epic, check that its
feature is inside the focus (its section "Release focus" tells how to find the features that wait). An epic outside it gets the
label `after-release` and a one-line comment ("Waits for the release: release focus of `steering/project/RELEASE.md`"),
and no new sub-issue. Do not hold a ticket with `in-progress` or an open PR: let it finish and merge. Also each new follow-up ticket of a held epic or of milestone C work gets `after-release`.
Release epic (label `release`): its scope is the GitHub milestone of its version; a new sub-issue of it gets that
milestone too. It is done when its criteria are met (`steering/project/RELEASE.md`, "Release cycle");
close it with the label `close`, and `release.yml` makes the release. Tickets with `rank` (after a release) come first in
the refill: do the "Release cycle" of the `roadmap` skill, then the other steps.
When no source is left inside the focus, make tickets from the play test (`docs/PLAYTEST.md`, the comments of the
play-test tickets, P9 of `steering/project/PRINCIPLES.md`) and stop; do not make work outside the focus.
1. Split each `size:L` ticket N without open sub-issues (`ticket` skill), also when it is not a candidate yet. Lock it
   first with `python3 framework/tools/claim.py N --refill` (exit 1: skip it).
2. For each open epic whose sub-issues are all closed: make a sub-issue for each acceptance criterion that is
   still open and that an agent can do. A criterion that needs the owner stays on the epic.
3. Make up to 20 new tickets (within the cap) for the remaining goals of the open epics, and for the fallbacks in
   `docs/coverage.md`. When the open epics have no goal left that an agent can do, make the next epic from the
   feature list of `steering/project/ROADMAP.md` with the `roadmap` skill (the goals take turns). Each feature has an epic: run
   `python3 framework/tools/claim.py 0 --roadmap` (due after 30 merged PRs then, #3741, or at once when no run holds a claim and no ticket is ready, else after 60 minutes with no merged PR); exit 0: do the roadmap review now. Priority: that of the epic, else `P3`. Never `P0` or `P1`, except for
   a `tooling` ticket that blocks other tickets. Look for duplicates first, and list the open issues again just
   before you make the tickets: parallel runs make the same follow-ups at the same time (#300, #301).
   Run that list in its own tool call and read it before the create calls: a list and the creates in one call made 7 copies (#2778).
   Read the gap lists from main, not from your branch (`git fetch origin main`, `git show
   origin/main:tests/data/civ_bonuses.jsonl`), and also list the issues closed in the last 2 hours: #2340 copied
   #2309, which merged while the branch was 20 minutes old, and #2306 copied the closed #2249.
4. Prefer tickets that depend on no open ticket and change other files than the claimed tickets (fewer conflicts).
5. An epic takes at most 100 sub-issues (GitHub: 422 "Parent cannot have more than 100 sub-issues", #2538): a new
   ticket of a full epic says "Part of #E" in its body only; name it in the refill comment on the epic.
