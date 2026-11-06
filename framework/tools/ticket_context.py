"""Print the code places of a ticket in one call (#3829): its title and body, then for each name in backticks of the
body (dashboard.names): the def block of a function, the path, line count and docstring of a file, the test names of a
test file. A run reads them once after the claim, in place of a chain of sed, cat and grep calls."""
import argparse
import ast
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def files():
    """The paths of the files in git and the new files that git does not ignore, relative to ROOT."""
    return subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True).stdout.split()


def defs(name, paths, lines=80):
    """The def blocks of function name in the .py files of paths: "path:line" and the block, up to the next line with
    no indent (a top-level def or class), at most `lines` lines."""
    out = []
    for p in (p for p in paths if p.endswith(".py")):
        src = open(os.path.join(ROOT, p), encoding="utf-8", errors="replace").read().splitlines()
        for i, s in enumerate(src):
            if re.match(rf"\s*(async\s+)?def {re.escape(name)}\(", s):
                indent = len(s) - len(s.lstrip())
                end = next((j for j in range(i + 1, len(src)) if src[j].strip()
                            and len(src[j]) - len(src[j].lstrip()) <= indent and not src[j].lstrip().startswith(")")),
                           len(src))
                out.append(f"{p}:{i + 1}\n" + "\n".join(src[i:min(end, i + lines)]))
    return out


def describe(name, paths, raw=()):
    """The lines of one file name: its path and line count, its docstring, and its tests for a test file. raw: the
    paths of the body with this base name (`.claude/skills/autopilot/SKILL.md`): only the files that end with one."""
    out, raw = [], [r for r in raw if "/" in r]
    for p in (p for p in paths if p.rsplit("/", 1)[-1] == name
              and (not raw or any(p == r or p.endswith("/" + r) for r in raw))):
        text = open(os.path.join(ROOT, p), encoding="utf-8", errors="replace").read()
        out.append(f"{p}: {text.count(chr(10))} lines")
        if p.endswith(".py"):
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            if doc := ast.get_docstring(tree):
                out.append(doc)
            if name.startswith("test_"):
                out.append("tests: " + ", ".join(n.name for n in tree.body if isinstance(n, ast.FunctionDef)
                                                 and n.name.startswith("test_")))
    return out


def context(body, lines=80, paths=None):
    """The text of the code places that body names."""
    paths = files() if paths is None else paths
    out, tokens = [], [t.split()[0] for t in re.findall(r"`([^`\n]+)`", body or "") if t.split()]
    for n in sorted(dashboard.names(body)):
        found = defs(n[:-2], paths, lines) if n.endswith("()") else describe(
            n, paths, [t for t in tokens if t.rsplit("/", 1)[-1] == n])
        out += found or [f"not found: {n}"]
    return "\n\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("number", type=int)
    ap.add_argument("--lines", type=int, default=80, help="the most lines of one def block")
    a = ap.parse_args()
    i = dashboard.api(f"issues/{a.number}")
    print(f"#{a.number} {i['title']}\n{i.get('body') or ''}\n\n{context(i.get('body'), a.lines)}")


if __name__ == "__main__":
    main()
