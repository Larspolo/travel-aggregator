# Autopilot: ask the owner, denied actions and check tickets

Read this file when you must ask the owner, when the auto mode denies an action, when a ticket is wrong, and in
step 7 when the owner must check something in the game (part of the `autopilot` skill, #1700).

## Before you ask: the owner is the last resource

The owner (2026-11-14): "It should automatically use the available resources to fix it, and not ask me first."
A blocked step stays your work until each resource failed. Go down this list, and note each try with its result:

1. **Another route on this machine.** A host that gives no answer, a download that fails, a tool that is not there:
   use another server or mirror of the same data, another API of the same service, the package of a registry, or a
   copy that is in the repository. Put the route that works into the code or the setup (a list of servers in the
   script, `scripts/cloud-setup.sh`), so that the next run does not search again.
2. **Another machine.** A job of GitHub Actions has a network of its own. When a host gives no answer from a cloud
   session, a workflow can run the command and commit the result or make a PR.
3. **A device or a program that a cloud session does not have** (a phone, a second browser, the installed app,
   the real program). Do not give the check to the owner (owner, 2026-11-14). An emulator or the real program on
   the worker of the hub does it: for a phone, the Android emulator of the Android SDK. Suggest the tool
   yourself. Make a device ticket: no `needs-human`, a line that names the tool that the check needs, and the
   line `Depends on: #N` with the ticket of your project that brings the device tickets to the worker (when the
   project has none, make it: "Do the device tickets on the worker of the hub"). Ask the owner only for a
   sense that only a person has (how it feels in the hand), or with a proposal card for a tool that costs money
   or needs a key.
4. **A rule of the project stops the step.** Do not go around a rule. When the rule only gives the owner a step that
   a machine can do, ask for the rule, not for the step: a decision card that names the rule and its source, with
   your recommendation. One answer then removes the step for each later run.
5. **Only then a card**, for what only the owner has or decides: an account, a secret, money, a device, a right, a
   direction. The card names each try (`Tried:`) and says why no machine can do the step (`Only the owner:`).

A denial is not a resource that failed. When the auto mode denies an action, or a network policy refuses a host (403
or 407), a person or a guard decided it: do not go around it with another tool or another machine. That is a card.

## Ask the owner

Ask the owner (owner rule, #862) only with a card on the issue that needs the answer: a comment with the section
`## For the owner` (`ticket` skill, "needs-human tickets"), and then the label `needs-human`. Write the comment first:
the Cards workflow (`cards.yml`, `framework/tools/card.py`) reads the card when the label comes. It makes the owner
the assignee of a complete card, and GitHub tells the owner: do not write `@` and the name of the owner yourself. It
takes the label off an incomplete card and comments the lines that the card needs. Check a card before you post it:
`python3 framework/tools/card.py --text FILE`. When the owner of the card comments on it, the workflow takes the label and the
owner as the assignee off at once (owner, 2026-11-14): the owner has no step after the answer. The next run reads
the answer in step 3 and does what it says. The line `For:` of the card names the owner who knows the answer when it is not `owner` of `agent.toml`; until
#2867 is done, also add the label `for-lars` or `for-jeroen` (`ticket` skill, #72). Never ask with PushNotification, in the
session, or only in the status report. When the auto mode denies an action (for example closing an issue), do not send
it through another tool: add `needs-human` to that issue and comment the evidence and the action. When the owner did
it, remove the label.

## Close an issue

The auto mode can deny a close by the API (#862, #1641). So close with the label `close` (owner, #1740): write the
evidence comment first, then add the label (`gh api repos/OWNER/NAME/issues/N/labels -f 'labels[]=close'`). The
workflow `close.yml` removes `close`, `needs-human` and `in-progress`, closes the issue as completed and deletes its
claim refs. Use it for a finished epic, an answered decision ticket and a check ticket without bugs. When the auto mode
denies the label too (a session without the owner's `autoMode` rule, #1740: `claude auto-mode config` lists its allow
lines), do not try another way: keep the comment, add `needs-human` and "Please close".

If the ticket is wrong or not possible: say why in a card (`Kind: question`), add `needs-human`, run `python3 framework/tools/claim.py N --release` (it
removes `in-progress`). Do not merge partial work: add `hold` to its PR (the workflow also skips a PR whose ticket has `needs-human` or `blocked`).

## Check tickets (step 7)

The merge closes the ticket (`Closes #N`), and the Automerge workflow removes `in-progress`. If the owner must check something in the game, make
a small check ticket without `needs-human` first (#580). An agent runs the check itself (level 4 of `verify`: real server,
simulated clicks through the same functions as the player input, `tools/mc_shot.py`) and comments the results and the
images. When the check finds a bug, it makes a bug ticket for each one (with its lane: `ticket` skill, "Model lanes", #5770), adds "Depends on: #bug" to the check ticket, and does
not add `needs-human`: when the bugs are closed, the check ticket is a candidate again and a later run checks again (owner, #668).
A check ticket that also ships a tool (#3324) and finds bugs: ship the tool with
`python3 framework/tools/ship_pr.py N --part` ("Part of #N"): the merge then does not close the check ticket.
After a check without bugs it closes the check ticket on its evidence (owner decision B, #1708: progress does not wait
for the owner): a comment with the evidence of each point (screenshots, real clicks, values) and a short list of what only
a person can check (sound, the feel of a control, "is it fun": `verify` level 5, #1707), the label `owner-sample`, then the close. The owner checks a
sample of these closed tickets later in one game (`human` skill). The close: see "Close an issue" below. Never ask the owner about
times, speeds, values or texts: measure them and compare them with the original (owner, #1159). A look question links the image
before next to the image after (or the original next to the result).
