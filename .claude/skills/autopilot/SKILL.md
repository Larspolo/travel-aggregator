---
name: autopilot
description: Do one automatic work cycle on travel-aggregator. Read the owner's feedback, triage new issues, do the top ticket, ship it as a merged PR, report the run and improve the process. Use when a scheduled run starts, or when the owner says "work", "next ticket" or "/autopilot". Argument - the number of tickets to do (default 1).
---

# Autopilot: one work cycle

The project values are in `agent.toml` (#905; section `Status` of `cycle_start.py` prints them): `repo` (`OWNER/NAME`
below), `owner` (the GitHub login of the owner), `branch` (the default branch, `main` below), the status issue.
Follow each step in sequence. Do not skip the report (step 8).

The rare cases are in files next to this one (#1700). Read a file only when its case occurs:

| File | Read it when |
|---|---|
| `start.md` | Steps 1 to 5: at the start of a run with no brief of the pacer, and before each later ticket. |
| `github.md` | You need a `gh api` path (issues, labels, PRs, CI, sweep) or the list of labels. |
| `overlap.md` | A ticket, branch or PR of another run is in your way: a stale claim, a stalled PR, a takeover. |
| `queue.md` | Step 4 or 5: a `size:L` ticket, the epic check, the queue refill, the haiku and deep lanes. |
| `conflict.md` | A PR has a merge conflict (label `conflict`, or `mergeable_state` is `dirty`). |
| `owner.md` | You must ask the owner, the auto mode denies an action, a ticket is wrong, or step 7 needs a check ticket. |
| `process.md` | Step 6.5 (the questions of step 9) and after step 8 (the review slot). |
| `report.md` | Step 8 (the status issue, the metrics line). |
| `more.md` | After step 8, when the argument asks for more than 1 ticket (branch reset, push). |

## GitHub access

Use the GitHub MCP tools (`mcp__github__*`) when the session has them. Else use the REST API with `gh api`
(`github.md`). Cloud sessions block GraphQL, so `gh issue list` and `gh pr create` fail there; `search/issues` needs
`is:issue` in `q`. Put long text in a file and pass it with `-F body=@file.md`.

## Runs can overlap

Several runs work at the same time. Each run runs `python3 framework/tools/claim.py N --beat` for its ticket N at least every
20 minutes (after each verify level and before each push). A ticket with `in-progress`, and its PR, belong to another
run while `python3 framework/tools/claim.py N --stale` exits 1 or a run changed them in the last 30 minutes: do not touch
them. A beat or guard that says another run took your ticket over: stop that ticket at once (no push, no comment,
no release) and pick the next one. Takeovers, stalled PRs, hand-offs: `overlap.md`.

## 1. to 5. Start, open work, feedback, triage, pick

A run with an adopted brief of the pacer (`scheduled` skill, step 0) starts its first ticket at step 6: the pacer did
steps 1 to 5 (`framework/tools/pacer.py`). Else, and before each later ticket, do steps 1 to 5 of `start.md` first.
In all runs, keep a short list of time sinks (for example "read buildings.py in full", "CI red: missing file") for the
report of step 8, and the `Usage:` line (of the brief, else of the first `cycle_start.py`).

## 6. Do the ticket

1. Branch: use the branch that the session instructions name. Else `git fetch origin main` and
   `git checkout -b agent/<number>-<short-slug> origin/main`.
2. Beat (`python3 framework/tools/claim.py N --beat`) at least every 20 minutes until you open the PR.
   Read the ticket and its comments (the claim prints them, #3459) first: the owner's comments win. Then `python3 framework/tools/ticket_context.py N` once: the code places of the body (#3829). A brief of the pacer has both: skip the two reads. Read only the code that the ticket needs (code map: `CLAUDE.md`). Use Grep.
3. For a bug, write a failing test first. Then change the code. Keep the diff small and in the existing style.
   Put new tests in a new file `tests/test_<topic>.py`: parallel tickets that append to the end of one test file
   conflict (66 merge conflicts in 6 hours on 2026-10-25).
   A ticket that changes only data files gets no new test, also when its body asks for one (owner, 2026-10-29, #4242):
   skip that part and say why in the PR (`docs/extend.md`). `ship_pr.py` stops such a change.
4. Verify with the `verify` skill (by the change; never the full fast suite: the quick CI runs it, owner #4187).
5. Improve the process (step 9, `process.md`) now, so that the changes go into the same PR.
6. Stage only the files of the ticket: read `git status --short` first (no `logs/`, worlds or images; not
   `docs/coverage.md` or a `MAX` change in `tests/test_coverage.py`: `coverage.yml` does it on main).
7. Ship in one call: `python3 framework/tools/ship_pr.py N --message MSG.txt --title "<ticket title>" --body BODY.md`
   (MSG.txt: subject in STE imperative, what and why, `Closes #<number>`; BODY.md: what changed, how you verified
   (a criterion that you did not do names its follow-up ticket, `open_part`),
   and all that a later run needs to fix a red CI with no other context, #4187).
   It commits, runs the lint of `agent.toml` (always) and the test files of the change (`--tested`: you ran them on this tree; the files whose `GUARDS` match the change still run, #1328), runs the guard (hard rule before each
   push: it fails when the claim is not yours or another branch has a PR that closes #N, #288), pushes and opens the
   PR. A PR that changes `packaging/` or a workflow with its own PR checks: add `--hold` (the label `hold` at once).
   Then it waits for the quick CI (about 6 minutes, #4784): give the Bash call `timeout: 600000`.
   Exit 3: do not push: `claim.py N --release` (when the claim is yours; it removes `in-progress`), comment the reason
   in one line on the ticket and pick the next ticket.
8. It prints `mergeable_state`. `dirty`, or exit 6 (Automerge found a conflict after the green CI, #5584): run
   `python3 framework/tools/merge_main.py --push N` (`conflict.md`), then `ship_pr.py N --ci`.
   Do not merge by hand: CI runs only the quick checks on each PR (lint and fast tests, about 6 minutes), and the
   Automerge workflow merges the PR when CI is green, removes `in-progress` and deletes the branch. Exit 5: the quick
   CI (or a check of `[ci] gates` in `agent.toml`) is red, go to 9 now (a red PR after the run ends costs a takeover by a cold run, #4784). The CI still runs at
   the time limit: `ship_pr.py N --ci` once, then continue. The job `browser` runs all slow tests on each PR, and the server tests
   run only each night on main: before the push, do the levels of the `verify` skill that the change needs (only the
   slow test files of the change, #822). Continue
   with step 7 and the next ticket. Step 2 of a later cycle finds a red or conflicted PR.
9. CI red → find the cause in the printed failed steps and tests, fix, commit, `ship_pr.py N --message MSG.txt`.
   After 3 failed attempts stop: comment the cause on the ticket, add `blocked` or `needs-human` and `hold`, run
   `claim.py N --release` (it removes `in-progress`), and go to step 8 of the skill (report).
   A failed test that passes on your tree with no change is a flake: make a `bug` ticket with the test, the CI run
   id and the assert line first, then start the failed jobs again once (#1409: 2 re-runs had no ticket).
10. Merge conflict → as in 8.
11. CI green → the Automerge workflow merges. Add label `hold` to the PR if it must not merge yet.

Ask the owner only with the label `needs-human` and a comment on the issue that needs the answer (owner rule, #862).
Never ask with PushNotification, in the session, or only in the status report. Details, denied actions, a wrong
ticket: `owner.md`.

## 7. Close the ticket

The merge closes the ticket (`Closes #N`), and the Automerge workflow removes `in-progress`. If the owner must check
something in the game, make a small check ticket without `needs-human` first (#580; the rules of a check: `owner.md`).

## 8. Report the run

Read `report.md` and do it: `### Process changes`, one report with the metrics lines (`report.py --post`).
Then run `python3 framework/tools/claim.py 0 --review` and `python3 framework/tools/claim.py 0 --roadmap` (`process.md`).

## 9. Improve the process (before the commit in step 6)

Answer the questions of `process.md`. Do the action for each "yes". Spend little time.

## More tickets

If the argument asks for more than 1 ticket, go back to step 2 after step 8: read `more.md` first (branch reset,
push). Never force-push. Start a next work item only when the context is below 120k tokens (`more.md`).
Argument `max`: continue until no ticket is ready, a usage limit stops you, or the context is 120k or more.
Do not start other runs (no `fire_trigger`, #566): the pacer (`pacer.yml`, #3193) starts them.
