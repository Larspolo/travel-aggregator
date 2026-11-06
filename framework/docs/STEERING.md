# Steering the agent

The agent (Claude Code) works on this project automatically. You steer it asynchronously through GitHub
Issues. You can do all of this in the GitHub app on your phone.
`framework/docs/SYSTEM.md` describes the whole system: its parts, the locks, the pacing and your setup steps.

## How the agent works

Each run does one work cycle (the `autopilot` skill):

1. It reads your new comments on issues and PRs, and does what they ask.
2. It sorts new issues: priority, kind, size and lane labels. It splits large tickets.
3. It does the top ticket: code, tests, a PR. It merges the PR when CI passes.
4. It reports on the **Agent status** issue (label `agent-status`) with a short comment. GitHub sends you a
   notification. The dashboard in the issue body is generated from GitHub (`framework/tools/dashboard.py`, workflow
   `Dashboard`): waiting for you, working on, next up, recently done. It updates on each label change and every
   hour. Runs only add the process changes.
5. It improves its own process: it writes learnings, corrects its instructions and makes tooling tickets.
   One run per review slot (a gap of merged PRs in `[review]` of `agent.toml`: it halves from 80 to 10 while reviews
   make changes, doubles from 80 to 640 while they make none, and goes back to 80 when the result turns; shorter after you changed the system yourself): the `improve` skill learns from your own changes, walks all its levers and makes each change that pays,
   also large ones. The status issue lists each process change.

The agent takes instructions only from comments and issues by `Larspolo`.

## What you can do

| You want to | Do this |
|---|---|
| Add a ticket | New issue → **Ticket** form. One or two sentences are enough. |
| Do a ticket next | Give it label `P0`, or comment "do this next". |
| Change a priority | Change the label (`P0` do next, `P1` high, `P2` normal, `P3` later). |
| Give feedback | Comment on the ticket, on the PR, or on the status issue. |
| Reject merged work | Comment on the merged PR. The agent makes a follow-up ticket. |
| Answer a question | Answer in the `needs-human` ticket. The agent removes the label. |
| Answer the tickets that wait for you | Run `/human` in Claude Code on your computer, in a clone of the repository. It lists the `needs-human` tickets, prepares the world, the server or the options, guides you step by step and writes your answer on the ticket. Keep the session open: `/human` can wait for the next `needs-human` ticket and shows it when it opens (#1025). |
| Do a task that the agent cannot do | The agent asks on the issue: label `needs-human` and a comment that mentions you. Do it, then comment. |
| Stop the agent | Add label `paused` to the status issue. Remove it to continue. A process review can add it too, when the runs must wait for your steps: its comment names the ticket and the steps. |
| Cancel a ticket | Close it as "not planned". |
| Mute a ticket until later | Add the label `muted`. No agent works on it (also not on a muted epic), and "Waiting for you" hides it. Remove the label to bring it back. |
| Do a ticket only after the next release | Add the label `after-release`. No agent works on it before the next release. A push of a tag `v*` removes the label from all issues (workflow `after-release.yml`); remove it by hand to bring one ticket back earlier. |
| Set what the next release holds | Add a ticket to the GitHub milestone "vX.Y.Z" of the open release epic (label `release`) or remove it. For the roadmap features: the line "Release focus: X" or the levels of `steering/project/RELEASE.md`. Until the next release the agents work only inside the focus, and give each ticket outside it the label `after-release`. |
| Make a release | Close the release epic, or let the agents close it when its criteria are met. The Release workflow tags `vX.Y.Z` when the milestone has no open issue and CI of main is green, makes the GitHub release, closes the milestone, brings the held tickets back with `rank` and opens the next release epic and milestone. |
| Reject a process change | Comment on the status issue. The agent reverts it and notes why. |
| Ask for a process review | Comment "process review" on the status issue. A PR of your own session that the runs did not make (no commit with `Agent-Run:`) also makes the next review come soon: the review learns the lever from it. |
| Check or repair the start of the runs | Follow `framework/docs/OPERATOR.md` (check, repair, a new project, a move to another account), or start a session at claude.ai/code and write "Follow framework/docs/OPERATOR.md, section 1". A long-lived owner session is not necessary. |

Order of work: `P0` → `P1` → `P2` → `P3`. With the same priority, the lowest issue number goes first.
Tickets with `needs-human`, `blocked`, `muted`, `after-release`, `rank` or `epic` wait. A ticket that depends on a muted ticket waits too.

The agent asks you only on GitHub: on the issue that needs the answer, with the label `needs-human` and a
comment that mentions `@Larspolo` (#862). It does not ask with phone notifications or only in the status report.

## Labels

- Priority: `P0`, `P1`, `P2`, `P3`
- Size: `size:S`, `size:M`, `size:L` (L tickets are split before work starts)
- Kind: `bug`, `feature`, `tooling`, `design`, `docs`, `cleanup`
- Flow: `needs-human`, `blocked`, `muted`, `after-release`, `rank`, `release`, `in-progress`, `epic`, `agent-status`, `paused`

The file `.github/labels.txt` defines the labels. The Labels workflow creates them on `main`.

## Where the agent runs

- **Scheduled cloud runs** (recommended): a scheduled task in Claude Code on the web starts a new session on
  a timer. Each run uses your Max quota. Change or stop the schedule at claude.ai/code (scheduled tasks).
  The scheduled task must have the repository `Larspolo/travel-aggregator`. Without it, the runs cannot clone the code.
  To set it: open claude.ai/code/routines → the task → menu next to its name → **Edit** → **Advanced
  settings** → **General** → **Repository** → `Larspolo/travel-aggregator`. Below it, select the **Cloud environment**
  that allows the Mojang hosts. Select the model in the model selector of the prompt box. **Save changes**.
  More runs can work at the same time (start them with **Run now**). They claim tickets with a comment, so two
  runs do not do the same ticket. With the argument `max`, a run continues until no ticket is ready, and it
  starts a fresh run when its context is half full. To stop all runs: add `paused` to the status issue.
- **On your computer**: `scripts/autopilot.sh 3` runs 3 cycles, one ticket each.
  It needs the Claude Code CLI and the GitHub CLI (`gh auth login`).
- **By hand**: open a Claude Code session in this repository and type `/autopilot`.

## Network for the tests

Some tests of the project need hosts outside the package managers. The file `scripts/allowed-domains.txt` lists
them, one per line. Open the cloud environment menu in the session title bar → Edit → Network access → Allowed
domains, delete the old list and paste the whole file. Keep "Allow package managers" on. When an agent adds a host to
the file, it opens a `needs-human` ticket that asks you to paste it again (`docs/ENVIRONMENT.md`, "Network"). Steps: https://code.claude.com/docs/en/cloud-environments#network-access

## Setup script (faster start)

Use one cloud environment for all runs. All tickets use the same tools.
`scripts/cloud-setup.sh` installs the tools of the tests (`docs/ENVIRONMENT.md`, section "Setup script").
The cloud keeps the result as a snapshot for about 7 days, or until you change the script or the network
settings. Then the script runs again one time. To use it: cloud environment menu in the session title bar → Edit →
**Setup script** → paste the content of `scripts/cloud-setup.sh` → **Save**. When the file changes, the agent
sees it at the start of a session (the SessionStart hook compares `SETUP_VERSION`) and opens a `needs-human`
ticket that asks you to paste it again.

The agent also improves CI, this script and the other parts of the system by itself (`improve` skill). For settings
that only you can change (the environment, the network, the scheduled task, GitHub), it opens a `needs-human`
ticket with numbered steps.

## Pacing (no steering needed)

The runs are paced without you. `framework/tools/usage.py` reads the usage of your subscription (the 5-hour and 7-day windows,
as the Claude Code CLI reports them) and computes the number of runs: fast to 90 % of the 5-hour window 2 hours before
its reset, then slower to 98 % at the reset (your decision, 2026-10-26), and not the week faster than it passes
when `week_guard` in `agent.toml` is `true` (now `true` again after the release v0.1.0, your decision, 2026-11-01).
You do not need to send percentages.
A run of the scheduled task cannot start other runs (#566). So the workflow `pacer.yml` (#3193, #3194) runs
`framework/tools/pacer.py` every 10 minutes: it computes the runs that the target misses (`usage.fire`, at most `max_fire` of
`agent.toml` at a time) and starts them through the API trigger of each scheduled task (your secrets
`PACER_URL_<TASK>` and `PACER_TOKEN_<TASK>`). One workflow run loops for 5.5 hours, then starts the next one: GitHub
fires the cron of this repository only a few times per day. A red Pacer run shows a failed call (a wrong token: make
a new API token and change the secret). The scheduled tasks have no schedule of their own. To stop all runs: add `paused` to the status issue.

## CI and the merge

The repository is public, so GitHub Actions minutes are free (#370). CI runs only the quick checks on each PR (lint
and fast tests, about 1 minute), so that a PR merges soon. The full suite (slow tests, server tests, package)
runs each night on `main` (your decision, 2026-10-26); start it by hand with Actions → CI → Run workflow → "full".
The runs do the slow and server checks that a change needs in their own session. The workflow `automerge.yml`
merges an agent PR when its CI is green. It does not merge a PR with the label `hold`, or a PR whose ticket has `needs-human` or
`blocked`. After each merge it starts CI on `main`; a red run on `main` opens a `P0` ticket, and the runs fix it first.
To stop one PR, add `hold` to it. To stop all runs, add `paused` to the status issue.
The ruleset `Protect main` (Settings → Rules) refuses force pushes and deletes of `main`.

## Files that steer the agent

| File | Content |
|---|---|
| `CLAUDE.md` | Project guide and rules. Every session reads it. |
| `docs/LEARNINGS.md` | What the agent learned. It updates this file itself. |
| `steering/project/PRINCIPLES.md` and `steering/system/PRINCIPLES.md` | The direction of the project, made from your decisions. The agents recommend by it, and tell you when an answer goes against it. Edit it to change the direction. |
| `steering/project/DECISIONS.md` and `steering/system/DECISIONS.md` | The log of your decisions. The agents add a line for each answer. |
| `steering/project/ROADMAP.md` | The features of the three goals (done or missing). Add a line to get a feature built: the agents make an epic from it (`roadmap` skill). |
| `.claude/skills/autopilot/` | The work cycle. |
| `.claude/skills/verify/` | How to test a change. |
| `.claude/skills/ticket/` | How to write and split tickets. |
| `.claude/skills/improve/` | How the agent measures and improves its own process. |
| `.claude/skills/roadmap/` | How the agent makes epics from the roadmap and reviews it. |

You can edit these files. The agent follows the version on `main`.

## Several owners (#4229)

Each GitHub login of `owners` in `agent.toml` steers the agents (default: `[owner]`). When two owners ask opposite
things, `owner` decides. A run never adds a login by itself: Automerge holds a PR that changes `owner`, `owners` or
`[accounts]` until a login of main's `owners` approves it (`framework/tools/owner_gate.py`).
