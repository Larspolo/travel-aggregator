#!/bin/bash
# PreToolUse hook: block the shell commands that cost runs time (docs/LEARNINGS.md). Exit 2 blocks the command and
# shows the message to the agent. Each rule names its way around.
exec python3 -c '
import json, os, re, shlex, subprocess, sys
data = json.load(sys.stdin)
raw = (data.get("tool_input") or {}).get("command") or ""
cwd = data.get("cwd") or "."
def git(*args):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True).stdout.strip()
def words(seg):
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()
def in_merge():
    merge = git("rev-parse", "--git-path", "MERGE_HEAD")
    return bool(merge) and os.path.exists(os.path.join(cwd, merge))
def why():
    for m in re.finditer(r"(?<!<)<<-?\s*(\w+)[^\n]*\n(.*?)\n\s*\1\b", raw, flags=re.S):     # an unquoted tag
        if "`" in m.group(2):
            return (f"<<{m.group(1)} runs each `name` of the heredoc body as a command (#345). Quote the tag: "
                    f"<<\x27{m.group(1)}\x27.")
    cmd = re.sub(r"(<<-?\s*([\x27\x22]?)(\w+)\2[^\n]*)\n.*?\n\s*\3\b", r"\1", raw, flags=re.S)  # heredoc bodies are text
    for m in re.finditer(r"\bcat\s*>\s*([^\s|;&<>()]+)\s*<<", cmd):           # ">|" is the way around
        f = m.group(1).strip("\x27\x22")
        if "$" not in f and git("ls-files", "--", f):
            return (f"cat > {f} writes over a file that git tracks (#1945). Use the Edit tool, or write >| {f} "
                    "if you really mean to replace it.")
    assigned = set(re.findall(r"(?:^|[\s;&|(])(?:export\s+)?(\w+)=", cmd)) | set(re.findall(r"\bfor\s+(\w+)\s+in\b", cmd))
    for m in re.finditer(r"(?<![<>&\d])>>?\s*\x22?\$\{?(\w+)\}?/", cmd):
        v = m.group(1)
        if v != "TMPDIR" and not os.environ.get(v) and v not in assigned:
            return (f"${v} is empty here, so the redirect writes to /... (#2032, #865). Write the full path, "
                    "or set the variable on its own line (not in an & list).")
    bare = re.sub(r"\x27[^\x27]*\x27|\x22(?:\\.|[^\x22\\])*\x22", lambda m: m.group(0).replace("&", " "), cmd)   # a quoted & is text (#5226)
    parts = re.split(r"(?<![&>|<])&(?![&>])", bare)                      # the lists that a single & puts in the background
    for i, part in enumerate(parts[:-1]):
        bg = re.split(r"[;\n]", part)[-1]                                     # & takes only the list after the last ;
        for v in set(re.findall(r"(?:^|[\s(])(?:export\s+)?(\w+)=", bg)):
            later = "&".join(parts[i + 1:])
            if re.search(r"\$\{?" + v + r"\b", later) and not re.search(r"(?:^|[\s;(])" + v + "=", later):
                return (f"{v}= is set in a list that & puts in a background subshell, so the commands after the & "
                        f"see the old ${v} (#865). Set {v} on its own line first.")
    for seg in re.split(r"&&|\|\||[;\n]", cmd):
        w = words(seg)
        for tool in ("pkill", "pgrep"):
            if tool in w and (tool == "pkill" or "kill" in w[w.index(tool):]):
                rest = w[w.index(tool) + 1:]
                if any(a.startswith("-") and "f" in a.lstrip("-") and not a.startswith("--") for a in rest):
                    pat = next((a for a in rest if not a.startswith("-")), "")
                    if "[" not in pat:
                        return (f"{tool} -f \"{pat}\" also matches the shell that runs this command, and kills it "
                                f"(#1213). Write a bracket in the pattern, for example \"[{pat[:1]}]{pat[1:]}\".")
        at = next((i for i, x in enumerate(w) if x == "pytest" and (i == 0 or w[i - 1] == "-m")), None)
        safe = "xargs" in w[:at or 0] and {"-r", "--no-run-if-empty"} & set(w[:at or 0])     # no run with no file
        if at is not None and not safe and not os.environ.get("AOE2MC_FULL_SUITE"):
            args, sub = [], 0
            for x in w[at + 1:]:
                if not sub and (x in ("|", "&") or re.match(r"\d?>", x)):
                    break
                sub += x.count("$(")
                if not sub:
                    args.append(x)                                     # the words of a $(...) are no file names
                sub = max(0, sub - x.count(")"))
            some = any(re.search(r"\.py|::|/.", x) and "$" not in x and x.rstrip("/") != "tests" for x in args)  # $F: empty?
            if not some and not {"-m", "-k", "--lf", "--last-failed", "--co", "--collect-only", "-h", "--help"} & set(args):
                return ("python3 -m pytest with no test file runs the full fast suite: never do it, the quick CI runs it "
                        "on each push (owner, #4187). Name the test files of the change: python3 -m pytest tests/test_a.py. A $VAR or "
                        "$(...) can be empty (#4244): grep -l X tests/*.py | xargs -r python3 -m pytest -q.")
        if "gh" in w and any(a in ("-f", "--raw-field") and b.startswith("body=@") for a, b in zip(w, w[1:])):
            return ("-f sends the text @file literally: the issue body is only a path (#4250). "
                    "Use -F body=@file.md.")
        if w[:1] == ["gh"] and any(a in ("--body", "-b") and b.startswith("@") or a.startswith("--body=@")
                             for a, b in zip(w, w[1:] + [""])):
            return ("gh --body sends the text @file literally: the issue body is only a path (#4458). "
                    "Use --body-file file.md.")
        if re.match(r"\s*\(?\s*git\s+(?:-C\s+\S+\s+)?stash\b", seg):
            sub = (w[w.index("stash") + 1:] or ["push"])[0]
            if sub not in ("list", "show") and in_merge():
                return ("git stash in an unfinished merge drops MERGE_HEAD: the next commit is no merge commit "
                        "(#2281). Finish or abort the merge first, or test main in a git worktree.")
        if re.match(r"\s*\(?\s*git\s+(?:-C\s+\S+\s+)?(?:checkout|restore)\b", seg) and "--ours" in w and in_merge():
            return ("git checkout --ours FILE takes your whole file and drops the hunks of main that merged with no "
                    "conflict (#2627). Resolve only the marker hunks, then read git diff origin/main --stat.")
    return None
msg = why()
if msg:
    print("Blocked by .claude/hooks/guard-shell.sh: " + msg, file=sys.stderr)
    sys.exit(2)
'
