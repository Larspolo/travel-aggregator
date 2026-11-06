#!/usr/bin/env python3
"""Make several tickets in one call: the issues, their labels and their sub-issue links (owner, 2026-11-06).

A refill made each ticket with its own MCP call (6 to 10 `issue_write` calls in a deep run). Each call reads the full
context again (about 5k eq each at 50k context), so one call for all tickets saves most of that.

    python3 framework/tools/new_tickets.py FILE.md            # make the tickets, print "#N title" for each
    python3 framework/tools/new_tickets.py FILE.md --dry-run  # print what it would make

FILE.md: one block per ticket. A line `# <title>` starts a block (a body uses only `##` and smaller headings). Then
optional head lines, then the body (the `ticket` skill form):

    # Make the trip list page
    labels: P2, feature, size:S, lane:haiku
    parent: 94

    ## Goal
    ...
    Depends on: #new1

`parent: E` links the ticket as a sub-issue of epic E. `#newK` (in the body and in `parent:`) is the number of the
K-th ticket of the same file, so a chain or a new epic with its sub-issues fits in one file: make the earlier ticket
first. A body (not `parent:`) may name a later ticket of the file (for example an epic's `## Owner checks` names its
sub-issues): the tool makes that ticket, then patches the body once with the number. Each body needs the sections `## Goal` and `## Acceptance criteria` (the `ticket` skill; the hook
`guard-body.sh` checks the same for the MCP tool): the tool checks all tickets before it makes one. A failure stops the
tool; the lines of the tickets that it made are already printed.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402

NEW = re.compile(r"#new(\d+)\b")
PARENT_NEW = re.compile(r"new(\d+)$")
HEAD = re.compile(r"^(labels|parent):\s*(.*)$")


def parse(text):
    """[{"title", "labels", "parent", "body"}] of the blocks of FILE.md."""
    out = []
    for line in text.splitlines():
        if line.startswith("# "):
            out.append({"title": line[2:].strip(), "labels": [], "parent": None, "body": [], "head": True})
            continue
        if not out:
            if line.strip():
                raise ValueError(f"text before the first '# <title>' line: {line!r}")
            continue
        t, m = out[-1], HEAD.match(line)
        if t["head"] and m:
            if m[1] == "labels":
                t["labels"] = [x.strip() for x in m[2].split(",") if x.strip()]
            else:
                t["parent"] = m[2].strip().lstrip("#")
            continue
        if t["head"] and not line.strip():
            continue
        t["head"] = False
        t["body"].append(line)
    for t in out:
        del t["head"]
        t["body"] = "\n".join(t["body"]).strip() + "\n"
        if not t["title"]:
            raise ValueError("a ticket has no title")
        if not ("## Goal" in t["body"] and "## Acceptance criteria" in t["body"]):
            raise ValueError(f"{t['title']!r}: a new issue needs the sections ## Goal and ## Acceptance criteria")
    return out


def check(tickets):
    """Raise ValueError for a `#newK` that names no other ticket of the file, or a `parent:` that is not earlier."""
    total = len(tickets)
    for k, t in enumerate(tickets, 1):
        for m in NEW.finditer(t["body"]):
            i = int(m[1])
            if not 1 <= i <= total or i == k:
                raise ValueError(f"#new{i} in ticket {k}: only another ticket of the file (1 to {total}) can be named")
        p = PARENT_NEW.match(t["parent"] or "")
        if p and not 1 <= int(p[1]) < k:
            raise ValueError(f"parent: #new{p[1]} in ticket {k}: only an earlier ticket of the file can be the parent")


def resolve(text, made, k, later=False):
    """Replace each `#newK` with the number of the K-th ticket made. With `later`, a `#newK` of a later ticket stays."""
    def one(m):
        i = int(m[1])
        if later and i >= k:
            return m[0]
        return f"#{made[i - 1]['number']}"
    return NEW.sub(one, text)


def make(tickets, api=dashboard.api, out=print):
    """Make the tickets in order; returns the made issues. A body that names a later ticket is patched once at the end."""
    check(tickets)
    made, patch = [], []
    for k, t in enumerate(tickets, 1):
        body = resolve(t["body"], made, k, later=True)
        parent = resolve(f"#{t['parent']}", made, k).lstrip("#") if t["parent"] else None
        issue = api("issues", "POST", {"title": t["title"], "body": body, "labels": t["labels"]})
        made.append(issue)
        if NEW.search(body):
            patch.append(k)
        if parent:
            api(f"issues/{int(parent)}/sub_issues", "POST", {"sub_issue_id": issue["id"]})
        out(f"#{issue['number']} {t['title']}" + (f" (sub-issue of #{parent})" if parent else ""))
    for k in patch:
        api(f"issues/{made[k - 1]['number']}", "PATCH", {"body": resolve(tickets[k - 1]["body"], made, k)})
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", help="the tickets: one block per ticket, a line '# <title>' starts each")
    ap.add_argument("--dry-run", action="store_true", help="print the tickets, make nothing")
    a = ap.parse_args(argv)
    with open(a.file) as f:
        try:
            tickets = parse(f.read())
            check(tickets)                              # before any print or call: a bad reference stops all
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    if a.dry_run:
        for k, t in enumerate(tickets, 1):
            print(f"#new{k} {t['title']} · labels {', '.join(t['labels']) or '-'} · parent {t['parent'] or '-'}")
        return 0
    make(tickets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
