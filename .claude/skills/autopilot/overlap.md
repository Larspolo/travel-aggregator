# Autopilot: runs can overlap

Read this file when a ticket, a branch or a PR of another run is in your way: an old claim, a stalled PR, a takeover
(part of the `autopilot` skill, #1700).

## Claims, stale runs and takeovers

Several runs work at the same time: the owner wants maximum use of the quota. Each run shows that it is alive:
it runs `python3 framework/tools/claim.py N --beat` for its ticket N at least every 20 minutes (after each verify level and
before each push). A usage limit stops all runs at about the same time, and a stopped run never
continues (#231). So a ticket with `in-progress`, and its PR, belong to the other run while
`python3 framework/tools/claim.py N --stale` exits 1, or the ticket, its branch or its PR changed less than 30 minutes ago by a
run: do not touch them. A merge commit or a comment of a workflow (Unconflict, Automerge) does not count: these
workflows also change the PR of a stopped run (`python3 framework/tools/claim.py 0 --stuck`, "Stuck tickets"). Else the
other run stopped: take the ticket over with `python3 framework/tools/claim.py N --takeover` and say so in a comment. Exit 1 means that another run took it over first: leave it.
A ticket with `in-progress` and no claim ref (older runs): the same rule with the ticket, branch and PR times only.
The workflow `automerge.yml` merges an agent PR when its CI is green (#232, #370). A PR whose CI runs or is green waits
for that workflow: it is not stalled. Exception: a PR with red CI, label `conflict` or a merge conflict, and with no new
commit and no new comment of a run for 30 minutes, is stalled. A PR with label `conflict`, no new commit for 10 minutes and a
ticket claim with no beat for 10 minutes is stalled too, also when Automerge commented later: its run reported and went
on (`claim.py N --stale` and `--takeover` use 10 minutes then, #1773). Take it over at once
(`python3 framework/tools/claim.py N --takeover` with the ticket number N, then comment "Taken over by `<your branch>`: stalled."), for example when its run stopped. Then read the PR comments again: if an older "Taken over by" comment of another branch is less than
30 minutes old, leave the PR to that run. Work on the PR from your session branch (`claim.py` takes the run name
from the current local branch), push with `git push origin HEAD:<branch of the PR>`, and run the guard with
`--pr-branch <branch of the PR>` (#361). A merge of main: `git checkout -B <session branch> origin/<branch of the PR>` first (the tool merges into the
current branch: on a session branch at `main` it merges nothing and the push fails, #4175), then
`python3 framework/tools/merge_main.py --push N --pr-branch <branch of the PR>` does both (#3678). Then wait for its quick CI: `python3 framework/tools/ship_pr.py N --ci --pr-branch <branch of the PR>` (#5014).
A PR whose ticket has no `in-progress` label is free: any run can fix it (hand-off).
If your usage limit stops you, the next run continues your work through this rule.


## Stuck tickets

`python3 framework/tools/claim.py 0 --stuck` (autopilot step 2) prints one line for each `in-progress` ticket whose run stopped:
no beat for 30 minutes, a release that left the label, or no claim ref and no change for 30 minutes. Only the claim
decides: bots keep the PR of a stopped run busy (#2160 and #2161 stayed red for 6 hours, #2049 had no PR to find).
Take over the first ticket (`python3 framework/tools/claim.py N --takeover`, then comment "Taken over by `<your branch>`: stuck.").
Exit 1 there: another run was first, take the next line. With a PR: fix it at step 6.8. With no PR: do the ticket
from step 6 (start from its branch when it has one). That is the work of this cycle.
A ticket whose PR only waits for its quick CI or for Automerge gets no line (`pacer.ci_wait`). A line
`PR #M waits for the owner (no agent branch, no label automerge)`: a green PR that Automerge never merges. Do not take it
over: add `needs-human` and a comment that asks the owner to add the label `automerge` to PR #M or to merge it, then
`python3 framework/tools/claim.py N --release` (#5331).

## The flow brake

`python3 framework/tools/usage.py --flow` (autopilot step 2, owner, 2026-10-27) exits 1 when too many agent PRs wait (older
than `pr_minutes`, no `hold`) or CI has a queue: then CI or the merges are the bottleneck, not the quota, and a new PR
only makes more conflicts. The run then only repairs: fix one red, stalled or conflicted PR, also an older PR whose
run stopped. When no PR needs a fix, do no new ticket: go to step 8 and report "flow brake: no PR to repair".

## Fix main

One break of main gave 8 "Fix main" tickets in 6 minutes and 4 fix PRs (#3480): each run found no open `P0` ticket
and made its own. Before you make a "Fix main" ticket (step 2), also for a break that CI does not show (a workflow
that GitHub refuses), lock it: `python3 framework/tools/claim.py 0 --fixmain --state SHA` (SHA = the commit that broke main).
Exit 0: make the ticket. Exit 1: another run makes it: wait one minute, list the open `P0` tickets again and claim
that one, or pick another ticket.
