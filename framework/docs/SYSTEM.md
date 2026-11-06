# The agent system

This document describes the whole system that lets Claude Code agents work on travel-aggregator without a person: the parts,
the loop of a run, the locks, the quota pacing, the steering and the setup steps of the owner. Use it to understand
the system, or to set it up for another project. For the rules of the project, read `CLAUDE.md`. For the owner's
controls, read `framework/docs/STEERING.md`. This document links to them and does not copy them.

## The parts

| Part | What it does |
|---|---|
| Scheduled tasks (owner's account) | "travel-aggregator autopilot", "travel-aggregator autopilot haiku" and "travel-aggregator autopilot deep" have no schedule: the pacer starts them (since 2026-10-28 the workflow `pacer.yml` through their API triggers, #3194). |
| Pacer | The workflow `pacer.yml` (`framework/tools/pacer.py`, #3193): every 10 minutes it starts the runs that the quota target misses, through the API triggers of the scheduled tasks. |
| Runs | Cloud sessions of the autopilot task. Each run follows the skill `autopilot` with the argument `max`: tickets, one PR each. Many runs work at the same time. |
| Skills (`.claude/skills/`) | The procedures: `autopilot` (the work cycle), `verify` (checks before a push), `ticket` (write and split tickets), `design` (design tickets), `improve` (process review), `roadmap` (epics from `steering/project/ROADMAP.md`), `human` (guides the owner through the `needs-human` tickets on the owner's computer), `demo` (a demo game on the owner's computer: a ticket for each feedback in the chat, the cause of each crash, `game/demo_watch.py`). |
| Denied tools (`.claude/settings.json`) | The `deny` list removes the session tools that no skill uses (`Artifact`, `Workflow`, the `Suggest*` and `Search*` tools, and since 2026-10-29 the plan, worktree, task list, wake-up, notification and review-findings tools and the
session task tools `mcp__ccd_session` ...) from each session of the repository: their descriptions were about 19,000 of the 66,000 base tokens of each call (2026-10-28). A rule in a file that the SessionStart hook writes works only from the next session, so the list is in the repository. Since #5463 it also denies the agent types `claude-code-guide` and `statusline-setup`, and `skillOverrides` removes the unused skills from the skill list (`off`: `anthropic-skills:*`, `plugin-authoring`, `session-start-hook`; `user-invocable-only`: the local skills `demo`, `human`, `new-project`): 3,400 fewer tokens in each call. |
| Rules (`CLAUDE.md`, `docs/LEARNINGS.md`) | Each session loads them. `CLAUDE.md` has the commands, the code map and the rules. `docs/LEARNINGS.md` has the lessons for all runs (at most 3000 bytes); `docs/PITFALLS.md` (not loaded) has the lessons for some tickets, by case (#4454). |
| Tools (`tools/`) | `claim.py` (locks), `usage.py` (quota and the number of runs), `dashboard.py` (the status issue and the pick order), `health.py` (numbers for the review), `tokens.py` (the token sinks of a run), `operator_check.py` (the checks of the `operator` skill), `owner_tasks.py` (the tickets of the `human` skill). |
| GitHub | The issues are the tickets. Issue #1 (label `agent-status`) is the status issue: the dashboard and the state comment in its body. The run reports are files on the branch `metrics` (`runs/`, 2026-10-29; before: comments on the status issue). The labels are in `.github/labels.txt`. |
| Workflows (`.github/workflows/`) | CI, Automerge, Unconflict, Claims, Close, Dashboard, Coverage, Labels, Bundles (see below). |
| Cloud environment | The setup script `scripts/cloud-setup.sh` (Java, packages, server jars), the network access, the SessionStart hook. |
| Hooks (`.claude/hooks/`) | `session-start.sh` runs `scripts/session-setup.sh` if it exists and the `install` command of `agent.toml`, registers the merge driver `merge=jsonl` (#2004), sets an empty `TMPDIR` to `/tmp` and compares `SETUP_VERSION`. `guard-main.sh` blocks a force push, a history rewrite or a delete of `main`. `guard-shell.sh` blocks the shell pitfalls of `docs/LEARNINGS.md`: `cat > FILE <<` over a tracked file, a redirect into `$VAR/` with an empty variable, a variable set in a list that `&` puts in the background, an unquoted heredoc tag with `` ` `` in the body, `pkill -f` with no bracket in the pattern, and `git stash` or `git checkout --ours` in a merge. |

### Workflows

| Workflow | When | What |
|---|---|---|
| `ci.yml` (CI) | Each PR, each push to `main`, each night | Quick checks (lint, fast tests) on each PR; a Markdown-only PR runs only the doc tests (`tools/ci_select.py`, #2089); a change of `game/plugin` also compiles the Paper plugin (#2437). The full suite each night on `main`. A red `main` opens a `P0` ticket; a green `main` after a red one starts Unconflict (#3685). |
| `automerge.yml` (Automerge) | After CI, every 5 minutes, by hand | Merges an agent PR with green CI, and a PR on any branch with the label `automerge` (#3383). Skips `hold` (it wins over `automerge`) and tickets with `needs-human` or `blocked`. When GitHub calls the PR `dirty`, it merges `main` into it with our merge drivers and `framework/tools/unconflict.py` (`land()`), checks `ruff`, pushes and merges at once, with no new CI run (#3199); only a real conflict gets `conflict`, not a merge that failed because another merge landed in the same second (#3063). Then starts CI on `main`, Coverage and Claims (not Dashboard: the pacer starts it each cycle, 2026-10-29). |
| `unconflict.yml` (Unconflict) | Every 20 minutes, after each merge | Merges `main` into a conflicted agent PR when git solves the conflict alone (`merge=union` files) or both sides only add lines (`framework/tools/unconflict.py`, #1864; not the same `def` on both sides, and the merge passes `ruff check`, #2631), and starts CI. When `main` is green again, it also merges `main` into a PR whose last CI run failed while `main` was red, and starts CI (#3685): no run must take it over. `framework/tools/unconflict_pick.py` finds the PRs with git (`merge-tree` with no merge attributes, as GitHub merges) and 3 to 4 API calls, not 3 + 2 calls per open PR (2026-10-29). |
| `claims.yml` (Claims) | A ticket closes, after each merge, each day | Deletes the claim refs of closed tickets and old locks (`claim.py 0 --prune`: git and one API read; the REST script used about 60 calls a run, 2026-10-29). The runs cannot delete refs (403). |
| `dashboard.yml` (Dashboard) | Each pacer cycle (10 minutes), the cron as a fallback (not on events and not after each merge: the API rate limit, #2168, 2026-10-29) | Writes the dashboard in the body of the status issue (`framework/tools/dashboard.py`). |
| `pacer.yml` (Pacer) | One run loops for 5.5 hours (a cycle every 10 minutes), then starts the next run; the cron (`*/30`) only restarts a dead loop: GitHub fires the cron schedules of this repository a few times per day | Only while `pacer = "workflow"` in `[pacing]` of `steering/system/system.toml`: starts the runs that the quota target misses through the API trigger of each task (`framework/tools/pacer.py`, #3193). Each cycle also starts `dashboard-site.yml` and `dashboard.yml`, and writes the new status comments and its own record (quota, burns, target, claims, ready tickets, planned and started runs, the REST budget of the workflow token: `pacer.py --log`) to the branch `metrics` (`status/` and `pacer/`, `metrics_log.py --push`, 2026-10-29). Secrets: `CLAUDE_CODE_OAUTH_TOKEN` (the quota read), `PACER_URL_<TASK>` and `PACER_TOKEN_<TASK>` for `MAIN`, `HAIKU`, `DEEP`. A task takes at most 30 API starts per hour, an account 100. |
| `dashboard-site.yml` (Dashboard site) | Each pacer cycle (`pacer.yml` starts it), the cron as a fallback, by hand | Builds the owner's dashboard (`tools/dashboard_site.py`: the page of `tools/dashboard_artifact/`, the data of `tools/dashboard_data.py`) and publishes it to GitHub Pages (owner decision A, 2026-10-28). It replaces the hourly Claude task "travel-aggregator dashboard refresh" and the artifact (the skill `dashboard-refresh` was removed with the `Artifact` tool, 2026-10-28). `actions/cache` keeps the issues and PRs of the last build: a build reads only the changed ones (`dashboard_data.cached`), all of them once a day (2026-10-29: about 60 API pages a build before). |
| `coverage.yml` (Coverage) | Each push to `main` | Writes `docs/coverage.md`, `MAX` of `tests/test_coverage.py` and a column of `docs/DESIGN.md`. PRs do not change these files, so they do not conflict there. |
| `metrics.yml` (Metrics) | The cron (`*/15`, a few times a day), by hand with `days` | Writes the status issue comments to the orphan branch `metrics` (`framework/tools/metrics_log.py`, one file per day). `framework/tools/health.py` reads them, the run reports of `runs/` (each run adds its own file, `metrics_log.post`) and only the newest comments from the API (#1983). The tip keeps the last 14 days (`metrics_log.prune`: each reader fetches the whole tip); the git history of the branch keeps all days. A store outside GitHub (Cloudflare D1, free up to 5 million rows read a day) was not better: it adds an account, a token in the runs and a way to fail for the pacer (2026-10-29). The pacer loop writes the branch in each cycle too (2026-10-29): this workflow is the fallback and the backfill. |
| `labels.yml` (Labels) | A change of `.github/labels.txt` | Creates the labels. |
| `after-release.yml` (After release) | A push of a tag `v*`, `release.yml`, by hand | Moves the label `after-release` of each open issue to `rank`: the owner holds a ticket with it until the next release, and `framework/tools/dashboard.py` skips it until then (#4175). A deep run ranks the `rank` tickets (P1 to P3) and gives the next release epic its scope (`roadmap` skill, "Release cycle"). |
| `release.yml` (Release) | A closed issue with `release`, `close.yml`, each hour, by hand | Makes the milestone of each open release epic; tags `vX.Y.Z` of a closed release epic when its milestone has no open issue (the newest commit of main with a green CI run after the close), makes the GitHub release with the closed issues of the milestone as notes, closes the milestone, starts `installers.yml`, `worlds.yml` and `after-release.yml` on the tag, and opens the next release epic (with `rank`) and milestone (owner, 2026-11-01). |

### Tools of the system

| Task | Command |
|---|---|
| System numbers | `python3 framework/tools/health.py [--hours N]` (CI, setup, takeovers, conflicts, files in git; `improve` skill) |
| Start of the runs | `python3 framework/tools/operator_check.py` (quota, ready tickets, CI, old PRs, labels, owner comments; the scheduled tasks and the pacer: `framework/docs/OPERATOR.md`, #981) |
| Owner feedback | `python3 framework/tools/feedback.py` (the owner comments of the last 6 hours without a lock `claim/comment-ID`, autopilot step 3, #971) |
| Tokens of a run | `python3 framework/tools/tokens.py [--top N]` (the tokens of this session and the largest sinks: files, commands; the `Tokens:` line of the run report; `--verify`: the minutes of each check command) |
| Quota and pacing | `python3 framework/tools/usage.py` (5-hour and 7-day usage, resets; `--target`: the number of runs (90 % of the 5-hour window 2 hours before the reset, then 98 %); `--sample`: the `Usage:` line of the run report; `--fire`: the runs that the pacer starts now; `framework/tools/pacer.py` starts them, `pacer.yml`, #3193) |
| Dashboard of #1 | `python3 framework/tools/dashboard.py --dry-run` (`--next`: ticket candidates in pick order) |
| Release bar | `python3 tools/release.py` (percent of each goal for the levels C = 100 %, A and B: `steering/project/RELEASE.md`, #878) |

## The loop of a run

1. The pacer (`pacer.yml`) starts a run. The cloud clones the repository on the session
   branch `claude/<name>`.
2. The run reads `CLAUDE.md` and follows the skill `autopilot`. It stops at once when the status issue has `paused`.
   It runs `framework/tools/usage.py --fire`: when the running runs reach the target, it only finishes stalled PRs.
3. It finishes open work first: stalled PRs, red CI, merge conflicts, a red `main`.
4. It reads the new comments of the owner and does what they ask. It sorts new issues (priority, kind, size).
5. It picks a ticket in the order of `framework/tools/dashboard.py --next` (`P0` to `P3`, the least overlap with other work,
   the lowest number) and claims it (`framework/tools/claim.py N`). When the queue is short, it makes new tickets from the
   epics and the roadmap.
6. It does the ticket on its session branch (a later ticket of the run: on `<session branch>-<k>`, `more.md`): a failing test first for a bug, the change, the checks of the skill
   `verify`, and the process improvements (autopilot step 9) in the same PR.
7. It runs `framework/tools/claim.py N --guard`, pushes and opens a PR with `Closes #N` (`ship_pr.py`). It waits for the quick CI
   and fixes a red one with its warm context (#4784), then for the merge: a conflict there (exit 6) gets a merge of main (#5584).
8. CI runs the quick checks. Automerge merges the PR when they are green. The merge closes the ticket. Claims
   deletes the claim ref. Dashboard updates the status issue.
9. The run adds its report to the branch `metrics` (`report.py --post`: a `Usage:` line and a `Metrics:` line per ticket) and takes
   the next ticket. It stops when no ticket is ready, a usage limit stops it, or its context is 120k tokens or more.

## The locks

All locks are git refs. A push without force to a new ref fails when the ref exists, so only one run wins.
The details are in the text at the top of `framework/tools/claim.py`.

| Lock | Ref | Who |
|---|---|---|
| Ticket | `claim/N` (`claim/N-2` ... after a release) | `claim.py N`. The owner beats each 20 minutes (`--beat`). After 30 minutes without a beat the claim is stale: another run can take it over (`--takeover`). `--guard` before each push. |
| Owner comment | `claim/comment-ID` | `claim.py ID --comment`: one run acts on one owner comment. |
| Refill | `claim/refill-E-S` | `claim.py E --refill`: one run makes the sub-issues of epic E (E = 0: the whole queue, one per hour). |
| Process review | `claim/review-<gap>pr-<last>-<k>` | `claim.py 0 --review`: one run runs the `improve` skill after a gap of merged PRs (`[review]` of `steering/system/system.toml`, no hours: owner, 2026-10-29). A review with a change halves a gap up to `gap` (down to `min_gap`) and resets a larger one to `gap`; a review with no change doubles a gap from `gap` up (up to `max_gap`) and resets a smaller one to `gap` (`claim.next_gap`). Owner work since the last review (a merge with no commit of a run: each run commit has the trailer `Agent-Run:` of the `commit-msg` hook that `claim.py` installs at each claim, adopt or lock) makes the gap `owner_gap`. |
| Roadmap review | `claim/roadmap-100pr-<last>-<k>` | `claim.py 0 --roadmap`: one run reviews `steering/project/ROADMAP.md` after 100 merged PRs. |

Other rules against conflicts: one ticket per PR, new tests in a new file, new table entries on their own line in
alphabetical order, `merge=union` in `.gitattributes` for files where runs only add lines.

Clock or count (#2039). A rule that waits for work counts merged PRs, because the speed of the project changes and a
fixed time measures a different amount of work: the process review (`[review]` in `agent.toml`: between `min_gap` and `max_gap`),
the roadmap review (100), `Start after: N PRs after #M` and the window of `framework/tools/health.py` (50). A rule that finds a
stopped run or follows a real clock stays in minutes, because a stopped run merges nothing: the claim beat (20), a
stale claim (30, or 10 with the label `conflict`), a "Started by" comment (30), the Automerge sweep (10), an old PR in
`framework/tools/operator_check.py` (30), the pacer (10), `unconflict.yml` (20) and the refill lock (one per hour; a due review does not wait for it). The quota
windows (5 hours, 7 days) follow the subscription, the owner comments of `framework/tools/feedback.py` (6 hours before the
last run report, at most 23, #3060) get an answer in time, and a run longer than 90 minutes is about the context and
the container of one run. A wait to measure a change never names a date (owner, 2026-10-29): `framework/tools/health.py` lists the
open tickets with a date in their `Start after:` line ("Time waits", lever 8 of the `improve` skill).

## The quota pacing

All runs share the quota of one Claude Max account. `framework/tools/usage.py` reads the 5-hour and the 7-day usage with one
tiny CLI call. It computes the target number of runs: 90 % of the 5-hour window used 2 hours before the reset, then
98 % at the reset, and the week not faster than it passes: when the 7-day usage is ahead of the share of the week
that has passed, the count is at most the runs that the rest of the 7-day budget (1 − used) carries to the 7-day reset
at the measured 7-day burn per run-hour (`health.weekly_burn`, default `BURN7`). This count can be 0: the runs then
wait until the budget per hour is large enough again (#1695). Below `week_free` of `agent.toml` (98 %, owner, 2026-11-04) of the 7-day
usage there is no weekly guard: the runs fill each 5-hour window (owner, 2026-10-27). `week_guard` of `agent.toml` turns the weekly guard on
(`true`) or off (`false`: only the 5-hour window counts; owner, 2026-10-28). The CLI line shows the projection
(`week ahead +38 pt · runs out Wed 11:22`, at the mean rate of the week so far). `--fire` gives the number of runs to start now: the
target less the runs with a claim beat in the last 25 minutes, and less the runs that the pacer started in the last 12 minutes and
that have no claim yet (`usage.pending`, from the `--log` of `pacer.py`; each takes a ready ticket of its lane, 2026-10-29). A run cannot start other runs (no `fire_trigger`, #566),
so the pacer starts them (at most `max_fire` of `agent.toml` per cycle, and at most the ready tickets plus `refill_runs`: those runs refill the queue). The pacer is the workflow `pacer.yml` (#3193, #3194): each cycle fetches `main` and runs
`framework/tools/pacer.py`, so a change of the pacing rules works at the next cycle. The pacer also does steps 1 to 5 of the autopilot for each run that it starts (owner, 2026-10-29): it takes the next candidate of the lane of the run, claims it as `pacer-r<hex>`, adds `in-progress` and "Started by" with the session link, and sends a brief (the ticket, its comments, the code places of `ticket_context.py`, the `Usage:` line) in the `text` of the call. The run adopts the claim with `claim.py N --adopt NAME` and starts at step 6 (`scheduled` skill, step 0). A stuck ticket (its run stopped, `claim.py 0 --stuck`) comes first: the pacer takes it over for one run (`claim.py N --takeover` with the run name, the comment "Taken over by") and adds a `takeover:` line with the branch of its PR, so that the runs do not race for it (#4356). A refill run (no candidate left), and all runs while the flow brake is on or the last CI run on main is red, get no brief. A failed call releases its claim. It starts each run with one call of the
API trigger of its task; a task takes at most 30 API starts per hour (an account 100), and when a lane task answers
HTTP 429 its runs go to the main task. `framework/tools/health.py` measures the quota use of one run from the
`Usage:` lines of the run reports, and `usage.py` uses that value. After a plan upgrade the same work is a smaller share of the larger quota: when the burn of
the last 2 hours is less than half of the 24-hour burn, only the last 2 hours count (`health.ratio`, 5-hour and 7-day
burn, #1706). The most runs at one time is `max_runs` in `[pacing]` of `steering/system/system.toml` (default 16): raise it when the 5-hour window does not reach its limit (40 since 2026-10-27: at a burn of 0.009 per run-hour, 16 runs used only about 70 %).
Several Claude accounts at the same time (several collaborators): the plan `docs/COLLABORATORS.md` (#4185, epic #4232).
The flow brake (owner, 2026-10-27): when CI, merge conflicts or anything else stops the merges, the quota is not the
bottleneck, and more runs only make more open PRs and more conflicts. `--fire` counts the open agent PRs older than
`pr_minutes` without `hold` and the queued CI runs. At `max_waiting_prs` (default 10) it starts at most 1 run per
cycle, at `max_ci_queue` (default 5) none. A run asks `usage.py --flow` in autopilot step 2: with the brake on it only
repairs PRs and takes no new ticket.
A PR with the label `conflict` and no new commit for 10 minutes is stalled: a run takes it over (`claim.py`, #1773).
Automerge adds the label when its own merge of main with the drivers finds a real conflict (#3199), Unconflict when its merge of main finds a real conflict.
The target counts Opus runs. A run of a cheap lane counts its weight (#1727): a Haiku run sets `git config travel-aggregator.lane haiku`,
its claims end with ` lane haiku`, the `Usage:` lines count its runs (`· haiku N`), and `health.lane_weights` measures
the weight from them (least squares, at least 10 intervals with Haiku runs; before that `weights` of `agent.toml`,
0.25). `usage.py --fire` gives the ready `lane:haiku` tickets Haiku runs first, then Opus runs take the rest. A lane in `reserved` of `[pacing]` keeps its tickets for its own runs (Opus runs never take them, #1994). `framework/tools/tokens.py` reads the transcript of the
session and writes the `Tokens:` line of each run report: the tokens of the run and its largest sinks. `health.py`
adds them. The `Run:` line (`tokens.py --run-line`, 2026-10-29) names the session, the branch, the start, the wall minutes, the
model, the effort, the thinking tokens, the eq of each phase and of each ticket, and the lane: it joins the reports of
one run and the starts of the pacer, so that a run that stops with no report shows. The `improve` skill finds the largest loss of quota from this data, or the data that is missing, and
makes one `Process: <bottleneck>` ticket for it on the board.

## The steering

The owner steers only through GitHub (`framework/docs/STEERING.md`): new issues with the ticket form, priority labels,
comments, `hold` on a PR, `paused` on the status issue. The agents take instructions only from the owner's login.
An agent asks the owner only on the issue that needs the answer: label `needs-human` and a comment that mentions
the owner. A decision with several good options becomes a decision ticket. The `improve` skill changes the process
itself and lists each change on the status issue.

## Setup steps of the owner

Only the owner can do these steps. An agent that needs a change makes a `needs-human` ticket with numbered steps.
For a new project, follow `framework/docs/NEW_PROJECT.md` (the template, then these steps). `python3 framework/tools/bootstrap.py DIR --repo OWNER/NAME` copies the generic files, writes `agent.toml` and
the starts of the specific files, and prints these steps for the new repository (`--github`: also the labels and the
status issue). Merge the first PR of the bootstrap by hand: Automerge cannot merge it, because the workflows are not
on `main` yet.

1. **GitHub.** Install the Claude GitHub app on the repository. Make the repository public (free Actions minutes).
   Add the ruleset `Protect main` (Settings → Rules): no force push, no delete of `main`. Give the workflows write
   access (Settings → Actions → General → Workflow permissions), so that Automerge can merge. To let Automerge merge
   a PR of your own branch, add the label `automerge` to it (#3383).
2. **Cloud environment.** At claude.ai/code, make one environment for all runs. Network access: keep "Allow package
   managers" on and paste the whole file `scripts/allowed-domains.txt` into "Allowed domains". Paste it again when an
   agent asks (it adds a host to the file and opens a `needs-human` ticket, `docs/ENVIRONMENT.md`, "Network"). Setup script: paste
   `scripts/cloud-setup.sh`. Paste it again when an agent asks (the SessionStart hook compares `SETUP_VERSION`).
   One environment can serve two projects (#1964): paste one setup script that installs the needs of both (each
   script lists them in `SETUP_NEEDS`). The hook of the project with no version file in `/etc` checks only its
   `SETUP_NEEDS`, and asks for a new script only when one is missing.
3. **Status issue.** Open issue #1 with the label `agent-status` (the first run makes it when it is missing).
4. **Scheduled task "travel-aggregator autopilot".** No schedule: the pacer starts it (2026-10-28; before: hourly at :06). Repository `Larspolo/travel-aggregator`, the environment of step 2.
   Its prompt is only `/scheduled max` (owner, 2026-10-29): the skill `.claude/skills/scheduled/SKILL.md` holds the
   rules (`CLAUDE.md` is already in the context, follow the `autopilot` skill, no `fire_trigger` (#566), the quota target of
   `python3 framework/tools/usage.py --fire`, a branch and a PR for each ticket, instructions only from the owner, stop on
   `paused` or a usage limit), so a PR changes them and no task needs an edit.
5. **Pacer (`pacer.yml`, #3193, #3194).** On your computer run `claude setup-token`, and add the token as the
   repository secret `CLAUDE_CODE_OAUTH_TOKEN` (the quota read). For each autopilot task (steps 4, 7, 8): in the
   app, edit the task, add an API trigger, generate a token, and add the secrets `PACER_URL_<TASK>` (the fire URL)
   and `PACER_TOKEN_<TASK>` (the token) with `<TASK>` = `MAIN`, `HAIKU`, `DEEP`. Keep `pacer = "workflow"` in
   `[pacing]` of `steering/system/system.toml`. Then start Actions → Pacer → Run workflow once: the run loops and starts the next
   run itself. A new token makes the old one invalid: change the secret too. Another Claude account NAME
   (`docs/COLLABORATORS.md`): add `CLAUDE_CODE_OAUTH_TOKEN_<NAME>`, `PACER_URL_<NAME>_<TASK>` and
   `PACER_TOKEN_<NAME>_<TASK>`; the pacer uses it from its next cycle (#4237).
6. (Removed in #3427: the pacer session, skill `pacer`.)
7. **Scheduled task "travel-aggregator autopilot haiku" (optional, #1715).** No schedule: the pacer fires it. Model
   `claude-haiku-5-5`, the prompt `/scheduled max lane haiku`. These runs take only the tickets with
   `lane:haiku` (`ticket` skill, "Model lanes"); Opus runs take them only when nothing else is ready.
   `framework/tools/health.py` prints one line per lane (runs, PRs, minutes, tokens). `framework/docs/OPERATOR.md`, section 3, makes the task.
8. **Scheduled task "travel-aggregator autopilot deep" (owner, 2026-10-28).** No schedule: the pacer fires it. Model
   `claude-opus-5-5` at effort high (the owner's setting; the main task runs at low effort), the prompt
   `/scheduled max lane deep`. These runs take the tickets with `lane:deep` and do the epic check, the queue refill, the roadmap
   review and the process review (`autopilot/queue.md`, "Deep lane").
9. **Move to another Claude account (owner, 2026-10-28).** Follow `framework/docs/OPERATOR.md`, section 4 (or start a session
   in the new account with the repository and let it follow the section). The steps pause the runs (label `paused`),
   make the tasks of steps 4, 7 and 8, write the new IDs to `agent.toml`, and check all parts at the end. The steps
   that only you can do:
   - In the old account: disable the scheduled tasks of travel-aggregator (their API tokens stop with them).
   - The secrets of step 5: a new `claude setup-token` of the new account and new API triggers of the new tasks.
   - In the new account: connect GitHub (the Claude GitHub app stays on the repository); make the cloud environment
     of step 2; set the repository, the model and the effort of each new task (autopilot: Opus 5.5, effort low;
     haiku: Haiku 5.5; deep: Opus 5.5, effort high). The tool cannot set these three values.
   The GitHub side (tickets, claims, labels, the status issue) does not change.

To check or repair steps 4–8, follow `framework/docs/OPERATOR.md` (#981). It checks the scheduled
tasks, the runs of `pacer.yml`, the quota, CI, the PRs and the labels, and repairs them after you agree. A long-lived owner session is not necessary.

## Generic and specific files

"Generic" files work for another project with no change, or with a change of `agent.toml` only (#905: the repository,
the owner login, the default branch, the status issue, the commands, the doc paths). "Specific" files hold rules of travel-aggregator.
`framework/files.txt` lists the generic files, one path per line (#4192): add a new generic file there. The table below
lists only the specific files: a new project writes them itself.
The tests of the generic tools are generic too, so that a new project has them (#1900). Not in the list: the tests
of `framework/tools/bootstrap.py` (they copy this repository) and the tests that need a specific tool (`tools/dashboard_data.py`,
`tools/release.py`). `tests/test_generic_words.py` fails when a generic file names the domain of the project.
`tests/test_generic_tools.py` fails when a generic file names a `tools/X.py` that is not in `framework/files.txt` (#1963).
The framework stays in this repository: `framework/tools/bootstrap.py` copies it into a new project, and an improvement
in one project reaches another project only by a copy (owner decision A, #4197: a synced repository waits until a
second project starts).

| File | Kind (`steering`: the owner steers with it) | What is specific to travel-aggregator |
|---|---|---|
| `agent.toml` | specific | All the project values that the generic files use. `framework/tools/agent_config.py` reads it. |
| `CLAUDE.md` | specific | The commands, the code map, the rules of the domain. It imports `framework/CLAUDE.md` with `@framework/CLAUDE.md`. |
| `docs/ENVIRONMENT.md` | specific | The hosts of the tests and the tools of the setup script (Mojang, Java, Minecraft, #1900). |
| `docs/LEARNINGS.md` | specific | The lessons of this project. The first section (environment and GitHub) is mostly generic. |
| `steering/README.md` | steering | The list of the steering files: who writes each, and its kind. |
| `steering/project/ROADMAP.md` | steering | The three goals and their features. |
| `steering/project/RELEASE.md` | steering | The release bar: the levels of each goal, the release focus and the release cycle. |
| `steering/project/PRINCIPLES.md` | steering | The direction of the project: the owner's preferences for travel-aggregator, made general from the decisions. |
| `steering/project/DECISIONS.md` | steering | The log of the owner's project decisions (one line each), the evidence of the project principles. |
| `steering/system/PRINCIPLES.md` | steering | The owner's preferences for the agent system, made general from the decisions. |
| `steering/system/DECISIONS.md` | steering | The log of the owner's system decisions (one line each), the evidence of the system principles. |
| `.claude/skills/verify/SKILL.md` | specific | The check levels (preview image, world reader, Minecraft server, screenshots). |
| `.claude/skills/design/SKILL.md` | specific | The design of buildings, units and animals. |
| `.claude/skills/roadmap/SKILL.md` | specific | The three goals of travel-aggregator. |
| `.claude/skills/human/SKILL.md` | specific | The preparation of a play test (worlds, `game/run.py`, Minecraft 26.3). |
| `.claude/skills/demo/SKILL.md` | specific | The demo game (`--random-map arabia`, `game/run.py`, `game/demo_watch.py`, the Minecraft client folders of macOS). |
| `scripts/cloud-setup.sh` | specific | Java, the Minecraft server jars, the Vulkan and X tools of the client. |
| `scripts/session-setup.sh` | specific | The project steps of the SessionStart hook: JDK 25, the pip pillow and setuptools. |
| `scripts/allowed-domains.txt` | specific | The "Allowed domains" of the cloud environment: the hosts of the tests and the research tools. |
| `tools/dashboard_site.py` | specific | The owner's dashboard page and its runtime (GitHub Pages). |
| `tests/test_dashboard_site.py` | specific | None (a test of `tools/dashboard_site.py`). |
| `tests/test_generic_tools.py` | specific | The tools of travel-aggregator that generic files may name (`OPTIONAL`, #1963). |
| `tests/test_generic_words.py` | specific | The words of travel-aggregator that the generic files must not contain (#1900). |
| `.github/workflows/ci.yml` | specific | The Python, Java and Minecraft steps, the test markers. The red-`main` ticket is generic. |
| `.github/workflows/dashboard-site.yml` | specific | The owner's dashboard page on GitHub Pages (`tools/dashboard_site.py`, `tools/dashboard_artifact/`). |
| `.github/workflows/coverage.yml` | specific | The coverage of the AoE2 types. |
| `.github/workflows/bundles.yml` | specific | The app bundles of the converter (PyInstaller, `packaging/`, #1541) and their installers (#1542). |
| `.github/workflows/installers.yml` | specific | On a tag `v*`: the installers of `bundles.yml` in the release of the tag (#1542). |
| `.github/workflows/release.yml` | specific | Tags the closed release epic `vX.Y.Z`, starts `installers.yml`, `worlds.yml` and `after-release.yml` on the tag, opens the next release epic (owner, 2026-11-01). |
| `.github/workflows/worlds.yml` | specific | The worlds of `examples/` and `samples/` as zips in a release (#207). |
| `.gitattributes` | specific | The list of `merge=union` files, and `merge=jsonl` for `game/data/*.jsonl` and `tests/data/civ_bonuses.jsonl` (`framework/tools/merge_jsonl.py`, #2004, #2100). |
