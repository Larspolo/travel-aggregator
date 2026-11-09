---
name: roadmap
description: Turn the goals of travel-aggregator in steering/project/ROADMAP.md into epics. Use in the queue refill (autopilot step 5) when the open epics have no work left, and when `python3 framework/tools/claim.py 0 --roadmap` gives the roadmap review to the run, to review the feature list.
---

# Plan toward the goals

`steering/project/ROADMAP.md` lists the features of each goal: done (`[x]`) or missing (`[ ]`, with a key such as
`goal:feature`). The sub-items under a feature say what the user can do or see when it is done.

## Make the next epic (in the refill)

Do this in the refill of autopilot step 5 (you hold its lock, `python3 framework/tools/claim.py 0 --refill`), when the
open epics have no goal left that an agent can do.

1. List the epics: `gh api "repos/OWNER/NAME/issues?labels=epic&state=all&per_page=100"` (`repo` in `agent.toml`). A feature has an epic when an
   epic body names its key ("Roadmap: `<key>`"). A `muted` epic counts too.
2. Pick the goal whose newest epic is the oldest (a goal without an epic first). Tie: the order of the file.
3. In that goal, take the first missing feature without an epic. Grep the code for it first: when the code does it
   already, mark it `[x]` in the next PR and take the next one.
4. Make the epic with the `ticket` skill: the goal (what the user sees), the sub-items of the feature as acceptance
   criteria, a criterion that checks the whole feature, the criterion "`README.md` describes what this epic added, and
   `python3 -m pytest -m readme` passes" (one README PR at the end, `steering/project/PRINCIPLES.md`, "Try a
   feature"), the line "Roadmap: `<key>`", and the labels `epic`, `feature`,
   `size:L`, `P3`. Compare it with `steering/project/PRINCIPLES.md`. A choice with no single best option, or in an
   area of "Owner involvement", gets a decision ticket first (`ticket` skill, "Decision tickets").
5. Make its first 3 to 5 sub-issues (`size:S` or `size:M`, `P3`). The first one is small and useful alone.
6. Do not change `steering/project/ROADMAP.md` for a new epic: the key in the epic body is enough.

## Review the feature list (the roadmap review)

When `python3 framework/tools/claim.py 0 --roadmap` exits 0, after step 8 of the autopilot skill:

1. Mark a feature done (`[x]`, with the epic number) when its epic is closed: `python3 framework/tools/roadmap_status.py`
   prints the features to mark ("mark done"), with no epic ("no epic") and `[x]` with no number ("no number").
2. Compare each goal with the code and the principles: what must a user do that the project cannot do yet? Add at
   most 5 missing features, each with a new key, one line and its sub-items.
3. Keep the order: the features that the next features need come first.
4. Put the change into the PR of your ticket, or make a `docs`, `size:S` ticket for it. The owner can change the list
   at any time.
