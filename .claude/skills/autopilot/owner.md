# Autopilot: ask the owner, denied actions and check tickets

Read this file when you must ask the owner, when the auto mode denies an action, when a ticket is wrong, and in
step 7 when the owner must check something in the game (part of the `autopilot` skill, #1700).

## Ask the owner

Ask the owner (owner rule, #862): only with the label `needs-human`, the label `for-lars` or `for-jeroen` (`ticket` skill, #72) and a comment on the issue that needs the answer.
The comment mentions the owner (`@` and `owner` of `agent.toml`) and says exactly what the owner must do. Never ask with PushNotification, in the
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

If the ticket is wrong or not possible: comment why, add `needs-human`, run `python3 framework/tools/claim.py N --release` (it
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
