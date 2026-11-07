"""Merge `origin/main` into the branch in one call: fetch, merge, solve, commit, check, and push (owner, 2026-10-28).

Merges of main by hand were 28 % of the calls and 25 % of the cost of four runs on 2026-10-28: about 6 calls per
merge, an own resolver script each time, and the full fast suite after each merge. This tool does it in one call.

    python3 framework/tools/merge_main.py             # merge origin/main, solve the add-add hunks, commit, ruff and the tests
    python3 framework/tools/merge_main.py --push N    # the same, then `claim.py N --guard` and the push of the branch
    python3 framework/tools/merge_main.py --push N --pr-branch B   # a takeover from the session branch: guard and push to B
    python3 framework/tools/merge_main.py --no-test   # no ruff and no tests (a merge before the code of the ticket)

Steps: copy main's merge driver of `game/data/*.jsonl` into the git directory (#2096), `git fetch origin main`,
`git merge` with `merge.conflictStyle diff3`. `framework/tools/unconflict.py` solves each hunk in which both sides only add
lines, also in a file that has a real conflict. When no conflict is left, the tool commits the merge, runs
`ruff check .` and the test files of the merge (`test_files`: the test files of the branch and the test files that
import a conflicted module; the quick CI runs the full suite), and with `--push N` pushes after the guard.
Exit 0: merged (and checked, pushed). Exit 1: a real conflict stays: the tool prints each hunk; solve it, `git add`
the file, and run the tool again (it then commits, checks and pushes; a merge that the agent committed by hand is
checked too, #5040). Exit 2: ruff or a test fails.
Exit 3: the guard or the push fails (do not push by hand).
"""
import argparse
import glob
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unconflict  # noqa: E402

MAX_TESTS = 30      # more test files import a conflicted module (the main module): run only the branch's, CI runs the rest
HUNK_LINES = 40     # lines of each conflict hunk in the output
IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+)?import\s+\(?([\w., ]+)", re.M)


def git(*args, check=False):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


def modules(path):
    """The names under which a test can import the module of `path` (`game/scenario.py`: game.scenario, scenario)."""
    if not path.endswith(".py") or path.startswith(("tests/", "framework/tests/")):
        return set()
    m = path[:-3].replace("/", ".")
    return {m, m.rsplit(".", 1)[-1]}


def imports(text):
    """The module names that a file imports: `import a, b`, `from a import b` (a and a.b)."""
    out = set()
    for base, names in IMPORT.findall(text):
        for n in (x.split(" as ")[0].strip() for x in names.split(",")):
            out |= {base, f"{base}.{n}"} if base else {n}
    return out


def test_files(conflicted, changed, tests):
    """(test files to run, test files left to CI). `tests`: {path: text} of the test files of the repository."""
    own = sorted({f for f in changed + conflicted if f in tests})
    mods = set().union(*map(modules, conflicted)) if conflicted else set()
    users = sorted(f for f, text in tests.items() if f not in own and mods & imports(text))
    return (own + users, []) if len(own) + len(users) <= MAX_TESTS else (own, users)


def show(path, left):
    """The text of the hunks that stay in `path`: `left` = [(line, reason)] of `unconflict.solve_some`."""
    lines = open(path, encoding="utf-8").read().splitlines()
    out = []
    for at, why in left:
        end = next((i for i in range(at - 1, len(lines)) if lines[i].startswith(">>>>>>> ")), len(lines) - 1)
        part = lines[at - 1:end + 1]
        cut = part[:HUNK_LINES] + ([f"... ({len(part) - HUNK_LINES} more lines)"] if len(part) > HUNK_LINES else [])
        out.append(f"{path}:{at}: {why}\n" + "\n".join(cut))
    return "\n".join(out)


def solve(files):
    """Solve what `unconflict` can in each conflicted file. Returns the text of the hunks that stay ("" when none)."""
    shown = []
    for f in files:
        text = open(f, encoding="utf-8").read()
        if "<<<<<<< " not in text:
            shown.append(f"{f}: no conflict markers (deleted on one side, or a binary file): solve it with git")
            continue
        new, left = unconflict.solve_some(text)
        why = "" if left else unconflict.check(f, new) or unconflict.hides(f, new) or unconflict.stray(f, new)
        if why:
            shown.append(f"{f}: {why}")
            continue
        open(f, "w", encoding="utf-8").write(new)
        if left:
            shown.append(show(f, left))
        else:
            git("add", f, check=True)
            print(f"{f}: solved (both sides only add lines)")
    return "\n".join(shown)


def check(conflicted, base):
    """ruff and the tests of the merge. Returns True when both pass."""
    r = subprocess.run(["ruff", "check", "."], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-3000:])
        return False
    changed = git("diff", "--name-only", f"{base}...HEAD").stdout.split()
    tests = {f: open(f, encoding="utf-8").read() for f in glob.glob("tests/test_*.py") + glob.glob("framework/tests/test_*.py")}
    run, rest = test_files(conflicted, changed, tests)
    if rest:
        print(f"{len(rest)} more test files import the conflicted modules: the quick CI runs them")
    if not run:
        print("no test file to run: the quick CI runs the fast suite")
        return True
    cmd = [sys.executable, "-m", "pytest", "-q", *(["-n", "auto"] if len(run) > 8 else []), *run]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("\n".join((r.stdout + r.stderr).strip().splitlines()[-15:]))
    return r.returncode == 0


def push(number, pr_branch=None):
    """`claim.py N --guard`, then the push of the branch (once more after a merge of the remote branch). True: pushed.
    pr_branch: the branch of a PR that the run took over from its session branch (`overlap.md`, #3678)."""
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claim.py")
    g = subprocess.run([sys.executable, tool, str(number), "--guard", *(["--pr-branch", pr_branch] if pr_branch else [])],
                       capture_output=True, text=True)
    if g.returncode:
        print(f"guard failed, no push: {(g.stdout + g.stderr).strip()}")
        return False
    branch = pr_branch or git("branch", "--show-current").stdout.strip()
    for _ in range(2):
        r = git("push", "origin", f"HEAD:refs/heads/{branch}")
        if r.returncode == 0:
            print(f"pushed -> {branch}")
            return True
        if "fetch first" not in r.stderr and "non-fast-forward" not in r.stderr:
            break
        git("fetch", "-q", "origin", branch)            # the workflow Unconflict merged main into it (#2120)
        if git("merge", "-q", "--no-edit", f"origin/{branch}").returncode:
            git("merge", "--abort")
            break
    print(f"push failed: {r.stderr.strip()}")
    return False


def both_changed(base, left, right):
    """The files that both sides of a merge changed from their base."""
    return sorted(set(git("diff", "--name-only", base, left).stdout.split())
                  & set(git("diff", "--name-only", base, right).stdout.split()))


def hand_merge(pr_branch=None):
    """The files that both sides changed when HEAD is a merge commit that is not on the push branch yet (the agent
    committed the merge by hand after exit 1), else None (#5040: such a merge got no ruff and no tests)."""
    if len(git("log", "-1", "--format=%P").stdout.split()) != 2:
        return None
    target = pr_branch or git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if git("merge-base", "--is-ancestor", "HEAD", f"origin/{target}").returncode == 0:
        return None                                             # pushed already
    base = git("merge-base", "HEAD^1", "HEAD^2").stdout.strip()
    return both_changed(base, "HEAD^1", "HEAD^2")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--push", type=int, metavar="N", help="after the merge and the checks: guard ticket N and push")
    ap.add_argument("--pr-branch", metavar="B", help="with --push: push to branch B, the PR that the run took over (#3678)")
    ap.add_argument("--no-test", action="store_true", help="no ruff and no tests")
    a = ap.parse_args(argv)
    gd = git("rev-parse", "--git-common-dir", check=True).stdout.strip()
    driver = git("show", "origin/main:framework/tools/merge_jsonl.py").stdout
    if driver:
        open(os.path.join(gd, "merge_jsonl.py"), "w").write(driver)
    if not git("config", "--get", "merge.jsonl.driver").stdout.strip():
        print("warning: no merge.jsonl.driver: run .claude/hooks/session-start.sh (game/data lines can double)")
    if git("rev-parse", "-q", "--verify", "MERGE_HEAD").returncode:          # no merge in progress: start one
        git("fetch", "-q", "origin", "main", check=True)
        before = git("rev-parse", "HEAD").stdout.strip()
        m = git("-c", "merge.conflictStyle=diff3", "merge", "--no-edit", "origin/main")
        conflicted = git("diff", "--name-only", "--diff-filter=U").stdout.split()
        if m.returncode and not conflicted:
            print(m.stdout + m.stderr)
            return 1
        left = solve(conflicted)
        if left:
            print(left)
            print("A real conflict stays: solve the hunks above, `git add` the files, and run this tool again "
                  "(it commits the merge).")
            return 1
        if conflicted:
            git("commit", "-q", "--no-edit", check=True)
        merged = git("rev-parse", "HEAD").stdout.strip() != before
        print(f"merged origin/main ({len(conflicted)} conflicted files solved)" if merged else "already up to date")
        if not merged and (conflicted := hand_merge(a.pr_branch)) is not None:   # committed by hand: check it (#5040)
            merged = True
            print("merge committed by hand: check it")
    else:                                                       # the agent solved the rest: finish the merge
        conflicted = git("diff", "--name-only", "--diff-filter=U").stdout.split()
        if conflicted:
            print("still conflicted: " + " ".join(conflicted))
            return 1
        base = git("merge-base", "HEAD", "MERGE_HEAD").stdout.strip()   # the files that both sides changed
        conflicted = both_changed(base, "HEAD", "MERGE_HEAD")
        git("commit", "-q", "--no-edit", check=True)
        merged = True
        print("merge committed")
    if merged and not a.no_test and not check(conflicted, "origin/main"):
        return 2
    if a.push is not None and not push(a.push, a.pr_branch):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
