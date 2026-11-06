"""The push workflows that Automerge must start after its merges (#4839): a merge with GITHUB_TOKEN starts no `push`
workflow. Prints each workflow of DIR that runs on a push to main, has `workflow_dispatch`, and whose `paths` or
`paths-ignore` filter matches one of the merged files. Skips the workflows that Automerge starts after each merge.

    python3 framework/tools/push_workflows.py [--dir .github/workflows] FILE...

Reads only the `on:` block, with the standard library (no YAML dependency): inline lists and block lists."""
import argparse
import os
import re
import sys

SKIP = {"ci.yml", "claims.yml", "coverage.yml", "unconflict.yml"}   # automerge.yml starts these after each merge


def items(text):
    """The values of an inline list "[a, 'b']" or of one scalar."""
    text = text.strip()
    if text.startswith("["):
        text = text.strip("[]")
    return [v.strip().strip("'\"") for v in text.split(",") if v.strip()]


def on_block(src):
    """{event: {key: [values]}} of the `on:` block. An event with no settings has {}."""
    lines = [ln.split(" #")[0].rstrip() for ln in src.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    for i, ln in enumerate(lines):
        m = re.match(r"""^["']?(on|true)["']?:\s*(.*)$""", ln)   # YAML 1.1 reads a bare on as true
        if m:
            break
    else:
        return {}
    if m.group(2):
        return {e: {} for e in items(m.group(2))}
    events, event, ev_depth, key = {}, None, 0, None
    for ln in lines[i + 1:]:
        depth = len(ln) - len(ln.lstrip())
        if depth == 0:
            break
        s = ln.strip()
        if s.startswith("- "):
            if key:
                events[event][key] += items(s[2:])
            elif event is None:
                events[s[2:].strip()] = {}
            continue
        k, _, v = s.partition(":")
        if event is None or depth <= ev_depth:
            event, ev_depth, key = k.strip(), depth, None
            events[event] = {}
        else:
            key = k.strip()
            events[event][key] = items(v)
    return events


def glob_re(pattern):
    """A regex of a GitHub filter glob: ** matches across "/", * and ? do not."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def selected(patterns, path):
    """GitHub's rule: the last matching pattern decides, a "!" pattern excludes."""
    hit = False
    for p in patterns:
        neg = p.startswith("!")
        if glob_re(p[1:] if neg else p).match(path):
            hit = not neg
    return hit


def wanted(events, files):
    push = events.get("push")
    if push is None or "workflow_dispatch" not in events:
        return False
    if "tags" in push and "branches" not in push:
        return False                                       # a tag-only push
    if "branches" in push and not selected(push["branches"], "main"):
        return False
    if "paths" in push:
        return any(selected(push["paths"], f) for f in files)
    if "paths-ignore" in push:
        return any(not selected(push["paths-ignore"], f) for f in files)
    return True


def workflows(folder, files):
    out = []
    for name in sorted(os.listdir(folder)):
        if name.endswith((".yml", ".yaml")) and name not in SKIP:
            with open(os.path.join(folder, name)) as f:
                if wanted(on_block(f.read()), files):
                    out.append(name)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", default=".github/workflows")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    for name in workflows(a.dir, a.files) if a.files else []:
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
