"""Make and set up the GitHub repository of a new project with `gh` (the `new-project` skill).

    python3 framework/tools/new_repo.py DIR --repo OWNER/NAME [--description TEXT] [--private] [--dry-run]
    python3 framework/tools/new_repo.py DIR --repo OWNER/NAME --secrets    # asks for each secret, no echo
    python3 framework/tools/new_repo.py DIR --repo OWNER/NAME --start      # starts the pacer once
    python3 framework/tools/new_repo.py DIR --repo OWNER/NAME --check      # one line per setup step: OK or MISSING

DIR is the output of `framework/tools/bootstrap.py`, with the specific files filled. The default run makes the first
commit, makes the repository (public: free Actions minutes), pushes, and does the GitHub steps of
`framework/docs/SYSTEM.md` ("Setup steps of the owner", step 1) and step 3: the workflow permissions, the ruleset
`Protect main`, the labels and the status issue. Each step that is done already (the repository exists, a label exists)
is ok, so a second run repairs a first run that stopped. `--secrets` sets the secrets of `pacer.yml`: the value of an
environment variable of the same name, else a prompt with no echo. A value never goes to the output.
"""
import argparse
import getpass
import json
import os
import subprocess
import sys

import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bootstrap  # noqa: E402

APP = "https://github.com/apps/claude/installations/select_target"   # the owner installs the Claude GitHub app here

# The ruleset of step 1: no force push and no delete of the default branch.
RULESET = {"name": "Protect main", "target": "branch", "enforcement": "active",
           "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
           "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}]}


def lanes(target):
    """The lanes of `weights` in `[pacing]` of the new project (steering/system/system.toml): each has a task."""
    try:
        with open(os.path.join(target, "steering", "system", "system.toml"), "rb") as f:
            return sorted(tomllib.load(f).get("pacing", {}).get("weights", {}))
    except (OSError, tomllib.TOMLDecodeError):
        return []


def secret_names(target):
    """The secrets of pacer.yml (SYSTEM.md, step 5): the quota token, and the fire URL and token of each task."""
    return ["CLAUDE_CODE_OAUTH_TOKEN"] + [f"PACER_{k}_{t.upper()}" for t in ["main"] + lanes(target) for k in ("URL", "TOKEN")]


def noreply_calls(target):
    """The calls that set the local email of DIR to the GitHub noreply address: GitHub refuses a push whose commit has a
    private email (#4796). No call when the email is a noreply address already."""
    email = subprocess.run(["git", "-C", target, "config", "user.email"], capture_output=True, text=True).stdout.strip()
    if email.endswith("@users.noreply.github.com"):
        return []
    ident = (gh_out(["api", "user", "--jq", ".id,.login"]) or "").split()
    if len(ident) != 2:
        return []
    address = f"{ident[0]}+{ident[1]}@users.noreply.github.com"
    print(f"local git identity of {target}: {ident[1]} <{address}> (the private email is refused by GitHub)")
    return [(["git", "-C", target, "config", "user.email", address], None),
            (["git", "-C", target, "config", "user.name", ident[1]], None)]


def git_calls(target, branch):
    """The calls that make the first commit in DIR (no call when DIR has a commit already)."""
    if subprocess.run(["git", "-C", target, "rev-parse", "--verify", "-q", "HEAD"], capture_output=True).returncode == 0:
        return []
    return [(["git", "-C", target, "init", "-q", "-b", branch], None), *noreply_calls(target),
            (["git", "-C", target, "add", "-A"], None), (["git", "-C", target, "commit", "-q", "-m", "Set up the agent system"], None)]


def ruleset_names(repo):
    """The names of the rulesets of the repository, one per line of the output; [] when there is none or no repository yet."""
    try:
        r = subprocess.run(["gh", "api", f"repos/{repo}/rulesets", "--jq", ".[].name"], capture_output=True, text=True)
    except OSError:
        return []
    return r.stdout.splitlines() if r.returncode == 0 else []


def repo_calls(target, repo, branch, description="", private=False, exists=False):
    """(command, stdin) of each step of the default run, in order."""
    make = [] if exists else [(["gh", "repo", "create", repo, "--private" if private else "--public", "--description",
                                description, "--source", target, "--remote", "origin", "--push"], None)]
    push = [(["git", "-C", target, "push", "-u", "origin", branch], None)] if exists else []
    settings = [(["gh", "api", f"repos/{repo}", "-X", "PATCH", "-F", "has_issues=true", "-F", "allow_squash_merge=true"], None),
                (["gh", "api", f"repos/{repo}/actions/permissions/workflow", "-X", "PUT",
                  "-f", "default_workflow_permissions=write"], None)]
    if RULESET["name"] not in ruleset_names(repo):             # a second run: the ruleset exists, GitHub answers 422 with another text
        settings.append((["gh", "api", f"repos/{repo}/rulesets", "-X", "POST", "--input", "-"], json.dumps(RULESET)))
    labels = open(os.path.join(target, ".github", "labels.txt")).read()
    return make + push + settings + [(c, None) for c in bootstrap.github_calls(repo, labels)]


def ok(call, r):
    """A step that is done already counts as done: a label or a ruleset that exists (422)."""
    text = r.stdout + r.stderr
    return r.returncode == 0 or ("/labels" in " ".join(call) and "already_exists" in text) or \
        ("/rulesets" in " ".join(call) and "already exists" in text.lower())


def status_exists(repo):
    """True when the repository has an issue with the status label (a second run makes no second status issue)."""
    r = subprocess.run(["gh", "api", f"repos/{repo}/issues?labels={bootstrap.CONFIG['status']['label']}&state=all",
                        "--jq", "length"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() not in ("", "0")


def run(calls, dry):
    """Run each call; print one line per call. Returns the number of failed calls."""
    failed = 0
    for call, stdin in calls:
        if dry:
            print("would run:", " ".join(call[:4]))
            continue
        r = subprocess.run(call, input=stdin, capture_output=True, text=True)
        good = ok(call, r)
        failed += not good
        print(("ok   " if good else "FAIL ") + " ".join(call[:4]) + ("" if good else f": {(r.stderr or r.stdout).strip()[-300:]}"))
    return failed


def set_secrets(repo, names, env, ask=getpass.getpass):
    """Set each secret from env, else from a prompt with no echo; an empty answer skips it. Returns the set names."""
    done = []
    for name in names:
        value = env.get(name) or ask(f"{name} (empty: skip): ")
        if not value:
            continue
        r = subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value, capture_output=True, text=True)
        print(("ok   " if r.returncode == 0 else "FAIL ") + f"secret {name}" + ("" if r.returncode == 0 else f": {r.stderr.strip()}"))
        done += [name] * (r.returncode == 0)
    return done


def trigger(target):
    """The ID of the scheduled task "NAME autopilot" in `[pacing]` of steering/system/system.toml ("" when not set)."""
    try:
        with open(os.path.join(target, "steering", "system", "system.toml"), "rb") as f:
            return tomllib.load(f).get("pacing", {}).get("trigger", "")
    except (OSError, tomllib.TOMLDecodeError):
        return ""


def checks(target, repo, gh):
    """(name, ok, hint) of each setup step that GitHub or DIR can show. gh(args) gives the stdout of a `gh` call, or
    None when it fails. The app, the cloud environment and the tasks show only in the Claude app: the owner says them."""
    secrets = set((gh(["secret", "list", "--repo", repo, "--json", "name", "--jq", ".[].name"]) or "").split())
    rules = gh(["api", f"repos/{repo}/rulesets", "--jq", ".[].name"]) or ""
    perms = gh(["api", f"repos/{repo}/actions/permissions/workflow", "--jq", ".default_workflow_permissions"]) or ""
    runs = gh(["run", "list", "--repo", repo, "--workflow", "pacer.yml", "--limit", "1", "--json", "status", "--jq", ".[].status"])
    return [("repository", gh(["repo", "view", repo, "--json", "name"]) is not None, "run this tool with no option"),
            ("workflow permissions", perms.strip() == "write", "run this tool with no option"),
            ("ruleset Protect main", RULESET["name"] in rules.splitlines(), "run this tool with no option"),
            ("status issue", status_exists(repo), "run this tool with no option"),
            *((f"secret {n}", n in secrets, "run this tool with --secrets") for n in secret_names(target)),
            ("trigger in steering/system/system.toml", bool(trigger(target)), "write the ID of the task \"NAME autopilot\""),
            ("a run of the workflow Pacer", bool((runs or "").strip()), "run this tool with --start")]


def gh_out(args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("target")
    ap.add_argument("--repo", required=True, help="OWNER/NAME of the new repository")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--description", default="")
    ap.add_argument("--private", action="store_true", help="a private repository (Actions minutes are not free)")
    ap.add_argument("--dry-run", action="store_true", help="print the calls, change nothing")
    ap.add_argument("--secrets", action="store_true", help="set the secrets of pacer.yml")
    ap.add_argument("--start", action="store_true", help="start the workflow Pacer once")
    ap.add_argument("--check", action="store_true", help="show which setup steps are done")
    a = ap.parse_args(argv)
    if a.repo.count("/") != 1:
        ap.error("--repo must be OWNER/NAME")
    if a.check:
        rows = checks(a.target, a.repo, gh_out)
        for name, good, hint in rows:
            print(f"OK       {name}" if good else f"MISSING  {name}: {hint}")
        return 0 if all(good for _, good, _ in rows) else 1
    if a.secrets:
        names = secret_names(a.target)
        if a.dry_run:
            print("\n".join(names))
            return 0
        done = set_secrets(a.repo, names, os.environ)
        print(f"{len(done)} of {len(names)} secrets set.")
        return 0 if len(done) == len(names) else 1
    if a.start:
        return run([(["gh", "workflow", "run", "pacer.yml", "--repo", a.repo, "--ref", a.branch], None)], a.dry_run)
    exists = subprocess.run(["gh", "repo", "view", a.repo], capture_output=True).returncode == 0
    calls = repo_calls(a.target, a.repo, a.branch, a.description, a.private, exists)
    if exists and status_exists(a.repo):
        calls = calls[:-1]                                  # the status issue is the last call
    failed = run(git_calls(a.target, a.branch), a.dry_run) + run(calls, a.dry_run)
    name = a.repo.split("/")[1]
    print(f"\n{failed} steps failed." if failed else "\nThe repository is ready.")
    print(f"Steps that only the owner can do: install the Claude GitHub app on {a.repo} ({APP}), make the cloud environment "
          f"and the scheduled tasks of \"{name} autopilot\" (framework/docs/SYSTEM.md, steps 2, 4, 7 and 8), then run this "
          f"tool with --secrets and --start.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
