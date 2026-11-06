"""framework/tools/tokens.py and the Tokens: lines in framework/tools/health.py: the token sinks of a run (owner, 2026-10-27)."""
import health
import tokens


def call(mid, write=0, read=0, out=0, tool=None):
    content = [{"type": "tool_use", "id": tool[0], "name": tool[1], "input": tool[2]}] if tool else []
    return {"type": "assistant", "message": {"id": mid, "content": content, "usage": {
        "input_tokens": 0, "cache_creation_input_tokens": write, "cache_read_input_tokens": read, "output_tokens": out,
        "cache_creation": {"ephemeral_1h_input_tokens": write, "ephemeral_5m_input_tokens": 0}}}}


def result(tid, text):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": text}]}}


def test_eq_weights():
    assert tokens.eq({"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000,
                      "output_tokens": 2, "cache_creation": {"ephemeral_1h_input_tokens": 60}}) == 10 + 40 * 1.25 + 120 + 100 + 10


def test_labels():
    assert tokens.label("Bash", {"command": "cd /x && python3 -m pytest -q tests/a.py"}) == "Bash pytest a.py"
    assert tokens.label("Bash", {"command": "sed -n 1,40p tests/t.py"}) == "Bash sed t.py"
    assert tokens.label("Bash", {"command": "python3 framework/tools/health.py --hours 3"}) == "Bash health.py"
    assert tokens.label("Read", {"file_path": "/home/user/travel-aggregator/game/train.py"}) == "Read game/train.py"
    assert tokens.label("mcp__github__issue_read", {}) == "mcp issue_read"
    assert tokens.kind("Bash pytest tests/a.py") == "Bash pytest" and tokens.kind("Read game/train.py") == "Read"


def test_a_result_costs_each_later_call():
    recs = [call("m1", write=1000, out=10, tool=("t1", "Read", {"file_path": "/home/user/r/big.py"})),
            call("m1", write=1000, out=10),                     # a second block of the same call: count it once
            result("t1", "x" * 4000),                           # 1000 tokens
            call("m2", read=1000, write=1000, out=10), call("m3", read=2000, out=10), call("m4", read=2000, out=10)]
    t = tokens.analyse(recs)
    assert t["calls"] == 4 and t["out"] == 40 and t["base"] == 1000 and t["peak"] == 2000
    assert t["sinks"]["Read big.py"] == 1000 * (2.0 + 0.1 * 2)  # written once, read by the 2 calls after the next
    assert t["sinks"]["base"] == 2000 + 1000 * 0.1 * 3
    assert t["sinks"]["output"] == 200


def test_health_reads_the_tokens_line():
    t = {"eq": 2e6, "calls": 50, "write": 3e5, "read": 9e6, "out": 4e4, "peak": 120e3, "base": 80e3,
         "sinks": {"base": 1e6, "output": 2e5, "Read a.py": 3e5, "Read b.py": 1e5, "Bash pytest x": 2e5}}
    line = tokens.line(t)
    assert line.startswith("Tokens: 2.00M eq · calls 50 ·") and line.endswith("base 50%, Read 20%, output 10%, Bash pytest 10%")
    other = "Tokens: 1.00M eq · calls 9 · write 0.1M · sinks base 30%, Bash gh 40%"
    lines = health.token_lines([{"body": "Run\n" + line}, {"body": other}, {"body": None}])
    assert lines[1] == (1.0, {"base": 0.3, "Bash gh": 0.4})
    assert health.token_sinks(lines, 2) == [("base", (1.0 + 0.3) / 3), ("Read", 0.4 / 3)]


def test_repo_base(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x" * 40 + "\n@docs/L.md\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "L.md").write_text("y" * 400)
    assert tokens.repo_base(tmp_path) == (52 + 400) / tokens.DOC_CHARS
    assert tokens.repo_base(tmp_path / "docs") == 0


def test_calls_line_counts_the_phases_and_the_top_labels():
    chain = [call("a", tool=("1", "Bash", {"command": "python3 -m pytest -q"})),
             call("b", tool=("2", "Bash", {"command": "python3 -m pytest -q"})),
             call("c", tool=("3", "Read", {"file_path": "x.py"}))]
    line = tokens.calls_line(chain, k=1)
    assert line.startswith("Calls: ") and " · top 2x " in line
    assert line.count("Calls:") == 1
