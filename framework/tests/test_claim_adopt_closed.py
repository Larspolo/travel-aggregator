"""framework/tools/claim.py stops a run whose ticket closed after the pacer claimed it (#4249): --adopt and --guard exit 1."""
import claim
from test_claim import clones  # noqa: F401  (fixture)


def test_adopt_and_guard_stop_a_closed_issue(clones, monkeypatch, capsys):  # noqa: F811
    a, _, _ = clones
    states = {"issues/12": {"number": 12, "state": "closed"}, "issues/13": {"number": 13, "state": "open"}}
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path: states.get(path, []))
    monkeypatch.chdir(a)
    assert claim.main(["12", "--adopt", "pacer-x"]) == 1
    assert "#12 is closed" in capsys.readouterr().out
    assert claim.refs(12) == {}                       # no beat commit for a closed ticket
    states["issues/12"] = {"number": 12, "state": "open"}
    assert claim.main(["12"]) == 0                    # claimed while open
    states["issues/12"] = {"number": 12, "state": "closed"}
    assert claim.main(["12", "--guard"]) == 1         # closed during the run: stop
    assert "#12 is closed" in capsys.readouterr().out


def test_guard_goes_on_with_an_open_issue(clones, monkeypatch):  # noqa: F811
    a, _, _ = clones
    states = {"issues/13": {"number": 13, "state": "open"}}
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path: states.get(path, []))
    monkeypatch.chdir(a)
    assert claim.main(["13"]) == 0
    assert claim.main(["13", "--guard"]) == 0
