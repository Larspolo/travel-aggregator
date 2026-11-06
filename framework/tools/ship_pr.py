"""Ship a ticket in one call: checks, commit, guard, push, PR and its merge state (owner, 2026-10-28).

The first push of a ticket took 2 to 6 tool calls in each run on 2026-10-28, and one run pushed a failed test:
`pytest | tail -1 && git commit && ... && git push` read the exit code of `tail`. This tool reads each exit code.

    python3 framework/tools/ship_pr.py N --message MSG.txt --title "Title" --body BODY.md   # the first push of ticket N
    python3 framework/tools/ship_pr.py N --message MSG.txt                                  # a later push to the open PR
    python3 framework/tools/ship_pr.py N --ci                                               # only wait for the quick CI again
    python3 framework/tools/ship_pr.py N --ci --pr-branch B                                 # the same for the PR of branch B (a takeover)

Steps: `git commit -F MSG.txt` of the staged files (without `--message`: the commits that are there), the lint command of `agent.toml` (also with `--tested`),
the tests (the test files of the branch and the test files that import its changed modules, never the full
suite: the quick CI runs it, owner #4187; `--tested`: you ran them on this tree), `claim.py N --guard` and the push (`merge_main.push`), the PR (a new
one with `Closes #N` in its body; or the open PR of the branch), and `mergeable_state` (`dirty`: run
`python3 framework/tools/merge_main.py --push N`). Then it waits for the quick CI of the pushed commit, up to `WAIT`
minutes after its start (#4784): a red quick CI after the end of its run cost a takeover and a cold run 30 to 40
minutes later (11 to 25 of 50 takeovers on 2026-10-30); the run that wrote the code fixes it with its warm context.
Run it with the Bash `timeout` 600000. Exit 0: shipped (the quick CI is green, still runs at the time limit: `--ci`
waits again). Exit 2: the lint or a test fails, a change of data
files only adds a test (`docs/extend.md`), or the prose of the message or body closes another ticket (#472;
nothing committed or pushed). Exit 3: the
guard or the push fails (do not push by hand). Exit 4: no commit to ship, or the PR call fails. Exit 5: the quick CI
is red, or a check of GATES (`[ci] gates` of `agent.toml`) during the wait for the merge: it prints the failed steps and tests;
fix them, commit and run it again.
After a green quick CI it reads the PR until Automerge merged it, up to the same time limit (#5584): in 3 of 9
takeovers of 100 merged PRs on 2026-11-01, main moved during the CI wait, the merge of Automerge found a conflict 0 to 2
minutes after the green CI, and the run had reported and stopped. Exit 6: the PR has a merge conflict (also at the
push): run `python3 framework/tools/merge_main.py --push N`, then `ship_pr.py N --ci`.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claim  # noqa: E402
import dashboard  # noqa: E402
import merge_main  # noqa: E402
from agent_config import CONFIG  # noqa: E402

push = merge_main.push
QUICK = "quick"                                     # the check of ci.yml that Automerge waits for
GATES = tuple(CONFIG.get("ci", {}).get("gates", ()))   # `[ci] gates` of agent.toml: the other checks of ci.yml
#                         that Automerge needs green (#221; none: only `quick`). Red after a green quick CI, the
#                         wait for the merge ended at the time limit with "Automerge merges it", and a cold run took
#                         the PR over (7 of 10 red CI runs and 5 of 8 takeovers in 100 PRs, process review 2026-11-02)
WAIT = 9          # minutes: the quick CI of a PR took 6.2 (median) and 7.2 (p90) minutes on 2026-10-30 (#4784)
POLL = 20         # seconds
DATA = ("data/", "game/data/", "tools/mcdata/")      # data files: a change there needs no test (owner, 2026-10-29)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def data_only_tests(changed):
    """The test files of a change that else changes only data files and docs, or []. Such a test checks the content of
    the data: a change of the data must not make a test fail (owner, 2026-10-29, #4242)."""
    tests = [f for f in changed if f.startswith(("tests/", "framework/tests/"))]
    rest = [f for f in changed if not f.startswith(("tests/", "framework/tests/")) and not f.endswith(".md")]
    return tests if tests and rest and all(f.startswith(DATA) for f in rest) else []


DATA_TESTS = ("tests/test_data_files.py", "tests/test_data_format.py", "tests/test_data_checks.py")
DATA_CHECKS = "tests/data_checks/"                     # the form check of each data file (#4778): no test_*.py


LINT = CONFIG.get("commands", {}).get("lint") or "ruff check ."


def lint():
    """The lint command of the project (`[commands] lint` of agent.toml), also with `--tested`: it takes seconds, and
    with only `ruff` a run pushed a Biome error of a TypeScript change: red CI, a stalled PR and a takeover (#69)."""
    r = subprocess.run(LINT, shell=True, capture_output=True, text=True)
    if r.returncode:
        print((r.stdout + r.stderr)[-3000:])
        return False
    return True


def checks():
    """The test files of the branch and of its changed modules (more than `MAX_TESTS`: only the branch's).
    Never the full fast suite: the quick CI runs it on each push (owner, #4187). True when all pass."""
    changed = git("diff", "--name-only", f"origin/{CONFIG['branch']}...HEAD").stdout.split()
    tests = {f: open(f, encoding="utf-8").read() for f in glob.glob("tests/test_*.py") + glob.glob("framework/tests/test_*.py")}
    run = merge_main.test_files(changed, changed, tests)[0]
    if any(f.endswith(".jsonl") or f.startswith(DATA_CHECKS) for f in changed):   # no import finds their tests (#4614)
        run = sorted(set(run) | {f for f in DATA_TESTS if f in tests})
    if not run:
        print("no test file of the branch: the quick CI runs the fast suite")
        return True
    par = ["-n", "auto"] if len(run) > 8 else []           # a few files start faster without xdist (verify)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", *par, *run], capture_output=True, text=True)
    print("\n".join((r.stdout + r.stderr).strip().splitlines()[-15:]))
    return r.returncode == 0


def body_with_ticket(text, number, part=False):
    """The PR body with `Closes #N`: Automerge takes the first closing word as the ticket (#984). part: `Part of #N`,
    no closing word: the ticket stays open (a check ticket that waits for its bug tickets, #3324)."""
    if part:
        return text if f"Part of #{number}" in text else f"{text.rstrip()}\n\nPart of #{number}\n"
    return text if claim.closes(number).search(claim.prose(text)) else f"{text.rstrip()}\n\nCloses #{number}\n"


CLOSER = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+#(\d+)\b", re.I)


def closer(text, number, part=False):
    """The first line that closes a ticket other than #number, or with `part` any ticket, else None. One ticket per
    PR: GitHub closes each ticket that a merged PR names after a closing word (#472: the body of PR #471 said
    "PR #468 closed #453" and closed #453; #470: "does not close #453" in a `--part` PR), also in code: no
    `claim.prose` here (#474: PR #473 closed #453 from a code span)."""
    for line in text.splitlines():
        if any(part or int(m.group(1)) != number for m in CLOSER.finditer(line)):
            return line.strip()
    return None


def state(number, tries=6, wait=5):
    """`mergeable_state` of PR `number`; GitHub computes it after a push (`unknown` or None for some seconds)."""
    for _ in range(tries):
        s = dashboard.api(f"pulls/{number}").get("mergeable_state")
        if s not in (None, "unknown"):
            return s
        time.sleep(wait)
    return "unknown"


def quick(sha, name=QUICK):
    """The check run `name` (default `quick`) of commit `sha`, or None (not queued yet)."""
    return next(iter(dashboard.api(f"commits/{sha}/check-runs?check_name={name}").get("check_runs", [])), None)


def red_gate(sha):
    """The first failed check run of GATES of commit `sha`, or None (green, still running or not queued)."""
    return next((c for c in (quick(sha, name) for name in GATES)
                 if c and c["status"] == "completed" and c["conclusion"] == "failure"), None)


def failures(check):
    """The failed steps and the failure annotations of a check run (ci.yml writes the failed tests as annotations: the
    cloud blocks the host of the job logs, #4784)."""
    steps = [s["name"] for s in dashboard.api(f"actions/jobs/{check['id']}").get("steps", []) if s["conclusion"] == "failure"]
    notes = [a["message"] for a in dashboard.api(f"check-runs/{check['id']}/annotations")
             if a["annotation_level"] == "failure" and not a["message"].startswith("Process completed with exit code")]
    return [f"failed step: {s}" for s in steps] + notes


def wait_ci(sha, deadline, get=quick, now=time.monotonic, sleep=time.sleep):
    """The completed check run `quick` of `sha`, or None at the deadline (a `now` time)."""
    while True:
        c = get(sha)
        if c and c["status"] == "completed":
            return c
        if now() + POLL > deadline:
            return None
        sleep(POLL)


def conflict(number):
    return f"merge conflict: run `python3 framework/tools/merge_main.py --push {number}`, then `ship_pr.py {number} --ci`"


def wait_merge(pr, deadline, get=None, now=time.monotonic, sleep=time.sleep, red=lambda: None):
    """After the green quick CI: "merged", "dirty" (Automerge found a conflict: main moved during the CI, #5584),
    "hold" (Automerge waits for the PR's own checks), "red" (`red()` gives a failed check of GATES: Automerge never
    merges it) or "open" at the deadline. At least one read."""
    get = get or (lambda n: dashboard.api(f"pulls/{n}"))
    while True:
        p = get(pr)
        if p.get("merged"):
            return "merged"
        if p.get("mergeable_state") == "dirty":
            return "dirty"
        if "hold" in {lb.get("name") for lb in p.get("labels", [])}:
            return "hold"
        if red():
            return "red"
        if now() + POLL > deadline:
            return "open"
        sleep(POLL)


def ci(number, sha, deadline, pr=None):
    """Wait for the quick CI of `sha` and print its result; then wait for the merge of PR `pr`. Exit 5 when the CI is
    red (the quick CI, or a check of GATES during the wait for the merge), 6 when the PR has a merge conflict, else 0."""
    print(f"waiting for the quick CI of {sha[:8]} (at most until {WAIT} minutes after the start)", flush=True)
    c = wait_ci(sha, deadline)
    if c is None:
        print(f"the quick CI still runs: run `python3 framework/tools/ship_pr.py {number} --ci` to wait again")
        return 0
    print(f"quick CI {c['conclusion']}")
    if c["conclusion"] != "failure":
        if pr is None:
            return 0
        gate = []                                   # the failed check of GATES, when one turns red
        m = wait_merge(pr, deadline, red=lambda: gate.append(red_gate(sha)) or gate[-1])
        if m == "red":
            c = gate[-1]
            print(f"{c.get('name') or 'gate'} CI failure")
        else:
            print(conflict(number) if m == "dirty" else f"PR #{pr}: {m}" + (": Automerge merges it" + (f" when the "
                  f"{', '.join(GATES)} check is green too" if GATES else "") if m == "open" else ""))
            return 6 if m == "dirty" else 0
    print("\n".join(failures(c)) or "no failed step: open the run of the check")
    print(f"fix it, commit and run `python3 framework/tools/ship_pr.py {number}` again (autopilot step 6.9)")
    return 5


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("number", type=int, help="the ticket")
    ap.add_argument("--message", help="a file with the commit message: commit the staged files first")
    ap.add_argument("--title", help="the PR title (a new PR)")
    ap.add_argument("--body", help="a file with the PR body (a new PR)")
    ap.add_argument("--tested", action="store_true", help="the checks of `verify` level 1 passed on this tree")
    ap.add_argument("--hold", action="store_true", help="add the label `hold`: Automerge waits for the PR's own checks")
    ap.add_argument("--part", action="store_true", help="`Part of #N` in place of `Closes #N` in a new PR: the ticket "
                    "stays open (a check ticket that waits for its bug tickets, autopilot `owner.md`)")
    ap.add_argument("--ci", action="store_true", help="only wait for the quick CI of the open PR of the branch")
    ap.add_argument("--pr-branch", help="with --ci: the branch of the PR (a takeover pushes to the PR of another run "
                    "from its session branch, #5014)")
    ap.add_argument("--wait", type=float, default=WAIT, help=f"minutes after the start to wait for the quick CI "
                    f"(default {WAIT}; 0: do not wait)")
    a = ap.parse_args(argv)
    deadline = time.monotonic() + a.wait * 60
    branch = git("branch", "--show-current").stdout.strip()
    for f in (a.message, a.body):
        if f and (line := closer(open(f, encoding="utf-8").read(), a.number, a.part)):
            print(f"{f} closes a ticket in the line {line!r}: reword it (GitHub closes each ticket after a closing "
                  f"word; only `{'Part of' if a.part else 'Closes'} #{a.number}`, #472)")
            return 2
    if a.ci:
        owner, head = CONFIG["repo"].split("/")[0], a.pr_branch or branch
        pr = next(iter(dashboard.api(f"pulls?head={owner}:{head}&state=open")), None)
        if pr is None:
            print(f"no open PR of {head}" + ("" if a.pr_branch else ": a takeover gives --pr-branch B"))
            return 4
        return ci(a.number, pr["head"]["sha"], deadline, pr.get("number"))
    if a.message:
        c = git("commit", "-q", "-F", a.message)
        if c.returncode:
            print(f"commit failed: {(c.stdout + c.stderr).strip()}")
            return 4
    if not int(git("rev-list", "--count", f"origin/{CONFIG['branch']}..HEAD").stdout.strip() or 0):
        print(f"no commit on {branch} that is not on {CONFIG['branch']}: nothing to ship")
        return 4
    owner = CONFIG["repo"].split("/")[0]
    pr = next(iter(dashboard.api(f"pulls?head={owner}:{branch}&state=open")), None)
    changed = git("diff", "--name-only", f"origin/{CONFIG['branch']}...HEAD").stdout.split()
    if bad := data_only_tests(changed):                  # also with --tested
        print(f"a change of data files only must not add or change tests: remove {' '.join(bad)} (docs/extend.md)")
        return 2
    if not lint() or (not a.tested and not checks()):
        return 2
    if not push(a.number):
        return 3
    if pr is None:
        if not (a.title and a.body):
            print(f"pushed, but no PR: give --title and --body (a new PR of #{a.number})")
            return 4
        try:
            pr = dashboard.api("pulls", "POST", {"title": a.title, "head": branch, "base": CONFIG["branch"],
                                                  "body": body_with_ticket(open(a.body, encoding="utf-8").read(), a.number, a.part)})
        except Exception as e:
            print(f"pushed, but the PR call failed ({e}): open the PR with `gh api` (`github.md`)")
            return 4
        print(f"opened PR #{pr['number']}: {pr.get('html_url', '')}")
    else:
        print(f"pushed to PR #{pr['number']}")
    if a.hold:                                  # at once: the quick CI of the PR must not merge it first
        dashboard.api(f"issues/{pr['number']}/labels", "POST", {"labels": ["hold"]})
        print(f"label hold on PR #{pr['number']}")
    s = state(pr["number"])
    print(f"mergeable_state {s}" + (f": {conflict(a.number)}" if s == "dirty" else ""))
    if s == "dirty":                                # a conflict: GitHub starts no CI on the PR
        return 6
    if a.wait <= 0:
        return 0
    return ci(a.number, git("rev-parse", "HEAD").stdout.strip(), deadline, pr["number"])


if __name__ == "__main__":
    sys.exit(main())
