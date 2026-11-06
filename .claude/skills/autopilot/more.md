# Autopilot: more tickets in one run

Read this file after step 8 when the argument asks for more than 1 ticket (part of the `autopilot` skill, #1700).

## Next tickets of the brief

A brief of the pacer with a `next: A B` line (#5076; in the report give `--source next` or `--source cycle_start`
for each ticket after the first, and `--next-failed N` for each `next:` ticket that another run had, #5308): after the report (step 8) of each ticket, do the quota check
of `scheduled` step 3b first. Then `git fetch origin main && git checkout -B <session branch>-<k> origin/main` and
`python3 framework/tools/claim.py A --or B` (one call: it tries B when another run has A; one number when the line has
one). Exit 0: start at step 6 with the claimed ticket (the claim prints the ticket and its comments; then
`python3 framework/tools/ticket_context.py N` once). Exit 1, or no `next:` ticket left: do steps 1 to 5 of `start.md`
as below. Continue until the `context:` limit of the brief, a usage limit, or no ready ticket: do not stop after 1
ticket to let the pacer pick (90 of 110 runs did 1 ticket; 1 ticket per run costs 0.37M eq per PR, 3 cost 0.19M).

## Later tickets with no brief

If the argument asks for more than 1 ticket, go back to step 2 after step 8 (finish stalled PRs of other runs, then new owner
feedback, step 3: run `python3 framework/tools/cycle_start.py --last N` again, N = your last ticket: within a priority it puts
the tickets of the same epic or files first, and the code that you read already makes them cheaper). The PRs of this run (on `<session branch>` or `<session branch>-<k>`)
are yours in step 2: when one is red or conflicted, check out its branch (`git fetch origin <b> && git checkout -B <b>
origin/<b>`) and fix it there (`python3 framework/tools/merge_main.py --push N`).

Do each later ticket on a new branch, also while the PR of the last ticket is open: do not wait for that PR (one run
spent 32 calls on such a wait, 2026-10-28). Before the claim of step 5, run `git fetch origin main && git checkout -B
<session branch>-<k> origin/main` (k = 2, 3, ...: one more for each new branch of this run; fetch `main` alone: a fetch
that also names a deleted branch fails as a whole). The scheduled task allows the push to these branches.
`framework/tools/claim.py` names the owner of a claim by the current branch, so claim, beat, guard and push on the new branch.
Push it with `git push -u origin <session branch>-<k>`, and check that the output shows `-> <session branch>-<k>`.
The open PR of the last ticket needs no wait: Automerge merges it when CI is green, and `unconflict.yml` merges `main`
into it. Never force-push: the auto mode denies it ("Git Destructive"; 33 runs lost a step on it on 2026-10-26).
Start a next work item only when the context is below 120k tokens (`python3 framework/tools/tokens.py` prints it as `peak`),
or below the `context:` line of the brief of the pacer (`pacer.context_limit`: higher while the task is near its hourly
start limit, so that no fresh run can start, #4190).
A work item is a ticket, a takeover of a stuck PR, a refill, an epic check, a roadmap review or a process review: two
deep runs that did a takeover, a review and a ticket reached 200k and used 1.8M and 2.3M eq (2026-10-29).
A fresh run pays about 0.18M eq before its first claim (the 47k base written to the cache at 2 times the price, and
the start calls). A next ticket in this run pays about 30 calls × 0.1 × the extra context. Below 120k the next ticket
is cheaper here (2 tickets per run: 0.38M eq per PR, 1 ticket: 0.62M), above it a fresh run is cheaper
(2026-10-29; the runs of 2 to 3 tickets that reached 200k to 260k used 42 % of the tokens).

Argument `max`: continue until no ticket is ready, a usage limit stops you, or the context is 120k tokens or more.
Do not start other runs: a run of the scheduled task has no `fire_trigger` (#566). The pacer (`pacer.yml`, #3193)
starts the runs that the quota target misses, every 10 minutes. A fresh run has a small context, so it works faster.
