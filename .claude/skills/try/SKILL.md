---
name: try
description: Let the owner of travel-aggregator try the new features with the development server on the owner's computer. Start the server at the newest main, show what is new, and make a ticket for each feedback. Only for a local Claude Code session that the owner starts in a clone of the repository and types "/try" in.
---

# Try the new features

The owner tries a feature by hand when an image is not enough: a click, an input, a game, a flow of pages. This
skill runs on the owner's computer. A cloud session has no window: stop there and say so.

## 1. Prepare

1. `git fetch origin main && git checkout main && git pull`, then run `install` of `[commands]` in `agent.toml`.
2. List what is new: the epics and the features closed since the last try (the newest comment "Tried:" on the status
   issue; with no comment, the last 7 days), and the open test tickets (`needs-human` with the `play` text of
   `[owner_tasks]` in `agent.toml`).
3. The preview server runs the newest green `main`: `https://travel-preview.larspolo.nl` (`deploy/preview/`).
   Compare the `commit` of `https://travel-preview.larspolo.nl/api/health` with `git rev-parse origin/main`; when
   they differ, wait up to 10 minutes (CI with its job `preview`, then watchtower). Give the owner the address
   and, per new feature, 1 to 3 steps to try it. Only when the owner asks for a local run: start `dev` of
   `[commands]` in `agent.toml` in the background and wait for its ready line.

## 2. Take the feedback

While the owner tries the features:
- A problem or a wish: make a ticket with the `ticket` skill (the steps, what the owner saw, what the owner wants;
  a screenshot or a log line as evidence). Say its number in one line.
- A crash or an error line of the server: find the cause in the server output and the code, then make a bug ticket.
- A test ticket that passes: comment "Tried: OK" on it and add the label `close`.

## 3. End

Stop a local server, if you started one. Comment "Tried: <date>" on the status issue, with the list of new tickets.
When the preview does not show the newest commit, or it does not answer, make a bug ticket for it first: each other
try depends on it (the job `preview` of the CI run on `main`, then the owner's `docker compose logs` on the server).
