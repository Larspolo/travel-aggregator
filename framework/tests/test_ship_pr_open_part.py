"""ship_pr.py stops a PR body that says a part of the ticket is not covered and names no ticket (#2486, #2408)."""
import ship_pr as ship
from test_ship_pr import fake_github, repo


def test_the_lines_of_the_merged_prs_match():
    assert ship.open_part("ok\nThe rail pass part is not in the test: the case is not covered yet.\n")
    assert ship.open_part("## Not covered\n- the exact price.\n") == "## Not covered"
    assert ship.open_part("- Not covered by a test here: the part on a real trip page.")


def test_a_named_ticket_a_verify_level_and_other_text_pass():
    assert ship.open_part("The rail pass case is not covered here. Follow-up: #2512") is None
    assert ship.open_part("- Not done: a uvicorn run (level 3) and screenshots (level 4).") is None
    assert ship.open_part("## What changed\n- The covered pass gives no price.\n") is None


def test_main_stops_before_the_commit(tmp_path, monkeypatch):
    work = repo(tmp_path)
    monkeypatch.chdir(work)
    calls = fake_github(monkeypatch)
    body = work / "BODY.md"
    body.write_text("## What changed\n- x\n\nThe case of the rail pass is not tested.\n")
    assert ship.main(["5", "--title", "T", "--body", str(body)]) == 2
    assert calls == []
