"""The tokens of this run and their sinks: one data source to find the bottleneck of the system (owner, 2026-10-27).

Claude Code writes each session to `~/.claude/projects/<cwd with - for />/<session>.jsonl` (subagents in
`<session>/subagents/*.jsonl`). Each API call has a `usage` record. This tool adds them and finds the tool results
that cost the most: a result stays in the context, so each later call reads it again from the cache.

    python3 framework/tools/tokens.py               # the Tokens: line of the newest session (autopilot step 8)
    python3 framework/tools/tokens.py --top 15      # the 15 largest sinks, one per line
    python3 framework/tools/tokens.py FILE.jsonl    # another transcript
    python3 framework/tools/tokens.py --verify      # the minutes and repeats of each check command (#1704)
    python3 framework/tools/tokens.py --phases      # the measured phase minutes of each claimed ticket (`report.py` uses them)
    python3 framework/tools/tokens.py --run-line    # the Run: line of the run report: who, when, the model, the eq per phase
    python3 framework/tools/tokens.py --queued      # exit 0: a brief of the pacer waits as the next turn (`scheduled` step 0)

The unit is "eq": input-token equivalents with the API price ratios (input 1, cache write 1.25 for 5 minutes and 2 for
1 hour, cache read 0.1, output 5). The subscription quota is not public, but it follows the cost of the calls.
A sink costs its tokens (about 4 characters each) written once to the cache, then read by each later call of its chain.
Sink `base`: the system prompt, the tools, CLAUDE.md and LEARNINGS, which each call reads again. The `Tokens:` line
gives its 4 largest parts (`base_parts`, #5615): `tools` (the tool schemas: deny a tool in `.claude/settings.json`),
`system`, `repo` (CLAUDE.md and its `@` files), `prompt`, `skills`, `agents`, `deferred`, `mcp`, `other`; an old
transcript gives only `repo`. Sink `output`: text,
thinking and tool input. The rest of the eq (not in the sinks): owner messages, hook text and the carried output.
Field `cost`: the API list price of the calls in $, by the model of each call (`PRICES`). The eq weighs a cache read
0.1, but Opus 5.5 pays 0.05 and Haiku 5.5 pays 5 times more above 100k prompt tokens: compare lanes by the cost.
Field `verify` (#1704): the wall minutes and the count of the check commands (`pytest`, `ruff`, `vitest`, `playwright`, `build`,
`lighthouse`, `biome` (#810), `mc_check.py`, `mc_shot.py`,
`render.py`, `check tool`: a server run of `tools/*_check.py` or `game/run.py`, and `wait`: a loop that waits for the
output of a background check), from the time of a tool call to the time of its result. A background command has its
minutes in the wait loop or the notification, not in its own call.
Field `force` (#3461): the count of the force pushes that failed (`git push --force`, `-f`, `+ref`; #903 forbids them).
Phases (`--phases`): each tool call gets a phase (`phase()`), and the wall time from the call to its result counts for
it; the time from the result to the next call of the session (the model thinks and writes it) counts for the next
call (#5528). A call `claim.py N` that wins starts ticket N; the time before the first claim counts for the first
ticket. The phases that runs gave by hand were guesses: 37 minutes for a 6.5-minute run (2026-10-28).
Run line (`--run-line`, 2026-10-29): the session ID and the branch (they join the reports of one run, its claims and
the starts of the pacer), the start and wall minutes, the model, the effort, the thinking tokens (a part of `out`),
the eq of each phase (the eq of a call goes to the phase of its tool calls) and the eq of each claimed ticket.
The pure functions take plain records, so the tests need no files.
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

W_IN, W_5M, W_1H, W_READ, W_OUT = 1.0, 1.25, 2.0, 0.1, 5.0
CHARS = 4                    # characters per token (an estimate: the transcript has no token count of a result)
DOC_CHARS = 2.5              # characters per token of the memory files (measured with /context, 2026-10-29, #3833)
IMAGE = 1600                 # tokens of an image in a tool result (an estimate)
# API list prices in $ per million tokens (input, output, cache read; a cache write is the input price × W_5M or W_1H),
# 2026-10. A second row is the price of a prompt above LONG tokens.
PRICES = {
    "claude-fable-5-1": ((10.0, 50.0, 0.25),),
    "claude-haiku-5-5": ((0.10, 0.50, 0.01), (0.50, 2.50, 0.05)),
    "claude-opus-5": ((5.0, 25.0, 0.50),),
    "claude-opus-5-5": ((4.0, 20.0, 0.20),),
    "claude-sonnet-5-5": ((2.0, 10.0, 0.20),),
}
LONG = 100_000


def eq(u):
    """Input-token equivalents of one `usage` record."""
    cc = u.get("cache_creation") or {}
    h1 = cc.get("ephemeral_1h_input_tokens", 0)
    m5 = cc.get("ephemeral_5m_input_tokens", (u.get("cache_creation_input_tokens") or 0) - h1)
    return (W_IN * (u.get("input_tokens") or 0) + W_5M * m5 + W_1H * h1 + W_READ * (u.get("cache_read_input_tokens") or 0)
            + W_OUT * (u.get("output_tokens") or 0))


def usd(u, model):
    """The API list price in $ of one `usage` record of `model`, or None for a model without a price."""
    rows = PRICES.get((model or "").split("[")[0])
    if not rows:
        return None
    cc = u.get("cache_creation") or {}
    write = u.get("cache_creation_input_tokens") or 0
    h1 = cc.get("ephemeral_1h_input_tokens", 0)
    m5 = cc.get("ephemeral_5m_input_tokens", write - h1)
    read, fresh = u.get("cache_read_input_tokens") or 0, u.get("input_tokens") or 0
    p_in, p_out, p_read = rows[-1] if fresh + write + read > LONG else rows[0]
    return (p_in * (fresh + W_5M * m5 + W_1H * h1) + p_read * read + p_out * (u.get("output_tokens") or 0)) / 1e6


def label(name, inp):
    """A short sink key that groups calls of the same kind over runs: `Bash pytest`, `Read tools/x.py`, `Skill design`."""
    if name == "Bash":
        cmd = inp.get("command", "")
        cmd = re.sub(r"^(\s*(cd \S+|[A-Z_]+=\S+|export \S+)\s*(&&|;)?\s*)+", "", cmd).strip()
        words = [w for w in re.split(r"[\s|;&]+", cmd) if w and not w.startswith(("-", "'", '"'))
                 and not re.fullmatch(r"[\d,$p]+", w)][:4]
        if words[:1] == ["python3"] and len(words) > 1:
            words = words[1:]
        if words[:1] == ["timeout"]:
            words = words[2:]
        return "Bash " + " ".join(w.rsplit("/", 1)[-1] if "/" in w and w.endswith(".py") else w for w in words[:2])
    if name in ("Read", "Edit", "Write"):
        p = inp.get("file_path", "")
        return f"{name} " + re.sub(r"^/home/user/[^/]+/", "", p)
    if name in ("Grep", "Glob"):
        return name
    if name == "Skill":
        return "Skill " + inp.get("skill", "")
    if name == "Agent":
        return "Agent " + inp.get("subagent_type", "general")
    if name.startswith("mcp__"):
        return "mcp " + name.split("__")[-1]
    return name


SLOW = r"pytest\b.*-m\s+['\"]?slow\b"
CHECKS = (("pytest -m mc", r"pytest\b.*-m\s+['\"]?mc\b"),
          ("pytest -m slow files", SLOW + r".*\b(framework/)?tests/\S+\.py|pytest\b.*\btests/\S+\.py\b.*-m\s+['\"]?slow\b"),  # #822
          ("pytest -m slow", SLOW),
          ("playwright", r"\bplaywright\s+test\b"), ("lighthouse", r"\blighthouse\.mjs\b"),   # the Node checks (#810)
          ("build", r"\bnpm run build\b|\bnext build\b"),
          ("pytest files", r"pytest\b.*\btests/\S+\.py"), ("vitest files", r"\bvitest\b.*\btests/\S+\.ts\b"),
          ("pytest", r"\bpytest\b"), ("vitest", r"\bvitest\b"), ("ruff", r"\bruff\b"), ("biome", r"\bbiome\b"),
          ("mc_check.py", r"mc_check\.py"), ("mc_shot.py", r"mc_shot\.py"), ("render.py", r"render\.py"),
          ("check tool", r"(?<!framework/)tools/\w+_check\.py|\bgame/run\.py\b"))   # a server run (#5424)
WAIT = r"\buntil\b|\bsleep\b"                 # a wait loop (LEARNINGS #413): its minutes are the minutes of a check
OUTPUT = r"rc=|\.out\b|\.log\b"               # the output of a background check that a wait loop reads
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\s*\1\s*$", re.M | re.S)   # text (a PR body, a file), no command


def check(cmd):
    """The check kind of a Bash command, or None. A command with several checks (`ruff && pytest`) gets the first
    one of CHECKS, the one that takes the most time. A wait loop for the output of a check is `wait`, a wait loop for
    something else (a server) is None. The text of a heredoc does not count."""
    cmd = HEREDOC.sub("", cmd)
    if re.search(WAIT, cmd):
        return "wait" if re.search("|".join(rx for _, rx in CHECKS) + "|" + OUTPUT, cmd) else None
    return next((k for k, rx in CHECKS if re.search(rx, cmd)), None)


def when(r):
    """The time of a transcript record in seconds, or None."""
    t = r.get("timestamp")
    return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() if t else None


def verify(records):
    """{check kind: [wall minutes, count]} of the check commands of one chain of records (#1704)."""
    start, out = {}, defaultdict(lambda: [0.0, 0])
    for r in records:
        msg = r.get("message") or {}
        content = msg.get("content")
        if r.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if b.get("type") == "tool_use" and b.get("name") == "Bash":
                    k = check((b.get("input") or {}).get("command", ""))
                    if k:
                        start[b["id"]] = (k, when(r))
        elif r.get("type") == "user" and isinstance(content, list):
            for b in content:
                if b.get("type") == "tool_result" and b.get("tool_use_id") in start:
                    k, t0 = start.pop(b["tool_use_id"])
                    t1 = when(r)
                    out[k][0] += (t1 - t0) / 60 if t0 is not None and t1 is not None else 0
                    out[k][1] += 1
    return dict(out)


def verify_field(v, k=4):
    """The `verify` field of the Tokens: line: the k check kinds with the most minutes (`pytest 4.1m 2x`)."""
    top = sorted(v.items(), key=lambda kv: -kv[1][0])[:k]
    return "verify " + (", ".join(f"{s} {m:.1f}m {n}x" for s, (m, n) in top) or "-")


FORCE = re.compile(r"\bgit push\b[^\n|;&]*?(?:\s--force\b|\s--force-with-lease\b|\s-f\b|\s\+\S)")
REFUSED = re.compile(r"(?i)rejected|denied|refused|forbidden|\b403\b|non-fast-forward")


def refused_pushes(records):
    """The count of the force pushes of one chain of records that failed (#903, #3461): the runs must not force-push."""
    start, n = set(), 0
    for r in records:
        content = (r.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if b.get("type") == "tool_use" and b.get("name") == "Bash" \
                    and FORCE.search(HEREDOC.sub("", (b.get("input") or {}).get("command", ""))):
                start.add(b["id"])
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in start:
                start.discard(b["tool_use_id"])
                text = b.get("content")
                text = text if isinstance(text, str) else " ".join(str(x.get("text", "")) for x in text or [])
                n += bool(b.get("is_error") or REFUSED.search(text))
    return n


# The PR body, the commit message and the comment files of step 8 (a redirect or tee to such a file, `REPORT_NAME`).
REPORT_FILE = r"(?i)(?:\bcat >|\btee)\s*\S*(?:body|msg|message|comment)[^/\s]*"
REPORT_NAME = re.compile(r"body|msg|message|comment", re.I)


# The phase of a Bash command: the first pattern that matches (`report.md`, phases; health.PHASES). `tokens.py --queued`
# is the first call of each scheduled run (`scheduled` step 0), so it is the start, not the report: its call writes the
# base to the cache (about 40k of the 50k report eq of a run in 66 of 67 runs, owner 2026-11-06).
PHASE_RULES = (("conflict", r"merge_main\.py|unconflict\.py|\bgit merge\b"),
               ("ci", r"ship_pr\.py|\bgit push\b|/pulls\b|check-runs|mergeable|claim\.py \d+ --guard"),
               ("claim", r"tokens\.py\s+--queued"),
               ("report", r"report\.py|tokens\.py|health\.py"),
               ("claim", r"claim\.py|cycle_start\.py|dashboard\.py|feedback\.py|usage\.py"),
               ("report", REPORT_FILE),
               ("code", r"\bsed -i\b|\bcat >|\btee\b"))
# A script that writes a file is code, also in the text of a heredoc (HEREDOC removes it before PHASE_RULES): 89 of
# 916 read calls of 50 runs were such edits, and `code` had 34 of 1064 minutes (#5616; the auto mode asks for Bash edits).
WRITES = re.compile(r"""\bopen\([^()]*(?:\([^()]*\)[^()]*)*,\s*['"][wax]b?\+?['"]|\.write(?:_text|_bytes)?\(|\bsed -i\b""")
BEAT = re.compile(r"\S*claim\.py\s+\d+\s+--beat\b[^;&|\n]*")   # a keep-alive: the rest of its command gives the phase
ORDER = ("conflict", "verify", "ci", "code", "claim", "report", "read")   # a call with several tools: the first here
# a claim: no option but --takeover or --adopt NAME (the brief of the pacer, #5622), or --or with the next candidates
CLAIMED = re.compile(r"claim\.py (\d+)(?:\s+--or((?:\s+\d+)+)|\s+--takeover|\s+--adopt\s+[\w.-]+)?(?=\s*(?:$|[;&|)<>\n]|\d>))")
PHASES = ("read", "claim", "code", "verify", "ci", "conflict", "report")   # the order of the Metrics: line


def phase(name, inp):
    """The phase of one tool call: read, claim, code, verify, ci, conflict or report."""
    if name == "Bash":
        cmd = BEAT.sub("", HEREDOC.sub("", inp.get("command", "")))
        if check(cmd):
            return "verify"
        got = next((k for k, rx in PHASE_RULES if re.search(rx, cmd)), "read")
        return "code" if got == "read" and WRITES.search(inp.get("command", "")) else got
    if name in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        return "report" if REPORT_NAME.search(os.path.basename(inp.get("file_path", ""))) else "code"
    if name.startswith("mcp__github__"):
        return "ci" if re.search(r"pull_request|check|job", name) else "report" if "comment" in name else "read"
    return "read"


def calls(records):
    """(calls per phase, calls per `label()`, pairs of consecutive labels) of one chain of records (#3459): the
    frequent sequences are the candidates for one combined script call."""
    by_phase, by_label, pairs, last = Counter(), Counter(), Counter(), None
    for r in records:
        content = (r.get("message") or {}).get("content")
        if r.get("type") != "assistant" or not isinstance(content, list):
            continue
        for b in content:
            if b.get("type") == "tool_use":
                name, inp = b.get("name", ""), b.get("input") or {}
                lab = label(name, inp)
                by_phase[phase(name, inp)] += 1
                by_label[lab] += 1
                if last:
                    pairs[(last, lab)] += 1
                last = lab
    return by_phase, by_label, pairs


def read_labels(records):
    """The calls per `label()` of the phase `read` (#189): the reads that repeat."""
    return Counter(label(b.get("name", ""), b.get("input") or {}) for r in records
                   if r.get("type") == "assistant" and isinstance((r.get("message") or {}).get("content"), list)
                   for b in r["message"]["content"] if b.get("type") == "tool_use"
                   and phase(b.get("name", ""), b.get("input") or {}) == "read")


def calls_line(records, k=5, k_read=3):
    """The Calls: line of the run report (#3970): the calls per phase, the k most frequent labels of a run and the
    k_read most frequent labels of the phase `read` (#189)."""
    ph, lab, _ = calls(records)
    return (f"Calls: {', '.join(f'{p} {n}' for p, n in ph.most_common())} · "
            f"top {', '.join(f'{n}x {x}' for x, n in lab.most_common(k))} · "
            f"read top {', '.join(f'{n}x {x}' for x, n in read_labels(records).most_common(k_read)) or '-'}")


def phases(records):
    """{ticket: {phase: minutes}} of one chain of records, in the order of the tickets; the time before the first
    claim counts for the first ticket (key None when no claim won). The gap from a call to the next call splits at
    the time of its last tool result: the run of the tool counts for its phase, the thinking and writing after the
    result for the phase of the next call (#5528). With no result time, the whole gap counts for the call."""
    calls = []                                        # (time, phase, claimed ticket or None, time of the last result)
    claims, done, ids = {}, set(), {}
    for r in records:
        msg = r.get("message") or {}
        content = msg.get("content")
        if r.get("type") == "assistant" and isinstance(content, list):
            tools = [b for b in content if b.get("type") == "tool_use"]
            if tools and when(r) is not None:
                ps = [phase(b.get("name", ""), b.get("input") or {}) for b in tools]
                calls.append([when(r), min(ps, key=ORDER.index), None, None])
                for b in tools:
                    ids[b.get("id")] = len(calls) - 1
                    ns = claim_numbers((b.get("input") or {}).get("command", "")) if b.get("name") == "Bash" else []
                    if ns:
                        claims[b["id"]] = (len(calls) - 1, ns)
        elif r.get("type") == "user" and isinstance(content, list):
            for b in content:
                if b.get("type") == "tool_result" and b.get("tool_use_id") in ids and when(r) is not None:
                    c = calls[ids[b["tool_use_id"]]]
                    c[3] = max(c[3] or when(r), when(r))
                if b.get("type") == "tool_result" and b.get("tool_use_id") in claims:
                    i, ns = claims.pop(b["tool_use_id"])
                    n = won(b, ns)
                    if n is not None and n not in done:
                        done.add(n)
                        calls[i][2] = n
    out, keys, ticket = {}, [], None
    first = next((c[2] for c in calls if c[2] is not None), None)
    for c in calls:
        ticket = c[2] if c[2] is not None else ticket
        keys.append(ticket if ticket is not None else first)
        out.setdefault(keys[-1], dict.fromkeys(PHASES, 0.0))
    for i, (t, ph, _, res) in enumerate(calls):
        end = calls[i + 1][0] if i + 1 < len(calls) else max(t, res or t)   # the last call: up to its result
        cut = min(max(res, t), end) if res is not None else end
        out[keys[i]][ph] += (cut - t) / 60
        if cut < end:                                 # the model thinks and writes the next call
            out[keys[i + 1]][calls[i + 1][1]] += (end - cut) / 60
    return out


def claim_numbers(cmd):
    """The tickets that the command claims, in the order of the tries: `claim.py N` and `claim.py N --or M K`."""
    m = CLAIMED.search(cmd + "\n")
    return [int(m[1]), *map(int, (m[2] or "").split())] if m else []


def won(block, numbers):
    """The ticket of `numbers` whose claim the tool result `block` says that it won (`claimed claim/N`, `claim/N-2`),
    or None."""
    c = block.get("content")
    text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
    m = re.search(r"(?:claimed|adopted) claim/(\d+)\b", text or "")
    return int(m[1]) if m and int(m[1]) in numbers else None


def steps(records):
    """One dict per API call of one chain, in order: `at`, `phase` (of its tool calls, the first in ORDER; a call with
    no tool call has the phase of the call before), `ticket` (the ticket of a claim of this call that won), `eq`,
    `model`, `effort` and `think` (the thinking tokens of its output)."""
    rows, by_id, claims, done = [], {}, {}, set()
    for r in records:
        msg = r.get("message") or {}
        content = msg.get("content") if isinstance(msg.get("content"), list) else []
        if r.get("type") == "assistant":
            row = by_id.get(msg.get("id"))
            if row is None:                         # one record per content block, all with the same usage
                u = msg.get("usage") or {}
                row = by_id[msg.get("id")] = dict(at=when(r), phase=None, ticket=None, eq=eq(u), model=msg.get("model"),
                                                  effort=r.get("effort"),
                                                  think=(u.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
                rows.append(row)
            for b in content:
                if b.get("type") == "tool_use":
                    p = phase(b.get("name", ""), b.get("input") or {})
                    row["phase"] = p if row["phase"] is None else min(row["phase"], p, key=ORDER.index)
                    ns = claim_numbers((b.get("input") or {}).get("command", "")) if b.get("name") == "Bash" else []
                    if ns:
                        claims[b["id"]] = (row, ns)
        elif r.get("type") == "user":
            for b in content:
                if b.get("type") == "tool_result" and b.get("tool_use_id") in claims:
                    row, ns = claims.pop(b["tool_use_id"])
                    n = won(b, ns)
                    if n is not None and n not in done:
                        done.add(n)
                        row["ticket"] = n
    last = "read"
    for row in rows:
        row["phase"] = last = row["phase"] or last
    return rows


def ticket_eq(rows):
    """{ticket: eq} of the rows of steps(): a call counts for the ticket of the last won claim; the calls before the
    first claim count for the first ticket (key None when no claim won)."""
    out, ticket = {}, None
    first = next((r["ticket"] for r in rows if r["ticket"] is not None), None)
    for r in rows:
        ticket = r["ticket"] if r["ticket"] is not None else ticket
        key = ticket if ticket is not None else first
        out[key] = out.get(key, 0.0) + r["eq"]
    return out


def run_data(records):
    """The data of the Run: line of one chain: session, branch, start, wall minutes, setup (the minutes from the start
    to the first won claim, the `setup` of the report), models, efforts, thinking tokens, CLI version, the eq of each
    phase and the eq of each ticket that a claim won."""
    rows = steps(records)
    first = lambda key: next((r[key] for r in records if r.get(key)), None)
    times = [t for t in map(when, records) if t is not None]
    by_phase = dict.fromkeys(PHASES, 0.0)
    for r in rows:
        by_phase[r["phase"]] += r["eq"]
    won = next((r["at"] for r in rows if r["ticket"] is not None and r["at"] is not None), None)
    return {"session": first("sessionId"), "branch": first("gitBranch"),
            "start": datetime.fromtimestamp(min(times), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if times else None,
            "wall": round((max(times) - min(times)) / 60, 1) if times else 0,
            "setup": round((won - min(times)) / 60, 1) if times and won is not None else None,
            "models": dict(Counter((r["model"] or "").removeprefix("claude-") for r in rows if r["model"]).most_common()),
            "effort": dict(Counter(r["effort"] for r in rows if r["effort"]).most_common()),
            "think": sum(r["think"] for r in rows), "cli": first("version"), "phases_eq": by_phase,
            "tickets_eq": {n: x for n, x in ticket_eq(rows).items() if n is not None}}


def run_line(records):
    """The Run: line of the run report (2026-10-29): `Run: <session> · branch B · start T · wall M min · model X ·
    effort E · think T · eq <phase> X, ... · tickets #N X, ...`. The session ID joins the reports of one run, the
    branch its claims and PRs. One chain: the main transcript."""
    d = run_data(records)
    m = lambda x: f"{x / 1e6:.2f}M"
    common = lambda c: ", ".join(f"{k} {n}" for k, n in c.items()) or "-"
    return (f"Run: {d['session'] or '-'} · branch {d['branch'] or '-'} · start {d['start'] or '-'} · "
            f"wall {d['wall']:.0f} min · model {common(d['models'])} · effort {common(d['effort'])} · "
            f"think {m(d['think'])} · cli {d['cli'] or '-'} · eq "
            + ", ".join(f"{p} {m(x)}" for p, x in d["phases_eq"].items())
            + ("" if not d["tickets_eq"] else " · tickets " + ", ".join(f"#{n} {m(x)}" for n, x in d["tickets_eq"].items())))


def data(t, records, repo=None, checks=None, force=None, k=10, parts=None):
    """All numbers of the run as one dict (`--json`): the fields of the Tokens: line, the top `k` sink groups (share of
    the eq), the calls of each phase and the most frequent calls, and run_data(). The run record of `report.py` holds it."""
    g = defaultdict(float)
    for s, x in t["sinks"].items():
        g[kind(s)] += x
    ph, lab, _ = calls(records)
    out = {key: round(t.get(key, 0), 4) for key in ("eq", "write", "read", "out", "peak", "base", "usd", "in", "text")}
    return {**out, "calls": t["calls"], "repo": None if repo is None else round(repo),
            "base_parts": {p: round(n) for p, n in (parts or {}).items()},
            "sinks": {s: round(x / t["eq"], 4) for s, x in sorted(g.items(), key=lambda kv: -kv[1])[:k]} if t["eq"] else {},
            "verify": {s: [round(m, 1), n] for s, (m, n) in (checks or {}).items()}, "force": force,
            "calls_phase": dict(ph.most_common()), "calls_top": dict(lab.most_common(k)), **run_data(records)}


def size(content):
    """Tokens of a tool result (string or list of blocks)."""
    if isinstance(content, str):
        return len(content) / CHARS
    return sum(len(b.get("text", "")) / CHARS if b.get("type") == "text" else IMAGE if b.get("type") == "image" else 0
               for b in content or [])


def analyse(records):
    """Totals and sinks of one chain of transcript records (in file order).
    Returns {"eq", "calls", "in", "write", "read", "out", "peak", "base", "text", "sinks": {label: eq}}; `text`: the
    estimated tokens of the chat text (a part of `out`; no one reads the chat of a scheduled run, owner 2026-11-06)."""
    seen, calls, uses = set(), [], {}
    t = dict.fromkeys(("eq", "in", "write", "read", "out", "peak", "base", "usd", "unpriced", "text"), 0.0)
    results = []                                    # (label, tokens, index of the next call)
    for r in records:
        msg = r.get("message") or {}
        if r.get("type") == "assistant":
            for b in msg.get("content") or []:
                if b.get("type") == "tool_use":
                    uses[b["id"]] = label(b.get("name", ""), b.get("input") or {})
                elif b.get("type") == "text":
                    t["text"] += len(b.get("text") or "") / CHARS     # the chat text: a part of `out`
            u = msg.get("usage")
            if u and msg.get("id") not in seen:     # one record per content block, all with the same usage
                seen.add(msg.get("id"))
                calls.append(u)
                t["eq"] += eq(u)
                d = usd(u, msg.get("model"))
                t["usd"] += d or 0
                t["unpriced"] += d is None
                t["in"] += u.get("input_tokens") or 0
                t["write"] += u.get("cache_creation_input_tokens") or 0
                t["read"] += u.get("cache_read_input_tokens") or 0
                t["out"] += u.get("output_tokens") or 0
                ctx = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                t["peak"] = max(t["peak"], ctx)
                if len(calls) == 1:
                    t["base"] = ctx                 # the system prompt, tools, CLAUDE.md and LEARNINGS of each call
        elif r.get("type") == "user" and isinstance(msg.get("content"), list):
            for b in msg["content"]:
                if b.get("type") == "tool_result":
                    results.append((uses.get(b.get("tool_use_id"), "?"), size(b.get("content")), len(calls)))
    n = len(calls)
    sinks = defaultdict(float)
    for lab, tok, at in results:
        sinks[lab] += tok * (W_1H + W_READ * max(n - at - 1, 0))
    first = calls[0] if calls else {}
    sinks["base"] = eq(first) - W_OUT * (first.get("output_tokens") or 0) \
        + t["base"] * W_READ * max(n - 1, 0)
    sinks["output"] = W_OUT * t["out"]
    t["calls"], t["sinks"] = n, dict(sinks)
    return t


def merge(parts):
    out = {"sinks": defaultdict(float)}
    for p in parts:
        for k, v in p.items():
            if k == "sinks":
                for s, x in v.items():
                    out["sinks"][s] += x
            elif k == "peak":
                out[k] = max(out.get(k, 0), v)
            elif k == "base":
                out.setdefault(k, v)                # the base of the main chain (the first part)
            else:
                out[k] = out.get(k, 0) + v
    return out


def kind(lab):
    """The group of a sink for the Tokens: line: the tool, and the program of a command (`Read`, `Bash pytest`)."""
    if lab.startswith("Bash"):
        return " ".join(lab.split(" ")[:2])
    return lab if lab.startswith(("base", "output", "Skill", "mcp", "Agent")) else lab.split(" ", 1)[0]


def line(t, k=5, repo=None, checks=None, force=None, parts=None):
    """The `Tokens:` line of the run report (framework/tools/health.py reads it). checks: the verify() of the run (#1704).
    force: the refused force pushes of the run (#3461). parts: the base_parts() of the run: the 4 largest replace the
    `repo` estimate (#5615)."""
    g = defaultdict(float)
    for s, x in t["sinks"].items():
        g[kind(s)] += x
    top = sorted(g.items(), key=lambda kv: -kv[1])[:k]
    m = lambda x: f"{x / 1e6:.2f}M"
    return (f"Tokens: {m(t['eq'])} eq · calls {t['calls']} · write {m(t['write'])} · read {m(t['read'])} · "
            f"out {m(t['out'])} · cost ${t.get('usd', 0):.2f}"
            + (f" (+{t['unpriced']:.0f} calls without a price)" if t.get("unpriced") else "")
            + f" · peak {t['peak'] / 1e3:.0f}k · base {t['base'] / 1e3:.0f}k"
            + (f" ({', '.join(f'{p} {n / 1e3:.1f}k' for p, n in list(parts.items())[:4])})" if parts
               else "" if repo is None else f" (repo {repo / 1e3:.0f}k)")
            + ("" if checks is None else " · " + verify_field(checks))
            + ("" if force is None else f" · force {force}") + " · sinks "
            + ", ".join(f"{s} {x / t['eq']:.0%}" for s, x in top))


# The parts of the base (#5615): the attachment types of the first turn, else "other" (environment, date, mode).
BASE_PARTS = {"instructions": "repo", "skill_listing": "skills", "agent_listing_delta": "agents",
              "deferred_tools_delta": "deferred", "mcp_instructions_delta": "mcp"}


def base_parts(records, base):
    """{part: tokens} of the base of the first call (#5615): the system prompt (`system`), the tool schemas (`tools`),
    the repository files (`repo`), the skill, agent, deferred tool and MCP lists, the first prompt (`prompt`) and the
    other attachments. The transcript gives the text of each part (records `prompt_snapshot` and `attachment`), not
    its tokens: the parts share the measured base by their characters. {} without a snapshot (an old transcript)."""
    chars, snap = defaultdict(int), {}
    for r in records:                               # the first turn writes the tools in a later snapshot
        a = r.get("attachment") if r.get("type") == "attachment" else None
        if isinstance(a, dict) and a.get("type") == "prompt_snapshot":
            for k in ("systemPrompt", "cliPrefix", "tools"):
                if snap.get(k) is None:
                    snap[k] = a.get(k)
    if not snap:
        return {}
    for r in records:
        if r.get("type") == "assistant" and (r.get("message") or {}).get("usage"):
            break
        a = r.get("attachment") if r.get("type") == "attachment" else None
        if isinstance(a, dict) and a.get("type") != "prompt_snapshot":
            text = r.get("rendered")
            n = sum(len(x.get("content") or "") for x in text) if isinstance(text, list) else len(json.dumps(a))
            chars[BASE_PARTS.get(a.get("type"), "other")] += n
        elif r.get("type") == "user" and a is None:
            c = (r.get("message") or {}).get("content")
            chars["prompt"] += len(c) if isinstance(c, str) else sum(len(b.get("text") or "") for b in c or [])
    chars["system"] += sum(len(x) for x in snap.get("systemPrompt") or []) + len(snap.get("cliPrefix") or "")
    chars["tools"] += sum(len(json.dumps(x)) for x in snap.get("tools") or [])
    total = sum(chars.values())
    return {k: base * n / total for k, n in sorted(chars.items(), key=lambda kv: -kv[1]) if n} if total else {}


def repo_base(root="."):
    """Tokens of the base that the repository controls: CLAUDE.md and the files that it loads with `@path` lines."""
    try:
        text = open(os.path.join(root, "CLAUDE.md")).read()
    except OSError:
        return 0
    n = len(text)
    for inc in re.findall(r"^@(\S+)$", text, re.M):
        try:
            n += len(open(os.path.join(root, inc)).read())
        except OSError:
            pass
    return n / DOC_CHARS


def load(path):
    with open(path) as f:
        return [json.loads(x) for x in f if x.strip()]


def newest(cwd=None):
    d = os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd or os.getcwd())))
    fs = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime)
    return fs[-1] if fs else None


BRIEF = "travel-aggregator pacer brief"   # `pacer.HEAD`: the first line of a brief


def queued_brief(records):
    """The `ticket:` line of a brief of the pacer that waits in the queue of this session, or None. A fire of the
    pacer makes a new session with two queued turns: the stored prompt of the task ("/scheduled ...", no brief) and,
    8 ms later, the brief. The brief comes only when the first turn ends: a first turn that did a whole run got its
    brief at 102k to 140k context and gave the ticket back (#4550). The queue is FIFO: `enqueue` adds, `dequeue`
    takes the oldest."""
    queue = []
    for r in records:
        if r.get("type") != "queue-operation":
            continue
        if r.get("operation") == "enqueue":
            queue.append(r.get("content") or "")
        elif r.get("operation") == "dequeue" and queue:
            queue.pop(0)
        elif r.get("operation") == "remove" and r.get("content") in queue:
            queue.remove(r["content"])
    for text in queue:
        if BRIEF in text:
            return next((x.strip() for x in text.splitlines() if x.strip().startswith("ticket:")), "ticket: ?")
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", nargs="?", help="a transcript (default: the newest session of this directory)")
    ap.add_argument("--top", type=int, help="print the N largest sinks, one per line")
    ap.add_argument("--verify", action="store_true", help="print each check command kind: minutes and count (#1704)")
    ap.add_argument("--calls", type=int, metavar="N", help="print the tool calls per phase and the N most frequent "
                    "calls and pairs of calls (#3459)")
    ap.add_argument("--phases", action="store_true", help="print the measured phase minutes of each claimed ticket")
    ap.add_argument("--calls-line", action="store_true", help="print the Calls: line of the run (#3970)")
    ap.add_argument("--run-line", action="store_true", help="print the Run: line of the run (session, start, model, "
                    "eq per phase and ticket)")
    ap.add_argument("--json", action="store_true", help="print all numbers of the run as one JSON object (report.py)")
    ap.add_argument("--queued", action="store_true", help="exit 0 and print its ticket line when a brief of the "
                    "pacer waits as the next turn of this session (`scheduled` skill, step 0, #4550), else exit 1")
    a = ap.parse_args(argv)
    path = a.file or newest()
    if not path:
        sys.exit("no transcript in ~/.claude/projects for this directory")
    if a.queued:
        got = queued_brief(load(path))
        print(f"queued brief: {got}" if got else "no queued brief")
        return 0 if got else 1
    subs = sorted(glob.glob(os.path.join(path[:-len(".jsonl")], "subagents", "*.jsonl")))
    chains = [load(path)] + [load(s) for s in subs]
    t = merge([analyse(c) for c in chains])
    v = defaultdict(lambda: [0.0, 0])
    for c in chains:
        for s, (m, n) in verify(c).items():
            v[s][0] += m
            v[s][1] += n
    if a.calls:
        ph, lab, pairs = calls(chains[0])
        print(f"calls {sum(ph.values())}: " + ", ".join(f"{k} {n}" for k, n in ph.most_common()))
        for k, n in lab.most_common(a.calls):
            print(f"  {n:4d}x  {k}")
        for (x, y), n in pairs.most_common(a.calls):
            print(f"  {n:4d}x  {x} -> {y}")
        return 0
    if a.calls_line:
        print(calls_line(chains[0]))
        return 0
    if a.run_line:
        print(run_line(chains[0]))
        return 0
    if a.phases:
        for n, p in phases(chains[0]).items():
            print(f"#{n}: " + ",".join(f"{k}={m:.0f}" for k, m in p.items()))
        return 0
    force = sum(refused_pushes(c) for c in chains)
    parts = base_parts(chains[0], t["base"])
    if a.json:
        print(json.dumps(data(t, chains[0], repo_base(), dict(v), force, parts=parts)))
        return 0
    print(line(t, repo=repo_base(), checks=dict(v), force=force, parts=parts))
    if a.verify:
        for s, (m, n) in sorted(v.items(), key=lambda kv: -kv[1][0]):
            print(f"  {m:6.1f} min  {n:3d}x  {s}")
    for s, x in sorted(t["sinks"].items(), key=lambda kv: -kv[1])[:a.top or 0]:
        print(f"  {x / t['eq']:5.1%}  {x / 1e3:8.0f}k  {s}")
    for p, n in parts.items() if a.top else ():      # the parts of the base of each call (#5615)
        print(f"  base  {n / t['base']:5.1%}  {n / 1e3:6.1f}k  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
