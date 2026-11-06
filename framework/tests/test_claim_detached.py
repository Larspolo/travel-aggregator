"""framework/tools/claim.py: a claim on a detached HEAD stops (exit 2) instead of claiming as `unknown` (#155)."""
import claim


def test_claim_on_detached_head_exits_2_and_claims_nothing(monkeypatch, capsys):
    monkeypatch.setattr(claim, "who", lambda: "unknown")

    def no_claim(*args, **kwargs):
        raise AssertionError("a claim on a detached HEAD must not reach the push")
    monkeypatch.setattr(claim, "claim_ticket", no_claim)
    monkeypatch.setattr(claim, "claim_comment", no_claim)

    assert claim.main(["155"]) == 2
    assert claim.main(["155", "--or", "156"]) == 2
    assert claim.main(["155", "--comment"]) == 2
    assert "check out your branch first" in capsys.readouterr().out


def test_claim_on_a_branch_claims_as_before(monkeypatch):
    monkeypatch.setattr(claim, "who", lambda: "claude/wizardly-ramanujan-mb95da-2")
    calls = []
    monkeypatch.setattr(claim, "claim_ticket", lambda number, takeover, remote: calls.append(number) or 0)

    assert claim.main(["155"]) == 0
    assert calls == [155]


def test_beat_and_guard_stay_as_they_are_on_a_detached_head(monkeypatch, capsys):
    monkeypatch.setattr(claim, "who", lambda: "unknown")
    monkeypatch.setattr(claim, "release", lambda number, remote, word="Release": "claim/155")

    assert claim.main(["155", "--beat"]) == 0
    assert "beat claim/155" in capsys.readouterr().out
