"""Compare the features of steering/project/ROADMAP.md with their epics (#1681).

    python3 framework/tools/roadmap_status.py

One line for each `[ ]` feature whose epic is closed as completed ("mark done: key (#E)"), each feature with no epic
("no epic: key") and each `[x]` feature with no epic number on its line ("no number: key"). An epic names its feature
with the line "Roadmap: `key`". The roadmap review (`roadmap` skill) uses it.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEATURE = re.compile(r"^\s*- \[([ xX])\] `([^`]+)`(.*)$")
KEY = re.compile(r"^Roadmap:\s*`([^`]+)`", re.M)


def features(text):
    """[(key, done, rest of the line)] of the roadmap text."""
    return [(m[2], m[1] != " ", m[3]) for m in map(FEATURE.match, text.splitlines()) if m]


def epic_keys(epics):
    """{key: [epics]} by the line "Roadmap: `key`" of the epic bodies."""
    out = {}
    for e in epics:
        for k in KEY.findall(e.get("body") or ""):
            out.setdefault(k, []).append(e)
    return out


def status(text, epics):
    by, lines = epic_keys(epics), []
    for key, done, rest in features(text):
        mine = by.get(key, [])
        if not mine:
            lines.append(f"no epic: {key}")
        if done:
            if not re.search(r"#\d+", rest):
                lines.append(f"no number: {key}")
            continue
        closed = [e for e in mine if e.get("state") == "closed" and e.get("state_reason") == "completed"]
        if closed and not any(e.get("state") == "open" for e in mine):
            lines.append(f"mark done: {key} (#{closed[-1]['number']})")
    return lines


def main():
    import dashboard
    epics = [i for i in dashboard.pages("issues?labels=epic&state=all", 20) if "pull_request" not in i]
    with open(os.path.join(ROOT, "steering/project/ROADMAP.md"), encoding="utf-8") as f:
        text = f.read()
    for line in status(text, epics):
        print(line)


if __name__ == "__main__":
    main()
