---
name: ticket
description: Write, size and split GitHub issues (tickets) for travel-aggregator in the project format. Use when you make a new ticket, triage an owner's issue, or split a size-L ticket into sub-issues.
---

# Write a ticket

Tickets are GitHub Issues in the repository `repo` of `agent.toml`. Write in ASD-STE100 Simplified Technical English.

## Form

Title: an instruction, less than 70 characters ("Fix the road pass on the sea floor").

Body:

```
## Goal
<One or two sentences: what changes for the user or the developer.>

## Context
<Where in the code: the files and functions that the ticket will change, in backticks (`buildings.py`, `furnish()`),
 why, and the evidence (output, image, test).
 The platform feature that does the job (CLAUDE.md: the platform features first), or why there is none.>

## Acceptance criteria
- [ ] <A result that a test or a check can show.>
- [ ] <...>

## Verify
<The verify level (1-4) and the commands or checks.>

Depends on: #<n>, #<m>        (only when another ticket must close first; at the start of its own line, not in a list item: `dashboard.depends` reads only such lines, #5354)
Start after: <N> PRs after #<M>       (only when the ticket must wait for work, for example to measure a change: N merged PRs after PR #M)
Start after: <YYYY-MM-DD HH:MM> UTC   (only for a real date outside the project, for example a quota reset; never to measure a change, #2039)
```

A ticket that measures a change counts merged PRs, never hours ("the 100 PRs before and after #M", not "24 hours
after"): the speed of the project changes, and a paused project merges nothing (owner, 2026-10-29). `framework/tools/health.py`
lists the open tickets with a date in `Start after:` ("Time waits").

A new line of a data file in `game/data/` needs no criterion "the values are those of the source" and no test of its values:
`tests/test_data_files.py` checks the form of each line with the module of its file in `tests/data_checks/` (#1916, #4778). A ticket that changes only data files names no new
test and no test file: its criterion is that the existing tests pass (owner, 2026-10-29, #4242; `docs/extend.md`).
A test of a menu or a bonus with the names and values of the new line is a test of the data content too. Name a test
of behavior only for a change of code, with test data or the expected value from the data. Never copy the test of an
older ticket of the same epic when that ticket changed only data. Never write a criterion "a test checks that the data file (or a workflow, `agent.toml`, a skill)
holds X": no test checks the content of a data or configuration file (owner, 2026-10-29, `docs/extend.md`).

Make two or more tickets in one call: write them to one file and run `python3 framework/tools/new_tickets.py FILE.md`
(its docstring has the form: `labels:`, `parent:` and `#newK` for a ticket of the same file). One MCP call per ticket
reads the full context again each time: a refill with 6 to 10 such calls paid about 5k eq per call (owner, 2026-11-06).

Labels: one priority (`P0`-`P3`), one kind (`bug`, `feature`, `tooling`, `design`, `docs`, `cleanup`),
one size (`size:S`, `size:M`, `size:L`), and the lane (`lane:haiku`, none or `lane:deep`, section "Model lanes";
a `bug` with a named cause and fix is Haiku). Add `needs-human` when only the owner can do it.
A ticket that changes the agent system (skills, `CLAUDE.md`, the agent tools in `tools/`, workflows, the setup) also
gets `process` (#901): the dashboard counts the merged PRs with it.

`dashboard.py --next` puts the tickets that share fewer files and functions with the work in progress first (#487):
name each file and function that the ticket changes, and no others (tools that only check, such as `render.py`, do not count).

## Size

- `size:S`: one PR, a small diff (about 150 lines or less), clear solution.
- `size:M`: one PR, up to about 400 lines, or one design decision.
- `size:L`: more than one PR, or research first. Do not start an L ticket: split it.

## Split an L ticket

1. Make S or M sub-issues, all in one call with `new_tickets.py` (`parent: E`; else `gh api
   repos/OWNER/NAME/issues/E/sub_issues -F sub_issue_id=<id of the child, not its number>`, or "Depends on" lines in a
   local session). Not the MCP `sub_issue_write`: each call returns the whole parent issue
   and its repository (about 4k tokens; 5 calls cost 20k tokens in one refill).
   Make the first sub-issue small and useful alone.
2. Give the sub-issues the priority of the parent and the order of the work (lower number = first).
3. Add `epic` to the parent. Its acceptance criteria check that the whole goal is covered, not only the sub-issues
   (owner rule, 2026-10-26, #820): name the full scope (a list, a table, or a source such as a wiki of the original) and a check
   that each item of it works, or that the owner excluded it in a comment on the epic. "All sub-issues are closed" is
   never the only criterion; it can be an extra line. Example: "Each code of the list on the wiki works in the
   program, or the owner excluded it." The epic closes when all its criteria are met.

## needs-human tickets

Add one label of `[audience]` in `agent.toml` too (#72): `for-lars` for the agent system (Claude, Docker, the
server, CI, the GitHub settings), `for-jeroen` for the project (decisions, features, the roadmap, and the payload captures of a
new source: Kind `outside`, owner Larspolo on #122). Mention the login
of that label in the comment. The status issue shows one list per label.
The owner reads them on a phone. Give numbered steps, the exact names of settings or files, and what the
owner must reply. One ticket per decision.
Make them early, but only when the owner can do them at once (owner, 2026-11-06): when you make an epic, make its
owner inputs (payloads, settings, decisions) too (the `roadmap` skill, "Owner steps first"). Never make a
`needs-human` ticket that waits for agent work: a check that needs agent work first is a line of the section
`## Owner checks` of its epic, and the run that closes its last ticket makes it.
Each `needs-human` ticket (also when you add the label to an existing ticket: add the section to the body or to
your comment) has a section `## For the owner`, so that the `human` skill (`/human` on the owner's computer, #983)
can prepare and guide it:

    ## For the owner
    Kind: play            (or decision, setting, outside, close, question)
    World: <the command that makes the test data, from CLAUDE.md>
    Start: <the command that starts the program, from CLAUDE.md>
    1. <one step that the owner does>
    2. ...
    Reply: <what the owner must write on the ticket>

Leave out `World` and `Start` when the ticket needs no world.
A check of a live replay gives one line per moment that the owner watches, and one per task without a time;
the `human` skill gives them to `game/watch.py` (#1123). The place is `chopper`, `unit:NAME`, `building:NAME` or
`tile:X,Y`; `end` is the end of the replay:

    Watch: 3:00 | chopper | Do the walk, the turn to the tree and the particles look right?
    Task: Right click the ender pearl, then click a jump in the menu | Is the wait with "Jump to ..." acceptable?
    Watch: end | building:TOWN_CENTER | Is the end clear?

A check ticket ("check X in the game") starts without `needs-human`: an agent runs the check first (`verify`, level 4),
comments the results and screenshots with the list of what only a person can check (#580, #1707): sound, the feel of a control (delay, how hard it is to aim), "is it fun".
The agent judges the clicks (`mc_shot.Client`) and the look (screenshot next to the image of the original) itself; a look point
goes to the owner only when the agent cannot decide, with the reason (`verify`, level 5).
Then it closes the ticket on this evidence with the label `owner-sample` (owner decision B, #1708), not `needs-human`.
No owner point for times, speeds, values or texts: the agent measures them against the original (#1159). A look point links an
image before and an image after.
When the check finds bugs, the check ticket depends on the bug tickets and closes only after a check without bugs (#668).
A bug ticket of a check names the check command in its Verify line, and the fix runs it before the push (`verify`, level
4, "Check tools", #5461). When the data of the check is only on the owner's computer (an install, a `.dat`), the bug
ticket gives the measured cause (a traceback, a count of tiles). Without one, ask the owner for it first (`needs-human`):
three fixes of a guessed cause came back as rework bugs (#5380 → #5422, #5381 → #5423, #5317 → #5361).

## Decision tickets

Owner rule (2026-10-26): when a design has two or more clear options and no single best one (an interface, a game rule,
the order of features), the owner decides on GitHub. Do not choose, and do not ask only in a session.
- Title: "Decide: <the question>". Labels: `needs-human`, the kind of the work (`feature`, `design`, ...), `size:S`,
  the priority of the work that waits for it.
- Body: the question, the options as a table (what the player sees, plus, minus, cost), your recommendation and why,
  and "Reply with the option name (A, B, ...) or your own idea." Compare each option with `steering/project/PRINCIPLES.md` and `steering/system/PRINCIPLES.md` first, and
  name the principle that the recommendation follows ("follows P3"). When two principles give different options, say so.
- The tickets that need the answer get "Depends on: #<decision>", so no run starts them before the owner answers.
- When the owner answers: write the decision into the document of the topic (for example `docs/research/gameplay.md`),
  add its line to the end of `steering/project/DECISIONS.md` and `steering/system/DECISIONS.md` (`taken`, `changed` or `other`, and the principle), remove `needs-human`
  and close the decision ticket. When the answer follows no principle, or goes against one, say it in the comment that
  records the decision: "This does not follow P<n> (<rule>). I will add it as an exception; reply if P<n> must change."
  Do not add `needs-human` for this: the owner replies only when the principle must change.
- One clearly best option: no decision ticket. Choose it and say why in the PR. Exception: an area of the section
  "Owner involvement" of `steering/project/PRINCIPLES.md` (when the file has it) always gets a decision ticket.

A research result that waits for the owner (options, milestones, "the owner decides") gets a `needs-human` ticket
for each decision, with the options and your recommendation, before the research ticket closes. A decision that
is only in a document is lost: milestones 2 and 3 of the replay research (#31) waited without a ticket until the owner asked (#371).

## Model lanes

Give each ticket the cheapest lane that does it right at the first try. Ask: what must the run decide that the body
does not say?

| Lane | Label | When | Cost |
|---|---|---|---|
| Haiku | `lane:haiku` | Nothing to decide. All 3 are true: the body names the place (file, function, data line); the body says the exact result or the check that shows it; the code has a similar change and the body names it (a function, a data line or the PR of an earlier ticket of the series). No render, screenshot or real game is needed. Examples: one ticket of a series (a unique technology, a civilization bonus, a random map script command), a new key of a data file, a fix whose cause the body names, a change of text or docs. `size:S` or a small `size:M`. | About 1/8 of an Opus ticket, 2.4 times the time (#1717; 22 of 24 merged, 2026-10-28) |
| Main (Opus, low effort) | none | Choices with a clear right answer: a bug with a known cause, a design or a look to judge, a check on the real server or client. | |
| Deep (Opus, high effort) | `lane:deep` | A choice where a wrong answer can pass the tests and cost later: a bug with an unknown cause, a race or shared state, a new structure, a change to how the runs decide or plan, a ticket that failed before (red CI after 3 tries, a takeover, reopened), a `size:L` ticket to split. | 4.5 times or more the tokens of a main run |

- The kind label does not choose the lane: a clear `process` ticket can be Haiku or main.
- Each `size:S` ticket gets `lane:haiku` (decision #158, kept by #161: rework 0 / 34, CI runs per run 1.2 before
  1.1), also when the 3 rules of the Haiku row are not all true, unless it needs a render, a screenshot or a judgment
  of a look. In the queue refill, also give `lane:haiku` to the ready `size:S` tickets with no lane that meet this rule.
- Not sure between Haiku and main: Haiku (owner, 2026-10-28). A Haiku run that finds the ticket unclear removes the
  label (`autopilot` skill, `queue.md`). Not sure between main and deep: main.
- Write tickets for Haiku (owner, 2026-10-29: 40 % of the closed tickets had `lane:haiku`, but 2 of 25 ready ones).
  When you make a ticket, decide the place and the result while that code is in your context: write the file, the
  function or data line, the exact result, the earlier ticket or PR of a series as the pattern, and (for a change of code only) the test to copy into the body, then give `lane:haiku` (a render, a
  screenshot or a real game still needs main). Spend at most one `grep` per ticket on it; when it does not find the
  place, give no Haiku label. In the queue refill, also give `lane:haiku` to the ready tickets with no lane whose
  body already meets the Haiku row (read the bodies only, not the code).
- Deep is for about 10 to 20 % of the tickets. Never both lane labels. Decision tickets and epics get no lane label.
- While `reserved` in `[pacing]` of `steering/system/system.toml` names a lane, the main runs never take its tickets (#1994).

## Rules

- One goal per ticket. If you write "and also", make two tickets.
- Search the open issues first. Do not make a duplicate.
- Release focus (`steering/project/RELEASE.md`; skip this rule when the project has no such file): decide for each new `feature` ticket if it goes into the next release
  (the GitHub milestone "vX.Y.Z" of the open release epic) or gets `after-release`, by comparison with the held tickets
  and the milestone ("A new feature: in the next release or after it?"). Not for a ticket with `in-progress` or an open PR: it
  finishes. Before the release, prefer tickets that make the play test work or improve what the player sees and does.
- Do not change the priority of a ticket that the owner set. Propose the change in a comment.
- A ticket that uses a tool, file or function of a ticket that is not merged yet gets "Depends on: #<that ticket>": else it is a candidate at once, and a run claims it without the tool (#829 needed `tools/replay_drift.py` of the open PR #830).
- A ticket that adds an item to the menu of a building (`train.ITEMS`) names its slot: the first free slot of that
  building after the slots of `main` and of the open tickets of the same building. Two tickets that said "a free slot"
  took the same slot and broke main twice in one hour (#1551: slot 18 of the archery range; #1548 and #1549: slot 20 of
  the university).
