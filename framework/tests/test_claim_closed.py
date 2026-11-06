"""framework/tools/claim.py does not claim a closed issue (#2339): the candidate list can name a ticket that closed seconds ago."""
import claim
from test_claim import clones  # noqa: F401  (fixture)


def test_no_claim_of_a_closed_issue(clones, monkeypatch, capsys):  # noqa: F811
    a, _, _ = clones
    states = {"issues/12": {"number": 12, "state": "closed"}, "issues/13": {"number": 13, "state": "open"}}
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path: states.get(path, []))
    monkeypatch.chdir(a)
    assert claim.main(["12"]) == 1 and claim.refs(12) == {}
    assert "#12 is closed" in capsys.readouterr().out
    assert claim.main(["12", "--takeover"]) == 1 and claim.refs(12) == {}
    assert claim.main(["13"]) == 0
