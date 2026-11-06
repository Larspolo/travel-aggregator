"""Set up the agent system in a new repository (#906).

    python3 framework/tools/bootstrap.py TARGET_DIR --repo OWNER/NAME [--branch main] [--github]

Copies the generic files of `framework/files.txt` (#4192; the specific files: the table "Generic and specific files"
in `framework/docs/SYSTEM.md`), with the repository, the owner login and the project name of the new project in place of travel-aggregator. Writes
`agent.toml` with the new values and placeholder commands, and short starts of the specific files that the generic
files need (`STUBS`: the files of `framework/template/` that the owner fills, #4196). Prints the setup steps of the owner (`framework/docs/SYSTEM.md`) and the specific files that stay to do.
`--github` also makes the labels of `.github/labels.txt` and the status issue with `gh api` (REST).
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_config import CONFIG, ROOT  # noqa: E402

SYSTEM = os.path.join(ROOT, CONFIG["docs"]["system"])
FILES = os.path.join(ROOT, "framework", "files.txt")
ROW = re.compile(r"^\| `([^`]+)` \| (generic|specific|steering) \|", re.M)

TEMPLATE = os.path.join(ROOT, "framework", "template")   # the files that the owner fills (#4196)


# The prompt of the scheduled task: only the command, so git controls the rules (`.claude/skills/scheduled/SKILL.md`,
# owner, 2026-10-29). Text after it would become a part of the skill argument. The lane tasks: `/scheduled max lane L`.
PROMPT = "/scheduled max\n"


def label_result(call, r):
    """The output line of one `gh api` call of --github: a label that exists (422 already_exists, for example `bug`
    of each new repository) is ok."""
    ok = r.returncode == 0 or ("/labels" in call[2] and "already_exists" in r.stdout + r.stderr)
    return ("ok  " if ok else "FAIL ") + " ".join(call[:3]) + ("" if ok else f": {r.stderr.strip()}")


CACHE = {".ruff_cache", "__pycache__", ".pytest_cache"}   # tool caches in the template: no part of it


def template(root=TEMPLATE):
    """{path: text} of the files of framework/template: the specific files that the generic files need, with comments
    that say what to fill (#4196)."""
    return {os.path.relpath(os.path.join(d, f), root): open(os.path.join(d, f)).read()
            for d, _, fs in sorted(os.walk(root)) if not CACHE & set(d.split(os.sep)) for f in sorted(fs)}


def fill(text, values):
    """The text with each {key} of values replaced; other braces (TOML tables, shell) stay."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m[1], m[0])), text)


STUBS = template()


def table(text):
    """(path, kind) of each row of the table "Generic and specific files" of framework/docs/SYSTEM.md."""
    return ROW.findall(text.split("## Generic and specific files", 1)[1])


def generic(text):
    """The generic files of framework/files.txt: one path or glob per line, # starts a comment line."""
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    return [p for line in lines for p in (sorted(os.path.relpath(f, ROOT) for f in glob.glob(os.path.join(ROOT, line)))
                                          if "*" in line else [line])]


def rows():
    """(path, kind) of each file of the system: the generic files of framework/files.txt, then the specific rows of
    the table "Generic and specific files" of framework/docs/SYSTEM.md."""
    return [(p, "generic") for p in generic(open(FILES).read())] + table(open(SYSTEM).read())


def section(text, title):
    """The section "## title" of a Markdown text, up to the next "## " heading."""
    m = re.search(rf"^## {re.escape(title)}\n.*?(?=^## |\Z)", text, re.M | re.S)
    return m.group(0).rstrip() + "\n" if m else ""


def rename(text, repo, name, owner):
    """The text with the repository, the owner login and the project name of the new project. One pass, the longest
    old value first: a new value that contains an old one is not replaced again (#953)."""
    new = {CONFIG["repo"]: repo, CONFIG["owner"]: owner, CONFIG["repo"].split("/")[1]: name}
    return re.sub("|".join(map(re.escape, sorted(new, key=len, reverse=True))), lambda m: new[m[0]], text)


def github_calls(repo, labels, title="Agent status"):
    """The `gh api` arguments that make the labels and the status issue of the new repository."""
    calls = [["gh", "api", f"repos/{repo}/labels", "-f", f"name={n}", "-f", f"color={c}", "-f", f"description={d}"]
             for n, c, d in (line.split("|", 2) for line in labels.splitlines() if line.strip() and not line.startswith("#"))]
    body = '<!-- agent-state: {"last_run": "1970-01-01T00:00:00Z", "runs": 0} -->\n## Agent status\n\n### Process changes\n'
    return calls + [["gh", "api", f"repos/{repo}/issues", "-f", f"title={title}", "-f", f"body={body}",
                     "-f", f"labels[]={CONFIG['status']['label']}"]]


def bootstrap(target, repo, branch="main"):
    """Write the files into target. Returns (copied, written, todo): the generic files, the stubs, the specific files
    that the owner or a first run must write."""
    owner, name = repo.split("/")
    files = rows()
    values = {"repo": repo, "owner": owner, "name": name, "branch": branch, **CONFIG["commands"],
              "generic": "@framework/CLAUDE.md"}      # the generic rules: the copy of framework/CLAUDE.md (#4193)
    copied, written = [], []
    for path, kind in files:
        if kind != "generic":
            continue
        src, dst = os.path.join(ROOT, path), os.path.join(target, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            text = open(src).read()
        except UnicodeDecodeError:
            shutil.copy2(src, dst)
        else:
            with open(dst, "w") as f:
                f.write(rename(text, repo, name, owner))
            shutil.copymode(src, dst)
        copied.append(path)
    for path, text in STUBS.items():
        dst = os.path.join(target, path)
        os.makedirs(os.path.dirname(dst) or target, exist_ok=True)
        with open(dst, "w") as f:
            f.write(rename(fill(text, values), repo, name, owner) if not path.endswith(".toml") else fill(text, values))
        if path.endswith(".sh"):
            os.chmod(dst, 0o755)
        written.append(path)
    todo = [p for p, k in files if k != "generic" and p not in STUBS]
    return copied, written, todo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("target")
    ap.add_argument("--repo", required=True, help="OWNER/NAME of the new repository")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--github", action="store_true", help="also make the labels and the status issue (gh api)")
    a = ap.parse_args(argv)
    if a.repo.count("/") != 1:
        ap.error("--repo must be OWNER/NAME")
    copied, written, todo = bootstrap(a.target, a.repo, a.branch)
    owner, name = a.repo.split("/")
    print(f"Copied {len(copied)} generic files and wrote {len(written)} starts ({', '.join(written)}) to {a.target}.")
    print("\nWrite these specific files for the project (see framework/docs/SYSTEM.md, \"Generic and specific files\"):")
    print("".join(f"- {p}\n" for p in todo))
    print(rename(section(open(SYSTEM).read(), "Setup steps of the owner"), a.repo, name, owner))
    print(f"The prompt of the scheduled task \"{name} autopilot\" (step 4), to paste as it is:\n")
    print(PROMPT.format(repo=a.repo, owner=owner, name=name, branch=a.branch))
    if a.github:
        labels = open(os.path.join(ROOT, ".github/labels.txt")).read()
        for call in github_calls(a.repo, labels):
            print(label_result(call, subprocess.run(call, capture_output=True, text=True)))


if __name__ == "__main__":
    main()
