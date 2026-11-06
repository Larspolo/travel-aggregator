"""Pick order by the overlap with the work in progress (#487), with fixture data (no network)."""
import dashboard


def issue(n, *names, body="", **kw):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": x} for x in names], body=body, **kw)


def test_names():
    text = ("In `buildings.py`: `hut()` and `app.convert()`; run `tools/render.py building HUT OUT.png`. "
            "Edit `docs/DESIGN.md` and `game/gather.py`. Not names: `--next`, `HUT_A`, `x = 3`, `LEARNINGS.md`.")
    assert dashboard.names(text) == {"buildings.py", "hut()", "convert()", "DESIGN.md", "gather.py"}
    assert dashboard.names(None) == set()


def test_work_takes_claimed_tickets_and_pr_files():
    issues = [issue(1, "P2", "in-progress", body="Change `furnish()` in `buildings.py`."),
              issue(2, "P2", body="Change `game/run.py`."), issue(3, pull_request={}, body="`units.py`")]
    busy = dashboard.work(issues, {3: ["framework/tools/dashboard.py", "docs/DESIGN.md"]})
    assert busy == {"furnish()", "buildings.py", "dashboard.py", "DESIGN.md"}


def test_less_overlap_first_within_a_priority():
    busy = {"buildings.py", "DESIGN.md", "furnish()"}
    issues = [issue(5, "P2", body="`buildings.py`, `docs/DESIGN.md`, `furnish()`"),
              issue(6, "P2", body="`buildings.py`"), issue(7, "P2", body="`game/gather.py`"),
              issue(8, "P3", body="`units.py`"), issue(4, "P1", body="`buildings.py` and `furnish()`")]
    # the priority stays first; in P2: overlap 0 (#7), 1 (#6), 3 (#5); the ticket number breaks a tie
    assert [i["number"] for i in dashboard.candidates(issues, busy)] == [4, 7, 6, 5, 8]
    assert dashboard.overlap(issues[0], busy) == ["DESIGN.md", "buildings.py", "furnish()"]
    assert [i["number"] for i in dashboard.candidates(issues)] == [4, 5, 6, 7, 8]       # no work: number order


def test_next_prints_overlap(monkeypatch, capsys):
    data = {"issues?state=open": [issue(1, "P2", "in-progress", body="`buildings.py`"),
                                  issue(2, "P2", body="`buildings.py`"), issue(3, "P2", body="`units.py`"),
                                  issue(9, pull_request={})],
            "pulls/9/files": [{"filename": "units.py"}, {"filename": "framework/tools/claim.py"}]}
    monkeypatch.setattr(dashboard, "pages", lambda path, limit=10: data[path])
    import health
    monkeypatch.setattr(health, "claim_refs", lambda: [])        # a live claim on origin must not change the test
    assert dashboard.main(["--next"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["#2 Ticket 2 (P2, None, overlap 1: buildings.py)", "#3 Ticket 3 (P2, None, overlap 1: units.py)"]
