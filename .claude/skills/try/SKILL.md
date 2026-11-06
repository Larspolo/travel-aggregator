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
3. Start the development server with `dev` of `[commands]` in `agent.toml`, in the background. Wait for its ready
   line. Give the owner the address (for example `http://localhost:8000`) and, per new feature, 1 to 3 steps to try it.

## 2. Take the feedback

While the owner tries the features:
- A problem or a wish: make a ticket with the `ticket` skill (the steps, what the owner saw, what the owner wants;
  a screenshot or a log line as evidence). Say its number in one line.
- A crash or an error line of the server: find the cause in the server output and the code, then make a bug ticket.
- A test ticket that passes: comment "Tried: OK" on it and add the label `close`.

## 3. End

Stop the server. Comment "Tried: <date>" on the status issue, with the list of new tickets. When `dev` does not work,
make a bug ticket for it first: each other try depends on it.
