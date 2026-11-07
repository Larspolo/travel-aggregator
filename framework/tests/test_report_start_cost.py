"""The start call and the end of a run (owner, 2026-11-06): `tokens.py --queued` is the first call of each scheduled run
and writes the base to the cache, so it counts for `claim`, not for `report`; `report.py --post` prints the context
peak, so the run needs no own `tokens.py` call; `tokens.py --json` measures the chat text that no one reads."""
import report
import tokens


def test_the_queued_check_is_the_start_not_the_report():
    assert tokens.phase("Bash", {"command": "python3 framework/tools/tokens.py --queued; echo \"exit $?\""}) == "claim"
    assert tokens.phase("Bash", {"command": "python3 framework/tools/tokens.py --top 15"}) == "report"
    assert tokens.phase("Bash", {"command": "python3 framework/tools/report.py --post --text t"}) == "report"


def test_the_first_call_of_a_scheduled_run_counts_for_claim():
    recs = [{"type": "assistant", "message": {"id": "a", "usage": {"cache_creation_input_tokens": 20000},
                                              "content": [{"type": "tool_use", "id": "a", "name": "Bash",
                                                           "input": {"command": "python3 framework/tools/tokens.py --queued"}}]}}]
    by_phase = tokens.run_data(recs)["phases_eq"]
    assert by_phase["claim"] == 25000 and by_phase["report"] == 0


def test_the_json_measures_the_chat_text():
    recs = [{"type": "assistant", "message": {"id": "a", "usage": {"output_tokens": 30},
                                              "content": [{"type": "text", "text": "x" * 40},
                                                          {"type": "tool_use", "id": "a", "name": "Read", "input": {}}]}},
            {"type": "assistant", "message": {"id": "b", "usage": {"output_tokens": 5},
                                              "content": [{"type": "text", "text": "y" * 8}]}}]
    t = tokens.analyse(recs)
    assert t["text"] == 12 and tokens.data(t, recs)["text"] == 12


def test_the_post_prints_the_context_peak(monkeypatch, capsys):
    monkeypatch.setattr(report, "git_lane", lambda: None)
    monkeypatch.setattr(report, "numbers", lambda: {"peak": 84321, "setup": 0})
    monkeypatch.setattr(report, "measured", lambda: {"7": "read=2,code=10"})
    monkeypatch.setattr(report, "report", lambda *a, **k: "body")
    monkeypatch.setattr(report.metrics_log, "post", lambda record: "runs/x.json")
    monkeypatch.setattr(report, "pages", lambda path: [{"number": 1}])
    monkeypatch.setattr(report, "api", lambda path, *a: {"body": ""})
    monkeypatch.setattr(report, "counted", lambda body: body)
    monkeypatch.setattr(report, "hand_off", lambda tickets: None)
    report.main(["--text", "t", "--usage", "u", "--ticket", "7", "--size", "S", "--result", "pr #1", "--post"])
    assert "context 84k" in capsys.readouterr().out
