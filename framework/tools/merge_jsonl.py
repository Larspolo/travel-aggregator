#!/usr/bin/env python3
"""Git merge driver for the data tables `game/data/*.jsonl`: merge the lines by their key "name" (#2004).

`merge=union` keeps the old and the new version of a line that one side changed, and `table.load()` then stops
("more than one line for X", #1890, #1934). This driver takes, for each name, the side that changed it. A line that
both sides changed merges key by key, also in nested objects, and a list of unique names merges name by name when
each side only adds or only removes names (#2064: two new units in the "missing" lists of almost all lines of
civs.jsonl). A key that both sides changed to different values, or a list that one side changed in place (the pair
"upgrade"), is a conflict: the file gets conflict markers around the two lines and the exit code is 1.
The line order comes from the side that moved lines (some tables are choice lists in file order); two different moves
are a conflict around the whole files (#3065).

    python3 framework/tools/merge_jsonl.py BASE OURS THEIRS     # git: merge.jsonl.driver "python3 framework/tools/merge_jsonl.py %O %A %B"

The result goes into OURS. A line without a JSON object with "name" is keyed by its text (a union without copies).
A file that does not parse falls back to the text merge of `git merge-file`.
"""
import json
import subprocess
import sys

GONE = object()                                          # a key that one version does not have


class Conflict(Exception):
    """Both sides changed one value to different values."""


def rows(path):
    """{key: line} of the file `path`, in file order."""
    with open(path, encoding="utf-8") as f:
        return rows_of(f)


def rows_of(lines):
    """{key: line} of the text lines `lines`, in their order."""
    out = {}
    for s in lines:
        if not s.strip():
            continue
        s = s.rstrip("\n") + "\n"
        o = json.loads(s)
        out[o["name"] if isinstance(o, dict) and "name" in o else s] = s
    return out


def order(ours, theirs):
    """The keys of `ours` in their order, and the new keys of `theirs` after their neighbour above in `theirs` and
    after the new keys of `ours` there (as `merge=union`). A new key with no neighbour below goes to the end: after a
    move on the side of `ours`, its old neighbour above is not the last key any more (#3065)."""
    out, mine, seq = list(ours), set(ours), list(theirs)
    for i, k in enumerate(seq):
        if k in mine:
            continue
        if not any(j in out for j in seq[i + 1:]):
            out.append(k)
            continue
        above = [j for j in seq[:i] if j in out]
        at = out.index(above[-1]) + 1 if above else 0
        while at < len(out) and out[at] not in theirs:
            at += 1
        out.insert(at, k)
    return out


def names(v):
    """True when `v` is a list of unique names (as "missing", "classes"), not a pair or a list of numbers."""
    return isinstance(v, list) and all(isinstance(n, str) for n in v) and len(set(v)) == len(v)


def value(o, a, b):
    """The merged value of the base `o`, ours `a` and theirs `b` (GONE: not there). Conflict when no merge is sure."""
    if a == b or b == o:
        return a
    if a == o:
        return b                                         # changed (or deleted) only on their side
    if all(isinstance(v, dict) for v in (o, a, b)):      # an object: key by key
        out = {k: value(o.get(k, GONE), a.get(k, GONE), b.get(k, GONE)) for k in order(a, b)}
        return {k: v for k, v in out.items() if v is not GONE}
    if all(names(v) for v in (o, a, b)):
        new = [(set(v) - set(o), set(o) - set(v)) for v in (a, b)]   # (added, removed) of each side
        if not any(add and rm for add, rm in new):       # no side changed a name in place (the pair "upgrade")
            out = [n for n in order(a, b) if n not in new[0][1] | new[1][1]]
            return sorted(out) if a == sorted(a) and b == sorted(b) else out
    raise Conflict


def common(side, base, ours, theirs):
    """The keys of all three versions in the order of `side`."""
    return [k for k in side if k in base and k in ours and k in theirs]


def merge(base, ours, theirs):
    """(lines, conflicts): the merged lines in the order of `ours`, the new lines of `theirs` after their
    neighbour above in `theirs` and after the new lines of `ours` there (as `merge=union`). When only `theirs` moved
    lines, the order of `theirs` with the new lines of `ours`; two different moves are one conflict (#3065)."""
    old, a, b = (common(x, base, ours, theirs) for x in (base, ours, theirs))
    if a != old and b != old and a != b:                 # both sides moved lines in different ways
        return ["<<<<<<< ours\n", *ours.values(), "=======\n", *theirs.values(), ">>>>>>> theirs\n"], 1
    lines, conflicts = [], 0
    for k in order(theirs, ours) if a == old != b else order(ours, theirs):
        o, a, b = base.get(k), ours.get(k), theirs.get(k)
        if a == b or b == o:
            pick = a
        elif a == o:
            pick = b                                     # changed (or deleted) only on their side
        else:                                            # changed on both sides: key by key (#2064)
            try:
                pick = json.dumps(value(*(json.loads(s) if s else GONE for s in (o, a, b))), ensure_ascii=False) + "\n"
            except Conflict:
                conflicts += 1
                lines += ["<<<<<<< ours\n", a or "", "=======\n", b or "", ">>>>>>> theirs\n"]
                continue
        if pick is not None:
            lines.append(pick)
    return lines, conflicts


def main(argv):
    base, ours, theirs = argv[1:4]
    try:
        lines, conflicts = merge(rows(base), rows(ours), rows(theirs))
    except (ValueError, KeyError, TypeError):            # not one JSON object per line: the plain text merge
        r = subprocess.run(["git", "merge-file", "-L", "ours", "-L", "base", "-L", "theirs", ours, base, theirs])
        return 1 if r.returncode else 0
    with open(ours, "w", encoding="utf-8") as f:
        f.writelines(lines)
    if conflicts:
        print(f"{ours}: {conflicts} name(s) changed on both sides", file=sys.stderr)
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
