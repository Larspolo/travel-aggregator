"""The `cost` field of the Tokens: line: the API list price of a run by the model of each call (owner, 2026-10-28)."""
import health
import tokens


def usage(fresh=0, write=0, read=0, out=0):
    return {"input_tokens": fresh, "cache_creation_input_tokens": write, "cache_read_input_tokens": read,
            "output_tokens": out, "cache_creation": {"ephemeral_1h_input_tokens": write, "ephemeral_5m_input_tokens": 0}}


def test_an_opus_run_costs_what_the_session_reports():
    # the usage and `total_cost_usd` 9.6446092 of a real one-session run (session_015DtRQpHKM64tSY1QYDo74U)
    u = usage(fresh=352, write=235522, read=30125826, out=86693)
    assert round(tokens.usd(u, "claude-opus-5-5"), 6) == 9.644609


def test_a_long_haiku_prompt_costs_five_times_more():
    short, long = usage(read=90_000, out=1000), usage(read=110_000, out=1000)
    assert round(tokens.usd(short, "claude-haiku-5-5"), 6) == round((90_000 * 0.01 + 1000 * 0.5) / 1e6, 6)
    assert round(tokens.usd(long, "claude-haiku-5-5"), 6) == round((110_000 * 0.05 + 1000 * 2.5) / 1e6, 6)


def test_a_model_without_a_price_shows_in_the_line():
    assert tokens.usd(usage(read=10), "claude-unknown") is None
    recs = [{"type": "assistant", "message": {"id": "a", "model": "claude-opus-5-5", "content": [], "usage": usage(read=1e6)}},
            {"type": "assistant", "message": {"id": "b", "model": "x", "content": [], "usage": usage(read=1e6)}}]
    t = tokens.analyse(recs)
    assert round(t["usd"], 6) == 0.2 and t["unpriced"] == 1
    assert "· cost $0.20 (+1 calls without a price) · peak" in tokens.line(t)


def test_health_sums_the_cost_of_each_lane():
    comments = [{"body": "Metrics: ticket #5 · size:S · pr #9 · 10 min\nTokens: 1.2M eq · out 0.03M · cost $4.10 · peak 1k"},
                {"body": "Metrics: ticket #6 · size:S · pr #8 · 20 min · lane haiku\nTokens: 0.8M eq · cost $0.50 · sinks x"},
                {"body": "Tokens: 1.0M eq · calls 9 · sinks base 30%"}]                 # an old line without a cost
    assert health.run_costs(comments) == {"opus": [4.1], "haiku": [0.5]}
