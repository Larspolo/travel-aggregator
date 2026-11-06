"""framework/tools/ship_pr.py --part: a new PR says "Part of #N" and does not close its ticket (#3324)."""
import claim
import ship_pr as ship
from test_ship_pr import fake_github, repo


def test_part_does_not_close_the_ticket(tmp_path, monkeypatch):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_github(monkeypatch)
    monkeypatch.setattr(ship, "push", lambda n: True)
    (tmp_path / "body.md").write_text("What changed.")
    assert ship.main(["5", "--title", "T", "--body", str(tmp_path / "body.md"), "--tested", "--part"]) == 0
    body = next(d["body"] for path, method, d in calls if path == "pulls" and method == "POST")
    assert body.endswith("Part of #5\n") and not claim.closes(5).search(claim.prose(body))


def test_part_keeps_a_body_that_names_it():
    assert ship.body_with_ticket("Part of #5: the tool.", 5, part=True) == "Part of #5: the tool."
