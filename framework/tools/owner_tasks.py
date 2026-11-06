"""The tickets that wait for the owner (#983): the open `needs-human` tickets that are not muted, with their kind
and question. The skill `human` (a local session of the owner, `/human`) lists them and prepares the chosen one.

    python3 framework/tools/owner_tasks.py             # decision tickets first, then the oldest first
    python3 framework/tools/owner_tasks.py --show N    # the section "## For the owner" of ticket N (else its last question)
    python3 framework/tools/owner_tasks.py --json      # the list as JSON
    python3 framework/tools/owner_tasks.py --wait      # wait for a new ticket (#1025): exit 0 and print it, exit 1 after --hours
    python3 framework/tools/owner_tasks.py --plan      # the plan of one session (#1674): close now, replay, play game, no game
    python3 framework/tools/owner_tasks.py --sample    # the closed check tickets for a sample check of the owner (#1708)

Kinds: `decision` ("Decide: ..."), `play` (a play test of the program: "Check ...", or a body
with the `play` text of `agent.toml`, section `[owner_tasks]`), `setting` (the environment, the
scheduled task or GitHub), `outside` (a step outside the cloud), `close` (close an issue that the auto mode did not let
the agent close, #862), `question` (all others). A last comment that asks for a close wins over all, then a line
"Kind: <kind>" in the section "## For the owner" wins over the title. Token: GITHUB_TOKEN, else `gh api`. Python
standard library only.
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_config import CONFIG  # noqa: E402
from dashboard import MUTED, api, labels, pages, question  # noqa: E402

KINDS = ["decision", "play", "setting", "outside", "close", "question"]
OUTSIDE = re.compile(r"\b(own computer|second repository|local session|on your computer|bootstrap)\b", re.I)
CLOSE = re.compile(r"\b(please close|close (this|it) by hand)\b", re.I)
SETTING = re.compile(r"\b(environment|setup script|network|variable|scheduled task|GitHub setting|secret|"
                     r"interaction limit|branch protection)\b", re.I)
PROJECT = CONFIG.get("owner_tasks", {})    # the words of the project: a play test, a recorded game
PLAY = PROJECT.get("play")
REPLAY = re.compile(r"\breplay|^\W*Watch:" + "".join(f"|{r}" for r in [PROJECT.get("replay")] if r), re.I | re.M)
PLAN = ("close now", "replay", "play game", "no game")       # the groups of --plan, in the order of a session
SAMPLE = "owner-sample"     # a check ticket that the agent closed on its evidence; the owner checks a sample (#1708)


def for_owner(body):
    """The text of the section "## For the owner" of an issue body, or ""."""
    m = re.search(r"^## For the owner[ \t]*\n(.*?)(?=^## |\Z)", body or "", re.M | re.S)
    return m.group(1).strip() if m else ""


def kind(issue, comments=()):
    """The kind of a needs-human ticket: "close" when the last comment asks for a close (the work is done, the auto
    mode denied the close, #862), else the "Kind:" line of "## For the owner", else from the title, the body and the
    last agent request. A check ticket ("Check ...") ends with a close request: the title must not win (#1674)."""
    comments = list(comments)
    if comments and CLOSE.search(comments[-1].get("body") or ""):
        return "close"
    m = re.search(r"^Kind:\s*(\w+)", for_owner(issue.get("body")), re.M | re.I)
    if m and m.group(1).lower() in KINDS:
        return m.group(1).lower()
    title = issue.get("title") or ""
    if title.startswith("Decide:"):
        return "decision"
    if re.match(r"(Check|Play|Test)\b", title) or PLAY and PLAY in (issue.get("body") or ""):
        return "play"
    if SETTING.search(title):
        return "setting"
    if OUTSIDE.search(title):
        return "outside"
    if CLOSE.search(show(issue, comments)):
        return "close"
    return "question"


def tasks(issues, comments):
    """The open needs-human tickets that are not muted, decision tickets first, then by number (the oldest first).
    comments: {issue number: comments}."""
    wait = [i for i in issues if "pull_request" not in i and "needs-human" in labels(i) and MUTED not in labels(i)
            and i.get("state", "open") == "open"]
    out = [{"number": i["number"], "title": i["title"], "kind": kind(i, comments.get(i["number"], [])), "epic": "epic" in labels(i),
            "question": ask(i, comments.get(i["number"], [])), "url": i.get("html_url", ""),
            "replay": bool(REPLAY.search(f"{i['title']}\n{i.get('body') or ''}"))} for i in wait]
    return sorted(out, key=lambda t: (t["kind"] != "decision", t["number"]))


def plan(found):
    """{group of PLAN: tasks} for one session of the `human` skill (#1674): closes first, then one replay with
    game/watch.py, one play game with game/play_guide.py, then the tickets without a game. The skill moves a ticket
    that asks for times, values or texts to agent work (#1159)."""
    got = {g: [] for g in PLAN}
    for t in found:
        if t["kind"] == "close":
            got["close now"].append(t)
        elif t["kind"] == "play":
            got["replay" if t["replay"] else "play game"].append(t)
        else:
            got["no game"].append(t)
    return got


def ask(issue, comments):
    """One line: the last question of the comments, else the first line of what the owner must do."""
    q = question(comments)
    if q != "see ticket":
        return q
    line = next((x.strip() for x in show(issue, comments).splitlines() if x.strip()), "see ticket")
    line = re.sub(r"^@\S+\s*", "", line)
    return line if len(line) <= 120 else line[:117] + "..."


def show(issue, comments):
    """What the owner must do for one ticket: its section "## For the owner", else the last agent comment."""
    text = for_owner(issue.get("body"))
    if text:
        return text
    last = next((c for c in reversed(comments) if "@" in (c.get("body") or "")), comments[-1] if comments else None)
    return (last.get("body") or "").split("\n---\n")[0].strip() if last else (issue.get("body") or "").strip()


def waiting():
    """The open needs-human tickets that are not muted (one GitHub request for up to 100)."""
    return {i["number"]: i for i in pages("issues?state=open&labels=needs-human")
            if "pull_request" not in i and MUTED not in labels(i)}


def wait(every=300, hours=12.0, clock=time.monotonic, sleep=time.sleep):
    """Wait for a needs-human ticket that was not open at the start (#1025). The skill `human` runs it in the
    background: the session uses no model turn while it waits. Returns the task of the new ticket, or None after
    `hours`. Only the new ticket's comments are read."""
    seen, end = set(waiting()), clock() + hours * 3600
    while clock() < end:
        sleep(every)
        now = waiting()
        new = sorted(set(now) - seen)
        if new:
            i = now[new[0]]
            return tasks([i], {i["number"]: pages(f"issues/{i['number']}/comments")})[0]
    return None


def sample(issues):
    """The closed check tickets with the label `owner-sample`, the oldest close first: the batch of a sample check."""
    return sorted((i for i in issues if "pull_request" not in i and SAMPLE in labels(i)), key=lambda i: i["closed_at"] or "")


def line(t):
    return f"#{t['number']} [{t['kind']}{', epic' * t['epic']}] {t['title']} – {t['question']}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--show", type=int, metavar="N", help="print what the owner must do for ticket N")
    ap.add_argument("--json", action="store_true", help="print the list as JSON")
    ap.add_argument("--plan", action="store_true", help="print the plan of one session: close now, replay, play game, no game")
    ap.add_argument("--sample", action="store_true", help="print the closed check tickets for a sample check (#1708)")
    ap.add_argument("--wait", action="store_true", help="wait for a new ticket: exit 0 and print it, else exit 1")
    ap.add_argument("--every", type=float, default=300, help="seconds between two checks of --wait (default 300)")
    ap.add_argument("--hours", type=float, default=12, help="hours that --wait waits at most (default 12)")
    a = ap.parse_args(argv)
    if a.wait:
        t = wait(a.every, a.hours)
        print(line(t) if t else f"No new ticket in {a.hours:g} hours.")
        return 0 if t else 1
    if a.sample:
        found = sample(pages(f"issues?state=closed&labels={SAMPLE}"))
        for i in found:
            print(f"#{i['number']} {i['title']} (closed {i['closed_at'][:10]})")
        if not found:
            print("No closed check waits for a sample check.")
        return 0
    if a.show:
        issue = api(f"issues/{a.show}")
        comments = pages(f"issues/{a.show}/comments")
        print(f"#{issue['number']} {issue['title']} ({kind(issue, comments)})\n")
        print(show(issue, comments))
        return 0
    issues = pages("issues?state=open&labels=needs-human")
    comments = {i["number"]: pages(f"issues/{i['number']}/comments") for i in issues if MUTED not in labels(i)}
    found = tasks(issues, comments)
    if a.json:
        print(json.dumps(plan(found) if a.plan else found, indent=1))
        return 0
    if a.plan:
        for g, ts in plan(found).items():
            print(f"{g} ({len(ts)}):" + "".join(f"\n  {line(t)}" for t in ts))
        return 0
    for t in found:
        print(line(t))
    if not found:
        print("No ticket waits for the owner.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
