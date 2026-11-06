"""Solve the merge conflicts in which both sides only add lines (#1864).

Parallel tickets add entries next to each other in the same table (`TECHS` and `UPGRADES` in `game/train.py`, the
command list of the plugin). Git then has a conflict with an empty base: nothing to choose, both sides stay.
Run it after a failed `git merge` with `merge.conflictStyle diff3` (the workflow `unconflict.yml` does). It solves
each conflicted file when all its hunks have an empty base, checks the result (Python compiles, JSON lines parse) and
`git add`s it. Exit 0: all conflicts are solved, commit the merge. Exit 1: a real conflict stays (it names it).
A table of keyed one-line entries ("KEY": ...) stays in alphabetical order (CLAUDE.md, "Code style").
A hunk in which both sides add a `def` or `class` of the same name stays a conflict: the second one hides the first (#2631).
A conflicted file with no markers (one side deletes it, the other changes it) stays a conflict (#3062).
A hunk whose base lines both sides keep is solved too: both sides that add a key before the first key of a table
change its opening line `return {"KEY": ...` (`kept`, #5860). A merge in which a nested function of one side hides a
module function of the other side stays a conflict (`hides`).
"""
import ast
import json
import re
import subprocess
import sys

KEYED = re.compile(r'^\s+"([^"]+)":')     # one entry of a table keyed by a name
DEF = re.compile(r'^\s*(?:async\s+def|def|class)\s+(\w+)')   # a function or a class (#2631)
FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
HEAD = re.compile(r'^(\s*[^\s"#][^"#]*[{[(])("[^"]+":.*)$', re.S)   # a table with its first entry on its opening line


def merge(ours, theirs):
    """The lines of one add-add hunk: both sides, keyed entries sorted. None for a key with two entries."""
    lines = ours + theirs          # no dedupe: two code blocks can each end with the same line
    keys = [KEYED.match(t) for t in lines]
    if not all(keys):
        return lines
    names = [k.group(1) for k in keys]
    if len(set(names)) < len(names):
        return None
    return sorted(lines, key=lambda t: KEYED.match(t).group(1))


def cut(lines, heads=None):
    """(lines, heads): each opening line of a keyed table (`return {"KEY": ...`) cut into its head (`return {`) and
    the first entry at the column of the next entries. heads: cut only these heads (the heads of the base)."""
    out, found = [], set()
    for t in lines:
        m = HEAD.match(t)
        if m and (heads is None or m.group(1) in heads):
            found.add(m.group(1))
            out += [m.group(1) + "\n", " " * len(m.group(1)) + m.group(2)]
        else:
            out.append(t)
    return out, found


def kept(ours, base, theirs):
    """The solved lines of a hunk in which both sides keep each base line and only add lines around it, or (None,
    reason). Both sides that add a key before the first key of a table change its opening line `return {"KEY": ...`;
    after the cut of that line (`cut`) the base lines stay on both sides (6 PRs of the XS series, #5860)."""
    b, heads = cut(base)
    o, t = cut(ours, heads)[0], cut(theirs, heads)[0]
    if any(o.count(x) != 1 or t.count(x) != 1 for x in b) or \
            any(s.index(x) > s.index(y) for s in (o, t) for x, y in zip(b, b[1:])):
        return None, "both sides change the same lines"
    out, i, j = [], 0, 0
    for x in b + [None]:                           # the added lines before each base line, and after the last one
        i2, j2 = (o.index(x), t.index(x)) if x is not None else (len(o), len(t))
        both, why = hunk(o[i:i2], [], t[j:j2])
        if both is None:
            return None, why
        out += both + [x] * (x is not None)
        i, j = i2 + 1, j2 + 1
    for k in range(len(out) - 1, -1, -1):          # join each cut head with its first entry again
        if out[k].rstrip("\n") in heads:
            if k + 1 == len(out) or not KEYED.match(out[k + 1]):
                return None, "a table head with no entry after it"
            out[k:k + 2] = [out[k].rstrip("\n") + out[k + 1].lstrip()]
    return out, ""


def hunk(ours, base, theirs):
    """The solved lines of one hunk, or (None, reason)."""
    if base is None:
        return None, "no base section: set merge.conflictStyle diff3"
    if base:
        return kept(ours, base, theirs)
    same = {m.group(1) for m in map(DEF.match, ours) if m} & {m.group(1) for m in map(DEF.match, theirs) if m}
    if same:
        return None, f"both sides define {', '.join(sorted(same))}"
    both = merge(ours, theirs)
    if both is None:
        return None, "both sides add the same key"
    return both, ""


def solve_some(text):
    """(text, left): each add-add hunk solved, each other hunk kept with its markers; left = [(line, reason)] of the
    kept hunks (the line of their `<<<<<<<` in the new text, from 1). `framework/tools/merge_main.py` solves what it can (#1864)."""
    out, left, lines, i = [], [], text.splitlines(keepends=True), 0
    while i < len(lines):
        if not lines[i].startswith("<<<<<<< "):
            out.append(lines[i])
            i += 1
            continue
        start, ours, base, theirs, part = i, [], None, [], "ours"
        i += 1
        while i < len(lines) and not lines[i].startswith(">>>>>>> "):
            t = lines[i]
            if t.startswith("||||||| "):
                part, base = "base", []
            elif t.rstrip("\r\n") == "=======":
                part = "theirs"
            else:
                (ours if part == "ours" else base if part == "base" else theirs).append(t)
            i += 1
        i += 1
        both, why = hunk(ours, base, theirs)
        if both is None:
            left.append((len(out) + 1, why))
            out += lines[start:i]
        else:
            out += both
    return "".join(out), left


def solve(text):
    """The text with each add-add hunk solved, or (None, reason)."""
    if not any(t.startswith("<<<<<<< ") for t in text.splitlines()):    # git keeps the changed side as it is
        return None, "no conflict markers: a modify/delete conflict, solve it with git"
    text, left = solve_some(text)
    return (None, left[0][1]) if left else (text, "")


def check(path, text):
    """An error text when the solved file is not valid, else ""."""
    try:
        if path.endswith(".py"):
            compile(text, path, "exec")
        elif path.endswith(".jsonl"):
            [json.loads(t) for t in text.splitlines() if t.strip()]
        elif path.endswith(".json"):
            json.loads(text)
    except (SyntaxError, ValueError) as e:
        return f"not valid after the merge: {e}"
    return ""


def hidden(text):
    """The names of the module functions and classes that a nested function of the same name hides."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    top = {n.name for n in tree.body if isinstance(n, (*FUNCS, ast.ClassDef))}
    return {d.name for n in tree.body if isinstance(n, FUNCS) for d in ast.walk(n)
            if d is not n and isinstance(d, FUNCS) and d.name in top}


def hides(path, text):
    """An error text when the merge makes a nested function hide a module function: one side adds `def civ_name` in
    `host()`, the other a module `def civ_name` that `host()` calls (#5860). Compiles and passes ruff, but is wrong."""
    if not path.endswith(".py"):
        return ""
    sides = [subprocess.run(["git", "show", f":{n}:{path}"], capture_output=True, text=True).stdout for n in (2, 3)]
    new = hidden(text) - hidden(sides[0]) - hidden(sides[1])
    return f"a nested function hides the module function {', '.join(sorted(new))}: rename one" if new else ""


def main():
    files = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], capture_output=True, text=True,
                           check=True).stdout.split()
    solved = {}
    for f in files:
        try:
            text, why = solve(open(f, encoding="utf-8").read())
        except (OSError, UnicodeDecodeError) as e:     # a rename/delete leaves no file, a binary file is no text
            text, why = None, f"cannot read: {e}"
        why = why or check(f, text) or hides(f, text)
        if why:
            print(f"{f}: {why}")
            return 1
        solved[f] = text
    for f, text in solved.items():        # write only when all files are solved
        open(f, "w", encoding="utf-8").write(text)
        subprocess.run(["git", "add", f], check=True)
        print(f"{f}: solved (both sides only add lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
