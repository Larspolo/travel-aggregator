"""The agent PRs that `unconflict.yml` merges `main` into, found with git and 3 to 4 API calls (2026-10-29).

The workflow read each open agent PR (`pulls/N`, up to 3 times while GitHub computed the merge state), the CI run of
its head and its head commit: about 3 + 2 calls per open PR at 38 runs an hour, a large part of the hourly REST limit
that all workflows share (it ran out at 14:21 to 14:26 on 2026-10-29). Git calls do not count:

- dirty: `git merge-tree` of `main` and the branch has a conflict when it reads no `.gitattributes` (`--attr-source`
  of the empty tree): GitHub ignores `merge=union` and the merge drivers, so it calls such a PR "dirty" (#280).
- red by a red main (#3685): the newest CI run of its head failed, and the newest run on `main` before it failed
  too, while `main` is green now. One list of the newest CI runs gives the run of each head.
- the age of the head (younger than 5 minutes: its run can still merge it) comes from `git log`.

    python3 framework/tools/unconflict_pick.py      # one line per PR: <number> <branch> <head sha> <label conflict: 1|0> <dirty|red>

It fetches `main` and the branches of the open agent PRs into `refs/remotes/origin/`.
"""
import datetime
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cycle_start import AGENT  # noqa: E402  (the branches of agent PRs, #3382)
from dashboard import api  # noqa: E402

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
YOUNG = 300                             # seconds: the run that pushed the head can still merge main itself


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=120)


def dirty(branch, main="origin/main"):
    """True when the merge of `main` into the branch has a conflict for GitHub (no merge attributes, no drivers)."""
    return git(f"--attr-source={EMPTY_TREE}", "merge-tree", "--write-tree", main, branch).returncode == 1


def has_main(branch, main="origin/main"):
    return git("merge-base", "--is-ancestor", main, branch).returncode == 0


def red_by_main(run, main_runs):
    """True when the CI run of a head failed and the newest main run before it failed too (#3685). main_runs:
    [(conclusion, created_at)] newest first."""
    if not run or run.get("conclusion") != "failure":
        return False
    before = [c for c, t in main_runs if t < run["created_at"]]
    return bool(before) and before[0] == "failure"


def pick(prs, main_runs, green, recent, head_run, is_dirty, contains_main, head_time, now):
    """[(number, branch, sha, label, why)]: the open agent PRs without `hold` whose branch lacks `main` and that are
    dirty, have the label `conflict`, or are red only by a red main while main is green (why: "dirty" or "red").
    recent: {sha: newest CI run} of one list; head_run(sha): the newest run of a head that is not in it (one call).
    A head younger than YOUNG seconds waits for its own run."""
    out = []
    for p in prs:
        labels = {x["name"] for x in p.get("labels", [])}
        branch, sha = p["head"]["ref"], p["head"]["sha"]
        if not branch.startswith(AGENT) or "hold" in labels or contains_main(branch):
            continue
        label = "conflict" in labels
        if is_dirty(branch) or label:
            why = "dirty"
        elif green and red_by_main(recent[sha] if sha in recent else head_run(sha), main_runs):
            why = "red"
        else:
            continue
        if now - head_time(branch) < YOUNG:
            print(f"#{p['number']}: the head is younger than 5 minutes", file=sys.stderr)
            continue
        out.append((p["number"], branch, sha, int(label), why))
    return out


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    prs = [p for p in api("pulls?state=open&per_page=100")
           if p["head"]["repo"] and p["head"]["repo"]["full_name"] == (repo or p["base"]["repo"]["full_name"])]
    refs = [f"+refs/heads/{b}:refs/remotes/origin/{b}" for b in {p["head"]["ref"] for p in prs}]
    if git("fetch", "-q", "origin", "+refs/heads/main:refs/remotes/origin/main", *refs).returncode:
        sys.exit("git fetch of main and the PR branches failed")
    runs = api("actions/workflows/ci.yml/runs?branch=main&status=completed&per_page=100")["workflow_runs"]
    main_runs = [(r["conclusion"], r["created_at"]) for r in runs
                 if r["event"] != "schedule" and r["conclusion"] in ("success", "failure")]
    head = git("rev-parse", "origin/main").stdout.strip()
    checks = api(f"commits/{head}/check-runs?check_name=quick")["check_runs"]
    green = any(c["conclusion"] == "success" for c in checks) or bool(main_runs and main_runs[0][0] == "success")
    recent = {}
    if green:                                       # the newest run of each head, newest first (#3685)
        for r in api("actions/workflows/ci.yml/runs?per_page=100")["workflow_runs"]:
            recent.setdefault(r["head_sha"], r)
    head_run = lambda sha: (api(f"actions/workflows/ci.yml/runs?head_sha={sha}&per_page=1")["workflow_runs"] or [None])[0]
    rows = pick(prs, main_runs, green, recent, head_run, lambda b: dirty(f"origin/{b}"),
                lambda b: has_main(f"origin/{b}"),
                lambda b: int(git("log", "-1", "--format=%ct", f"origin/{b}").stdout.strip() or 0),
                datetime.datetime.now(datetime.timezone.utc).timestamp())
    for row in rows:
        print(*row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
