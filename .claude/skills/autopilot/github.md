# Autopilot: GitHub access and labels

Read this file when you need a GitHub REST call or a label name (part of the `autopilot` skill, #1700).

## GitHub access

Use the GitHub MCP tools (`mcp__github__*`) when the session has them. Else use the REST API with `gh api`:
it works in cloud and local sessions. Cloud sessions block GraphQL, so `gh issue list` and `gh pr create` fail there.
`search/issues` works when `q` has `is:issue` or `is:pull-request` (else 422): look for a duplicate with
`gh api -X GET search/issues -f q='repo:OWNER/NAME is:issue WORDS' --jq '.items[] | "#\(.number) \(.state) \(.title)"'`.
Put long text in a file and pass it with `-F body=@file.md`.
Put the method after the path (`... -X PATCH`): the permission rules match the start of the command.
`gh api --paginate` stops after the first page in the cloud (403 "Numeric-ID repository paths": the next-page link
names `repositories/ID`): add `&page=P` in a loop until a page has fewer than 100 entries (#1707).

| Action | `gh api repos/OWNER/NAME` (`repo` in `agent.toml`) + |
|---|---|
| Open issues | `/issues?state=open&per_page=100` (entries with `pull_request` are PRs) |
| New comments since T | `/issues/comments?since=T&per_page=100` and `/pulls/comments?since=T&per_page=100` |
| Comment | `/issues/N/comments -F body=@file.md` |
| Add a label | `/issues/N/labels -f "labels[]=in-progress"` |
| Remove a label | `/issues/N/labels/in-progress -X DELETE` |
| Change an issue | `/issues/N -X PATCH -F body=@file.md` (or `-f state=closed`) |
| New issue | `/issues -f title="..." -F body=@file.md -f "labels[]=P2"` |
| Add a sub-issue | `/issues/N/sub_issues -F sub_issue_id=<id of the child (not its number)>` |
| Open PRs | `/pulls?state=open` |
| New PR | `/pulls -f title="..." -f head=BRANCH -f base=main -F body=@file.md` |
| CI of a commit | `/commits/SHA/check-runs --jq '.check_runs[] \| "\(.name) \(.status) \(.conclusion)"'` |
| Automerge sweep (step 2) | `/actions/workflows/automerge.yml/dispatches -f ref=main`: GitHub drops its cron runs, and a CI run of `GITHUB_TOKEN` gives no `workflow_run` event (#734). Still open 15 minutes after the sweep → read `/actions/workflows/automerge.yml/runs?per_page=5` and say why on the status issue |
| Start CI on a branch | `/actions/workflows/ci.yml/dispatches -f ref=BRANCH` (CI on `main` after a merge by hand) |
| Merge state of a PR | `/pulls/N --jq .mergeable_state` (`dirty` = merge conflict: CI does not start, merge `origin/main`) |
| CI job log | not possible with `gh` in the cloud: use `mcp__github__get_job_logs`, or run the check locally |

## Labels

| Group | Labels |
|---|---|
| Priority | `P0` (do next), `P1`, `P2`, `P3` (later) |
| Size | `size:S` (one short PR), `size:M` (one PR), `size:L` (too large: split first) |
| Kind | `bug`, `feature`, `tooling`, `design`, `docs`, `cleanup` |
| Flow | `needs-human` (waits for the owner), `blocked` (waits for another ticket), `in-progress`, `epic` (parent of sub-issues), `agent-status` (the status issue), `paused`, `owner-sample` (a closed check for the owner's sample, #1708) |
| PR | `hold` (the Automerge workflow does not merge it), `conflict` (the workflow could not merge it: fix it in step 2) |

