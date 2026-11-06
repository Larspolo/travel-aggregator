"""framework/tools/ship_pr.py --hold adds the label hold to the PR at once (#3245)."""
import ship_pr as ship
from test_ship_pr import fake_github, repo


def test_hold_labels_the_new_pr(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_github(monkeypatch)
    monkeypatch.setattr(ship, "push", lambda n: True)
    (tmp_path / "body.md").write_text("What changed.")
    args = ["5", "--title", "T", "--body", str(tmp_path / "body.md"), "--tested", "--hold"]
    assert ship.main(args) == 0
    assert ("issues/9/labels", "POST", {"labels": ["hold"]}) in calls
    assert "label hold on PR #9" in capsys.readouterr().out


def test_hold_labels_the_open_pr(tmp_path, monkeypatch):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_github(monkeypatch, open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "push", lambda n: True)
    assert ship.main(["5", "--tested", "--hold"]) == 0
    assert ("issues/9/labels", "POST", {"labels": ["hold"]}) in calls


def test_no_hold_flag_adds_no_label(tmp_path, monkeypatch):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_github(monkeypatch, open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "push", lambda n: True)
    assert ship.main(["5", "--tested"]) == 0
    assert not [c for c in calls if c[0].startswith("issues/")]
