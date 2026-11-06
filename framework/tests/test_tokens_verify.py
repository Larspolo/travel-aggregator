"""framework/tools/tokens.py --verify and the verify field in framework/tools/health.py: the minutes of each check command (#1704)."""
import health
import tokens


def use(tid, cmd, t):
    return {"type": "assistant", "timestamp": t, "message": {"id": tid, "content": [
        {"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": cmd}}]}}


def result(tid, t):
    return {"type": "user", "timestamp": t, "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": "ok"}]}}


def test_check_kinds():
    assert tokens.check("cd /x && python3 -m pytest -q") == "pytest"
    assert tokens.check("ruff check . && python3 -m pytest -m slow; echo rc=$?") == "pytest -m slow"
    assert tokens.check("PYTHONPATH=game:tools:. python3 -m pytest -m mc tests/test_a.py") == "pytest -m mc"
    assert tokens.check("python3 -m pytest tests/test_a.py tests/test_b.py") == "pytest files"
    assert tokens.check("ruff check .") == "ruff"
    assert tokens.check("python3 tools/mc_shot.py W out.png") == "mc_shot.py"
    assert tokens.check("timeout 580 bash -c 'until grep -q rc= $S/fast.out; do sleep 5; done'") == "wait"
    assert tokens.check("until grep -q 'Done (' logs/latest.log; do sleep 2; done") == "wait"
    assert tokens.check("until curl -s localhost:25565; do sleep 2; done") is None
    assert tokens.check("git status --short") is None
    assert tokens.check("cat > pr.md <<'EOF'\nRan `pytest -m mc` and ruff.\nEOF\ngh api x -F body=@pr.md") is None
    assert tokens.check("cat > a.md <<'EOF'\npytest -m mc\nEOF\npython3 -m pytest -q tests/test_a.py") == "pytest files"


def test_verify_minutes_and_repeats():
    recs = [use("a", "python3 -m pytest", "2026-10-27T10:00:00Z"), result("a", "2026-10-27T10:04:00Z"),
            use("b", "git diff", "2026-10-27T10:05:00Z"), result("b", "2026-10-27T10:05:01Z"),
            use("c", "python3 -m pytest -q", "2026-10-27T10:10:00Z"), result("c", "2026-10-27T10:13:30Z"),
            use("d", "ruff check .", "2026-10-27T10:14:00Z"), result("d", "2026-10-27T10:14:06Z")]
    v = tokens.verify(recs)
    assert v == {"pytest": [7.5, 2], "ruff": [0.1, 1]}
    assert tokens.verify_field(v) == "verify pytest 7.5m 2x, ruff 0.1m 1x"
    assert tokens.verify_field({}) == "verify -"


def test_the_tokens_line_has_the_verify_field_and_health_adds_it():
    t = {"eq": 1e6, "calls": 3, "write": 0, "read": 0, "out": 0, "peak": 0, "base": 0, "sinks": {"base": 5e5}}
    ln = tokens.line(t, checks={"pytest": [7.5, 2], "pytest -m mc": [21.0, 1]})
    assert " · verify pytest -m mc 21.0m 1x, pytest 7.5m 2x · sinks base 50%" in ln
    comments = [{"body": "Metrics: x\n" + ln}, {"body": tokens.line(t, checks={"pytest": [4.0, 1]})}]
    assert health.verify_minutes(comments) == {"pytest -m mc": (21.0, 1), "pytest": (11.5, 3)}
    assert health.token_lines(comments)[0] == (1.0, {"base": 0.5})   # the sinks still parse
    assert health.verify_minutes([{"body": tokens.line(t)}]) == {}    # an old line without the field
