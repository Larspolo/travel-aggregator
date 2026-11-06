"""A generic file uses only generic files (#5607): each framework tool, test module or Claude Code hook that a
generic file names or imports is in framework/files.txt, so a bootstrap copy has it."""
import os
import re

import bootstrap

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = re.compile(r"(?:framework/tools/\w+\.py|framework/tests/\w+\.py|\.claude/hooks/[\w-]+\.sh)")
IMPORT = re.compile(r"^\s*(?:from|import)\s+(\w+)", re.M)


def used(path, text):
    """The repository files that the text of a generic file names or imports (a module of framework/tools or of the
    folder of the file)."""
    names = set(PATH.findall(text))
    if path.endswith(".py"):
        for mod in IMPORT.findall(text):
            for folder in ("framework/tools", os.path.dirname(path)):
                names.add(f"{folder}/{mod}.py")
    return {n for n in names if os.path.isfile(os.path.join(ROOT, n))}


def missing(generic):
    gen = set(generic)
    out = {}
    for p in sorted(gen):
        if p == "framework/files.txt" or not os.path.isfile(os.path.join(ROOT, p)):
            continue
        with open(os.path.join(ROOT, p), errors="ignore") as f:
            for n in used(p, f.read()) - gen:
                out.setdefault(n, []).append(p)
    return out


def test_each_used_file_is_generic():
    assert missing(bootstrap.generic(open(bootstrap.FILES).read())) == {}, "add these files to framework/files.txt (or remove the use)"


def test_a_missing_tool_is_found():
    got = missing(["framework/tools/ship_pr.py", ".claude/settings.json"])
    assert any(n.startswith("framework/tools/") for n in got)     # ship_pr.py imports other framework tools
    assert any(n.startswith(".claude/hooks/") for n in got)       # settings.json runs the hooks
