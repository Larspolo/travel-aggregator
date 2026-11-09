---
name: roadmap
description: Turn the goals of travel-aggregator in steering/project/ROADMAP.md into epics. Use in the queue refill (autopilot step 5) when the open epics have no work left, and when `python3 framework/tools/claim.py 0 --roadmap` gives the roadmap review to the run, to review the feature list.
---

# Plan toward the goals

`steering/project/ROADMAP.md` lists the features of each goal: done (`[x]`) or missing (`[ ]`, with a key such as
`goal:feature`). The sub-items under a feature say what the user can do or see when it is done.

## Make the next epic (in the refill)

Do this in the refill of autopilot step 5 (you hold its lock, `python3 framework/tools/claim.py 0 --refill`), when the
open epics have no goal left that an agent can do. A goal that has an open sub-issue is not left, also when that
sub-issue waits for another ticket: then make the next epic (owner, 2026-11-06: a deep run read such waiting sub-issues
as work left and stopped with no refill, 113k eq for no ticket).

1. List all the epics, page by page: `gh api "repos/OWNER/NAME/issues?labels=epic&state=all&per_page=100&page=P"` (`repo` in `agent.toml`), with P = 1, 2, ... until a page has fewer than 100 entries. `gh api --paginate` stops after the first page in the cloud, so add `&page=P` yourself (`../autopilot/github.md`, "GitHub access", #1707; the repository had 115 epics on 2026-11-09). A feature has an epic when an
   epic body names its key ("Roadmap: `<key>`"). A `muted` epic counts too.
2. Pick the goal whose newest epic is the oldest (a goal without an epic first). Tie: the order of the file.
3. In that goal, take the first missing feature without an epic. Grep the code for it first: when the code does it
   already, mark it `[x]` in the next PR and take the next one. A feature whose line names an open `needs-human` ticket
   that is no input ("Kind: outside" or "Kind: setting"), for example a decision or an owner issue with a question in a
   comment, waits for the answer: take the next one (`usage.held`, #432, #1059).
4. Make the epic with the `ticket` skill: the goal (what the user sees), the sub-items of the feature as acceptance
   criteria, a criterion that checks the whole feature, the criterion "`README.md` describes what this epic added, and
   `python3 -m pytest -m readme` passes" (one README PR at the end, `steering/project/PRINCIPLES.md`, "Try a
   feature"), the line "Roadmap: `<key>`", and the labels `epic`, `feature`,
   `size:L`, `P3`. Compare it with `steering/project/PRINCIPLES.md`. A choice with no single best option, or in an
   area of "Owner involvement", gets a decision ticket first (`ticket` skill, "Decision tickets").
5. Owner steps first (owner, 2026-11-06: the work of the owner must not stop the progress). List each step of the
   feature that only the owner can do. Make a `needs-human` ticket only when the owner can do it at once: never a
   `needs-human` ticket that waits for agent work (owner, 2026-11-06).
   - An input that the owner can give now: a real payload of a travel site (P1, P5), a setting or a secret on a
     server, an account, a decision. Make it now as the first sub-issue; each agent sub-issue that needs it gets
     "Depends on: #<it>".
   - Agent checks first (owner, 2026-11-07): never ask a person to check what an agent can check. A layout, a
     sideways scroll, a width, a text, a value, a click flow or a page at phone width (Playwright with the device of
     the phone, `hasTouch`), the API of the preview (`scripts/preview_check.sh`): the agent checks it on a local server
     with the same commit and comments the evidence (`autopilot` skill, `owner.md`, "Check tickets"). These are never
     steps of an owner ticket, also when the agents cannot log in to the pages of the preview.
   - A check that only a person can do, after agent work: a real travel site with Tampermonkey in the owner's browser
     (P1), the feel of a control under a finger on a real phone, `docker compose up` on the owner's computer. Make no
     ticket yet. Write it in the epic
     body, in a section `## Owner checks`, one line each: `- After #a, #b: <what the owner checks>` (write the line when its sub-issues exist, in step 7 or
     in a later refill). The run whose
     PR closes the last of these tickets makes the `needs-human` ticket at once (`autopilot` skill, `report.md`),
     not at the end of the epic.
6. Look ahead for inputs: read the next 2 missing features (the ones that steps 2 and 3 give after this one) and make
   their input tickets of step 5 now, each with the line "Roadmap: `<key>`". Grep the open `needs-human` tickets for
   the key first (no duplicate). When the epic of that feature comes, add its input tickets as sub-issues.
7. Make its first 3 to 5 agent sub-issues (`size:S` or `size:M`, `P3`). The first one is small and useful alone.
8. Do not change `steering/project/ROADMAP.md` for a new epic: the key in the epic body is enough.

## Review the feature list (the roadmap review)

When `python3 framework/tools/claim.py 0 --roadmap` exits 0, after step 8 of the autopilot skill:

1. Mark a feature done (`[x]`, with the epic number) when its epic is closed: `python3 framework/tools/roadmap_status.py`
   prints the features to mark ("mark done"), with no epic ("no epic") and `[x]` with no number ("no number").
2. Compare each goal with the code and the principles: what must a user do that the project cannot do yet? Add at
   most 5 missing features, each with a new key, one line and its sub-items.
3. Keep the order: the features that the next features need come first.
4. Put the change into the PR of your ticket, or make a `docs`, `size:S` ticket for it. The owner can change the list
   at any time.
