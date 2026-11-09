---
name: improve
description: Review the whole agent system of travel-aggregator and make the changes that pay (CLAUDE.md, skills, tools, tests, CI workflows, the cloud setup script, settings), also large redesigns and changes that need owner steps. Use when `python3 framework/tools/claim.py 0 --review` gives the review slot to the run (autopilot step 9: after a gap of merged PRs, or soon after owner work on the system), after a run that failed or took more than 90 minutes, or when the owner asks for a process review.
---

# Improve the process

The aim: more closed tickets for the same quota, with the same quality, and **no owner work on the system**
(owner, 2026-10-29: "I would have wanted the improve skill to come up with these things too"). The owner must never
have to suggest an improvement. Each change that the owner makes by hand shows a lever that this loop did not see.

**Be bold** (owner, 2026-10-29). Make each change that pays, not only one per review: also a redesign of a part, also a
change that needs owner steps, also a pause of the project until the owner did them (step 4). "No change" is correct
only when each lever of step 3 is below its threshold, and the report gives the numbers.

**Count work, not time** (owner, 2026-10-29). A wait to measure a change counts merged PRs ("wait 50 PRs", not "wait
24 hours"): the speed of the project changes, and a paused project merges nothing. Only a real clock stays in time: a
quota window, a stale claim of a stopped run, a nightly job (`framework/docs/SYSTEM.md`, "Clock or count").

**The limit is the usage limit** (owner, 2026-10-27). The 7-day and the 5-hour windows limit the runs. So the main cost
of a loss is quota; minutes come second. Find the bottleneck from data, do not assume it. A known lever of step 3 with
its signal above the threshold is enough data. A hunch outside the levers is a thing to measure first.

## 0. Learn from the owner's work (misses)

`claim.py 0 --review` prints `owner work #N: <title>`: the PRs merged since the last review with no commit of a run
(each run commit has the trailer `Agent-Run:`: `framework/tools/claim.py` installs a `commit-msg` hook at each claim). `framework/tools/health.py` prints the same as
"Owner work", and "Misses": the issues that the owner opened to change the system (labels `process`, `tooling`,
`cleanup`). An owner comment on a process ticket that asks for a wider fix is a miss too (#1702).

For each item:
1. Read what the owner changed: `git log origin/main -1 --grep "(#N)$" --format=%B --stat`.
2. A feature or a steering choice of the owner (a game rule, a dashboard chart that the owner wanted): no miss. Write
   `feature` in the report and go on.
3. A change of the system: name its lever (step 3). Find the signal that would have found it, and add it when it is
   missing (a line of `framework/tools/health.py`, a field of the `Tokens:` or `Calls:` line). Then find the other places of the
   same lever and fix them too ("Fix all places", step 4). The owner fixed one place; this loop fixes the class.
4. Report it as `- <date>: miss #N (<lever>): <the new signal> · <the general change> (PR #n)`.

Misses come first: they are the changes of this review, before the largest loss of step 3.

## 1. Check the earlier changes

Read the lines of "Process changes" on the status issue that have `before:` numbers. For each change with at least 50
merged PRs after its merge (count them: `python3 framework/tools/health.py --prs 50 --until <merge time>` gives the "before"):
compute the same numbers now. Better → keep it. Not better → undo it, or fix the same loss in another way: that is a
change of this review. Fewer than 50 merged PRs → too early: keep it and say so.

## 2. Collect the data

Run `python3 framework/tools/health.py --prs 100 --compare` (about 2 minutes): the last 100 merged PRs, and under each line that
differs, the 100 PRs before (`  before: ...`). A change of more than 20 % between the two periods is a finding. It
prints CI, setup, takeovers, conflicts and their files, phases, quota per merged PR, release points per 1 % of 7-day
quota (the main number: progress to the goals 1 to 3 of `steering/project/ROADMAP.md` per quota; during a release
focus, the closed issues of the release milestone per 1 % of quota, #5552; while the roadmap grows, the line
`Features per 1 % of 7-day quota`: the closed roadmap epics), tokens and their sinks, lanes,
weak spots, misses, owner work, time waits, data in the code, review slots and files that do not belong in git.
`--hours N` only for a real clock (the night runs).

Also, only when a lever needs it:
- Tokens of one run: `python3 framework/tools/tokens.py --top 15`; the `Calls:` lines of the run reports (the most frequent
  commands of each run).
- Run reports and pacer cycles: the branch `metrics` (`git fetch origin metrics`; `status/`, `runs/`, `pacer/`).
- CI: the last 50 runs of each workflow and the steps of slow runs; the log of a failed job (`mcp__github__get_job_logs`).
- Environment: the `setup` minutes, and time sinks with "install", "download", "blocked" or "denied".
- `docs/LEARNINGS.md` and the "Process changes" list (what was tried before).
- Decisions: the share of `taken` in the last 10 lines of `steering/project/DECISIONS.md` and `steering/system/DECISIONS.md` with a recommendation. Lower than the 10
  before, or 3 lines with `new` → update `steering/project/PRINCIPLES.md` and `steering/system/PRINCIPLES.md` in this review.

## 3. Walk all levers

The levers are the kinds of change that the owner made by hand (PRs of owner sessions, 2026-10-28 and 2026-10-29) and
that this loop must find itself. Check each lever in each review: read its signal, compare it with its threshold.
A lever with no number is a measurement gap: lever 10.

| # | Lever | Signal | Threshold | Fix, strongest first | Owner PRs |
|---|---|---|---|---|---|
| 1 | Context per call | `Tokens:` `base` and its parts (`tools.py --top`: tools, system, repo, ...), `peak`; size of `CLAUDE.md`, `docs/LEARNINGS.md`, the skills | base above 30 % of eq, or repo part above 10k tokens | Deny unused tools and agent types, turn off unused skills (`skillOverrides`) in `.claude/settings.json`; move rows and lines to the topic doc that needs them; a learning line → a check (`guard-shell.sh`, a test); split a skill so that a step reads its own file; a subagent for a wide search (the tool `Agent` is denied: no run used it, #5615; allow it again first) | #3425, #3483, #3648, #3734, #3828, #4173, #5463 |
| 2 | Agent work that a tool or workflow can do | `Calls:` top commands; the same 3 or more calls in many runs; phases `read`, `claim`, `report` | a call sequence in 20 % of runs, or a phase above 15 % of the minutes | One-call tool (like `cycle_start.py`, `ship_pr.py`); a workflow (like Pacer, Automerge, Unconflict, Close, Claims); a hook; data written by a tool, not by the agent | #3201, #3211, #3311, #3614, #4172, #4184 |
| 3 | The cheapest model that does the job well | `Lane` lines (runs, PRs, cost); rework and red CI per lane; the kinds of `size:S` tickets that Opus runs do | a kind of ticket that a cheaper lane does at the same quality; a lane with rework above 10 % | Lane rules of the `ticket` skill ("Model lanes"); `reserved` and `weights` in `agent.toml`; a subagent with a cheap `model` for lists and searches in a run; a new lane (a new scheduled task: owner step) | #2690, #3147, #3392, #3609 |
| 4 | API calls | `Calls:` count of `gh api` and `mcp`; the REST budget in the pacer log; 403 and 429 in workflow logs | above 10 calls per ticket, or a workflow above half of its budget | Git in place of the API (refs, `merge-tree`, the branch `metrics`); one list call in place of one call per item; a cache; only the needed fields | #4171, #4172, #4178, #4180 |
| 5 | Merge conflicts by design | Conflicts per 100 merged PRs; the files and the tables of the conflict hunks | 3 conflicts per 100 PRs in one file or table | One file per item (`tests/test_<topic>.py`, one data line per item); a registry that finds its items (a glob), not a list; a generated file only on `main`; no test of the content of a data file | #2008, #3203, #3462, #4177 |
| 6 | Data in the code | `Data in the code` | a new place, or the count does not go down | A sub-issue of the data epic per place; `.jsonl` with `merge=jsonl` | #1909, #2100 |
| 7 | Conflicts that a merge driver can solve | Conflicts that a run solved by hand where both sides only added; `solved by Unconflict` | a file with 2 such conflicts | `merge=union` or `merge=jsonl` in `.gitattributes`; a rule of `framework/tools/unconflict.py`; `land()` of Automerge | #2004, #3199, #3202 |
| 8 | Clocks that measure work | `Time waits`; constants in minutes or hours in the tools that wait for work | any | `Start after: N PRs after #M`; a gap of merged PRs (`[review]` of `agent.toml`) | #2039, #3865 |
| 9 | Owner chores | `needs-human` tickets about the environment; owner PRs that paste, test hosts, set secrets; `Runs held by GitHub` and `started again by hand` | any step that the owner did twice | One file to paste; a check that names exactly what is missing; a workflow or an API that does the step | #1964, #3614, #4181 |
| 10 | Measurement gaps | A lever of this table with no number | any | Add the number to `framework/tools/health.py`, `framework/tools/tokens.py` or the pacer log first | #3819, #3970, #4171 |
| 11 | Quality | Rework, reopened tickets, bugs of check tickets, red night runs | rework above 5 % of the merged PRs | A check in the `verify` skill or CI; a rule from owner feedback; a fix of the flaky test | - |
| 12 | Waste of runs | Runs that merge nothing (`given back`), idle starts, lost claims, takeovers; `Pacer loop gaps` (no runs start); `Idle queue` (target > 0, no claim, no start, #5199) less its hours with `no work` (no ready ticket and no refill source: a wait for the owner) | above 5 % of the runs, a pacer gap above 1 h, or an idle stretch above 1 h with work | Rules of the pacer (`framework/tools/usage.py`) and of the claims (`framework/tools/claim.py`) | #3147, #4173 |

The threshold also counts a loss that comes back with its full cost: its quota, the takeovers that it causes, and
the rule lines that it added to `CLAUDE.md` and `docs/LEARNINGS.md` (each run loads them in each turn).

When the owner changes a part that no lever covers, add a row: a lever that the table does not name stays missed.

## 4. Make the changes

Each miss of step 0, each change of step 1 that did not help, and each lever above its threshold gets a change.
Write the "before" numbers first.

**Choose the strongest fix** (#1909, P10). Three levels: 1. a rule (text that each agent must remember and each run
loads), 2. a check that fails (a test, a CI step, a lint), 3. a structure that prevents the fault (a data file, a merge
driver, a generator, a workflow, a tool). Use the highest level that is in proportion. When a loss comes back after
its fix, the next fix goes one level up. A level-1 rule that stays is debt: make a ticket for its level-2 or level-3 fix.

**Fix all places** (#1909). Find all places with the same pattern (Grep, `ast`, a lint) and fix the class, not the
case. Make one epic for a large set (`ticket` skill), with all places as sub-issues, so the owner sees the whole plan.

**Each lever is a ticket on the board** (owner, 2026-10-27). First list the open process tickets
(`/issues?state=open&labels=process`). When one names the lever, claim it (`framework/tools/claim.py N`) and do it, or, when
another run owns it, go to the next lever. Else make `Process: <lever>` (`ticket` skill, labels `process`, `tooling`,
`P1`, `lane:deep` when it needs judgement): the evidence, the before-numbers, the cause or the question for new data.

**Size:**
- Small (a skill text, a setting, a workflow step, a tool option, a new check): do it in this review, one PR per
  change, title `Process: <what>`, label `process`. Up to 3 PRs per review; the rest as tickets.
- Large (a new tool, a redesign of a part, a change of many files): an epic or a `P1` ticket in this review. Do its
  first step now when it fits, and let the measurement wait: `Start after: 50 PRs after #<PR of the first step>`.
- Owner steps (environment settings, secrets, scheduled tasks, GitHub settings): make all parts in the repository first
  (for example `scripts/cloud-setup.sh`, `scripts/allowed-domains.txt`), then one `needs-human` ticket with numbered
  steps and the exact text to paste. Look for an open one first.

**Pause when the owner must act first** (owner, 2026-10-29). When the runs waste quota or make work that must be done
again until the owner did the steps (a broken setup, a missing secret that the runs need, a redesign that conflicts
with all work in progress), add the label `paused` to the status issue and comment there: the ticket, the steps, and
"remove the label `paused` when you are done". Do not pause for a step that the runs can wait for.

## 5. Clean up

- `docs/LEARNINGS.md` at 3000 bytes or less (lines for some tickets go to `docs/PITFALLS.md`, #4454) (only this skill merges and removes lines there; ticket runs only add),
  `CLAUDE.md` below 150 lines. Remove lines that are no longer true. `merge=union` (`.gitattributes`) keeps a removed line
  when main added lines next to it: after each merge of main, check that the removed lines stay out.
- Turn a learning line into a check when you can (a rule of `.claude/hooks/guard-shell.sh`, a fast test, a clear
  assert message, a setting of the start hook), then remove the line.
- Read the skills for instructions that contradict each other. Correct them.

## 6. Report and the next review

Add each change to "Process changes" on the status issue: `- <date>: <change> (PR #n) — before: <numbers>`, and each
miss as in step 0. Comment 3–6 lines: the misses and what they taught, the result of step 1, one line with the number of
each lever (`1 base 41 % · 2 claim 12 % · ...`), what you changed, and what you expect. The owner can reject a change
in a comment: then revert it and add the reason to `docs/LEARNINGS.md`.

Then set the next review: `python3 framework/tools/claim.py 0 --reviewed change` after a change, or `--reviewed none` when no
lever was above its threshold. The gap of merged PRs moves (`claim.next_gap`, the values in `[review]` of
`agent.toml`, owner 2026-10-29): `change` halves a gap up to `gap` (down to the count of ready tickets, between `min_gap` and `max_min_gap`) and resets a larger one to `gap`;
`none` doubles a gap from `gap` up (up to `max_gap`) and resets a smaller one to `gap`. Owner work since the last review makes it `owner_gap`. So reviews that find
work come more often, and reviews that find nothing come less often. Say `change` when the review opened a PR or a
ticket for a miss or for a lever above its threshold; else `none`. A small gap costs one deep run per gap: the
thresholds of step 3 are the brake.

## Guardrails

- Never weaken or remove tests, CI checks, lint rules or verify levels to save quota.
- Never remove the rule that only the owner (`owner` in `agent.toml`) gives instructions, or the `deny` list in
  `.claude/settings.json`, or the hook `.claude/hooks/guard-main.sh` (it stops the command before it runs; the
  ruleset `Protect main` of the owner only refuses the push). Never allow destructive commands (force-push, delete, `gh api`).
- Never change the priorities that the owner set. A decision with two or more good options goes to the owner as a
  decision ticket (`ticket` skill); a change with one clear best option needs no question.
- A pause is only for owner steps, never to save quota; its comment says how to end it.
- Explain the reason for each change. If an earlier change did not help (the numbers did not improve), revert it.
