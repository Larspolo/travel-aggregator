# Principles: the agent system

The direction of travel-aggregator for the agent system (how the runs work): what the owner prefers when two good
options compete. These principles come from the owner's decisions in the aoe2mc project (Larspolo/aoe2mc), where this
agent system started; `aoe2mc#N` names an issue there. New decisions of this project go to
`steering/system/DECISIONS.md`. The project principles (P1 to P5) are in `steering/project/PRINCIPLES.md`.

How to use it:
- **Agents.** Before you recommend an option (decision ticket, PR, epic), compare each option with these principles.
  Recommend the option that follows them, and name the principle in the recommendation ("follows P6").
  When two principles conflict, say so in the ticket: that is a real decision for the owner.
- **Owner.** When your answer does not follow a principle, the agent tells you in the comment that records the
  decision. Then you can change the principle, or keep your answer as an exception. Edit this file at any time:
  the agents follow the version on `main`.
- **Over time.** Each decision adds a line to `steering/system/DECISIONS.md`. The `improve` skill measures how often the owner
  takes the recommendation and updates the principles when they do not predict the owner's answers.

## P6. Ship "fine for now", expand later

Take the smallest option that works now, and make the next step a later ticket. Do not block on the ideal version.
- "A fine for now, expand with C" (aoe2mc#1308). "A at least" (aoe2mc#961). Control groups later (aoe2mc#745).
- The owner continued the siege design "for now" although not pleased with the look (aoe2mc#1353).

## P7. The owner's time is the scarcest resource

Ask the owner only what a person must judge. Measure, test and close the rest yourself.
- Ask only when there are several clear options and no single best one, and only on GitHub (aoe2mc#623, aoe2mc#862).
- Never ask for times, values or texts: test them automatically (aoe2mc#1159). Assign a check only when the agent
  thinks it is fully okay (aoe2mc#603, aoe2mc#668).
- Group the owner's tasks in one session, with a guide in the chat (aoe2mc#1123, aoe2mc#1674). Close the tickets that only
  need a close (aoe2mc#1674). An owner-heavy task waits until the end (aoe2mc#777, aoe2mc#907).
- Without a report of a fault, assume it works (aoe2mc#324).

## P8. Done means the whole scope

An epic closes when each item of its full scope works, or the owner excluded it with a reason (aoe2mc#820, aoe2mc#985).
Each owner question gets an answer (aoe2mc#971). The end goal is full support, not a demo: "full replay file support in the
end" (aoe2mc#371), 100 % = ready for outside play tests (aoe2mc#878).

## P9. Use the whole quota, and improve only from data

Use each usage window to its limit (aoe2mc#587). Change the process only where data shows a loss, and measure the effect
(aoe2mc#900, aoe2mc#1629). A hunch (for example "tokens are the bottleneck") is a thing to test, not a fact (aoe2mc#1629). A lever of the
`improve` skill whose signal is above its threshold is data enough (P11).
Expensive tools (a real browser on many pages) only when they are really needed (aoe2mc#176).

## P10. Fix the cause in all places, with a check or a structure, not a rule

When one cause shows in many places, fix all of them, not only the place that you saw. Prefer a structure that
prevents the fault (a data file, a merge driver, a workflow) or a check that fails (a test, a lint) to a rule that each
agent must remember. The owner should not have to ask for the wider fix.
- One table of a game file moved to a data file. The owner asked "Should we generalise this further?" (aoe2mc#1702) and
  then made the epic for all game data (aoe2mc#1909): by content, not by size, and a lint, not a question for each run.
- A label and a workflow close the tickets, not the owner (aoe2mc#1740). The merge workflow solves `.jsonl` conflicts (aoe2mc#1864).
- Avoid structures that conflict: a test of the length of a data file conflicts and tests nothing real (aoe2mc#2008).
- Data and configuration files exist so that a change there needs no change of code or tests: no test checks their
  content, only their form and the behavior of the code (owner, 2026-10-29).

## P11. The system improves itself boldly, and counts work, not time

The owner must never have to suggest an improvement of the system (owner, 2026-10-29). When the owner changes the system
by hand, the improve loop missed a lever: the next review comes soon, names the lever, and fixes all its places.
- The review checks all levers each time: context per call, work that a tool or workflow can do, the cheapest model
  that does the job well, API calls, conflicts by design, data in data files, merge drivers, clocks that measure work,
  owner chores, measurement gaps. These are the changes that the owner made by hand on 2026-10-28 and 2026-10-29.
- Make each change that pays, also a redesign, also one that needs owner steps. Pause the project when the runs
  must wait for those steps.
- A wait to measure a change counts merged PRs ("wait 50 PRs"), never hours: the speed changes, and a pause merges
  nothing (aoe2mc#2039). Only a real clock stays in time (a quota window, a stopped run).
- The gap between reviews follows their results (owner, 2026-10-29): while reviews find changes it halves from 80
  PRs down to 10, while they find nothing it doubles from 80 up to 640, and each turn of the result resets it to 80.

## Tensions

- P6 against P8: "fine for now" is a step, not the end. An epic stays open until the later step is done or excluded.
- P7 against quality: the owner does not check each item. A check closes on the agent's evidence, and the owner checks a sample later (aoe2mc#1708).
- P6 and P9 against P10: a pilot is "fine for now" and can wait for its numbers, but the epic for all places starts at
  once, with the pilot as its first sub-issue (aoe2mc#1909).
- P9 against P11: P9 measures before and after each change; P11 does not wait for a measured loss when a known lever
  is above its threshold. The measurement then shows if the change paid.
