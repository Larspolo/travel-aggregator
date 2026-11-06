"""`tokens.py --phases`: the phase minutes of each ticket, measured in the transcript (owner, 2026-10-28)."""
import health
import report
import tokens


def at(seconds):
    return f"2026-10-28T12:{seconds // 60:02d}:{seconds % 60:02d}.000Z"


def call(seconds, uid, name, **inp):
    return {"type": "assistant", "timestamp": at(seconds),
            "message": {"id": uid, "content": [{"type": "tool_use", "id": uid, "name": name, "input": inp}]}}


def result(seconds, uid, text):
    return {"type": "user", "timestamp": at(seconds),
            "message": {"content": [{"type": "tool_result", "tool_use_id": uid, "content": text}]}}


def test_each_call_gets_its_phase():
    assert tokens.phase("Bash", {"command": "ruff check . && python3 -m pytest -n auto"}) == "verify"
    assert tokens.phase("Bash", {"command": "python3 framework/tools/merge_main.py --push 5"}) == "conflict"
    assert tokens.phase("Bash", {"command": "python3 framework/tools/claim.py 5 --guard"}) == "ci"
    assert tokens.phase("Bash", {"command": "python3 framework/tools/claim.py 5"}) == "claim"
    assert tokens.phase("Bash", {"command": "sed -i 's/a/b/' x.py"}) == "code"
    assert tokens.phase("Bash", {"command": "sed -n 1,40p travel-aggregator.py"}) == "read"
    assert tokens.phase("Edit", {"file_path": "x.py"}) == "code"
    assert tokens.phase("mcp__github__create_pull_request", {}) == "ci"
    assert tuple(tokens.ORDER[:-1]) + ("read",) == tokens.ORDER and set(tokens.ORDER) == set(health.PHASES)


def test_the_time_goes_to_the_ticket_of_the_last_won_claim():
    recs = [call(0, "a", "Bash", command="python3 framework/tools/cycle_start.py"),
            call(60, "b", "Bash", command="python3 framework/tools/claim.py 7"), result(61, "b", "claimed claim/7\nadded"),
            call(120, "c", "Edit", file_path="x.py"),
            call(300, "d", "Bash", command="python3 -m pytest -n auto"),
            call(600, "e", "Bash", command="python3 framework/tools/ship_pr.py 7 --message m"),
            call(900, "f", "Bash", command="python3 framework/tools/claim.py 8"), result(901, "f", "owned by another run: x"),
            call(960, "g", "Bash", command="python3 framework/tools/claim.py 9"), result(961, "g", "claimed claim/9"),
            call(1020, "h", "Read", file_path="y.py"),
            call(1140, "i", "Bash", command="python3 framework/tools/report.py --post")]
    got = tokens.phases(recs)
    assert list(got) == [7, 9]
    # the time from a result to the next call counts for the next call (#5528): 61 s to 120 s is code, 901 s to 960 s
    # is the claim of ticket 9, 961 s to 1020 s is read
    sec = {k: {p: round(m * 60) for p, m in v.items()} for k, v in got.items()}
    assert sec[7] == {"read": 0, "claim": 60 + 1 + 1, "code": 59 + 180, "verify": 300, "ci": 300, "conflict": 0,
                      "report": 0}
    assert sec[9] == {"read": 59 + 120, "claim": 59 + 1, "code": 0, "verify": 0, "ci": 0, "conflict": 0, "report": 0}


def test_the_report_uses_the_measured_phases(monkeypatch):
    monkeypatch.setattr(report, "measured", lambda: {"7": "read=2,code=10", "None": "read=1"})
    monkeypatch.setattr(report, "report", lambda text, usage, lines: "\n".join(lines))
    printed = []
    monkeypatch.setattr("builtins.print", printed.append)
    report.main(["--text", "t", "--usage", "u", "--ticket", "7", "--size", "S", "--result", "pr #1"])
    assert "· 12 min ·" in printed[0] and "phases read 2 · claim 0 · code 10" in printed[0]
    report.main(["--text", "t", "--usage", "u", "--ticket", "7", "--size", "S", "--result", "pr #1",
                 "--phases", "read=1"])
    assert "· 1 min ·" in printed[1]                                           # a given --phases wins
