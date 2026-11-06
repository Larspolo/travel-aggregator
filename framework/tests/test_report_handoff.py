"""`report.py --post` gives back the claim of a reported ticket that no open PR closes (#5462): #5228 and #5413 kept
their claims after a `Part of` PR merged, and each one waited 30 minutes for a takeover."""
import report

ME = "claude/x-2"


def pr(body):
    return {"number": 50, "body": body}


def test_handoffs_takes_the_own_open_claims_with_no_closing_pr():
    claims = {1: f"Beat #1 by {ME} lane deep", 2: f"Claim #2 by {ME} (abc)", 3: f"Release #3 by {ME}",
              4: "Beat #4 by claude/other", 5: f"Beat #5 by {ME}"}
    pulls = [pr("Part of #1"), pr("Closes #2"), pr("`Closes #5` in code")]
    assert report.handoffs([1, 2, 3, 4, 5, 6, 1], claims, pulls, ME) == [1, 5]


def test_hand_off_releases_and_removes_the_label(monkeypatch, capsys):
    done = []
    monkeypatch.setattr(report.claim, "refs", lambda n: {1: "a", 2: "b"} if n == 7 else {})
    monkeypatch.setattr(report.claim, "subject", lambda ref: f"Beat #7 by {ME}" if ref == "claim/7-2" else "")
    monkeypatch.setattr(report.claim, "who", lambda: ME)
    monkeypatch.setattr(report, "pages", lambda path: [pr("Part of #7")])
    monkeypatch.setattr(report.claim, "release", lambda n: done.append(("release", n)) or f"claim/{n}-2")
    monkeypatch.setattr(report.claim, "stop", lambda n: done.append(("stop", n)))
    report.hand_off([7, 8])
    assert done == [("release", 7), ("stop", 7)] and "released #7" in capsys.readouterr().out


def test_hand_off_never_stops_the_report(monkeypatch, capsys):
    monkeypatch.setattr(report.claim, "refs", lambda n: {1: "a"})
    monkeypatch.setattr(report.claim, "subject", lambda ref: f"Beat #7 by {ME}")
    monkeypatch.setattr(report.claim, "who", lambda: ME)
    monkeypatch.setattr(report, "pages", lambda path: [])
    monkeypatch.setattr(report.claim, "release", lambda n: exit("claim/7 belongs to another run"))
    report.hand_off([7])
    assert "no hand-off: claim/7 belongs to another run" in capsys.readouterr().err
