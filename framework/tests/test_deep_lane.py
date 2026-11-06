"""The deep lane: Opus runs at the default effort for the hard tickets, the reviews and the refill, while the main runs
work at low effort (owner, 2026-10-28)."""
import claim
import dashboard
import usage


def issue(n, *names):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": x} for x in names], body="")


def test_the_pacer_gives_each_lane_its_tickets_and_the_deep_lane_the_refill():
    lanes = [("haiku", 2, 0.25), ("deep", 1, 4.0)]
    assert usage.plan(10, 0, 10, lanes, False, hi=8, refill=1, refill_lane="deep") == (5, {"haiku": 2, "deep": 2})
    assert usage.plan(10, 0, 10, lanes, False, hi=8, refill=1) == (8, {"haiku": 2, "deep": 1})    # the main runs refill
    assert usage.plan(3, 0, 10, lanes, False, hi=8, refill=1, refill_lane="deep") == (3, {"haiku": 2, "deep": 1})   # small room
    assert usage.plan(3, 2.5, 10, lanes, False, hi=8) == (2, {"haiku": 2, "deep": 0})      # less than one Opus run of room
    assert usage.plan(10, 0, 10, lanes, True) == (0, {"haiku": 0, "deep": 0})                # paused
    assert usage.lane_plan(2, 0, 10, 1, 0.25, False, hi=8) == usage.plan(2, 0, 10, [("haiku", 1, 0.25)], False, hi=8)[:1] + (1,)


def test_only_deep_runs_do_the_reviews_and_the_refill(monkeypatch, capsys):
    monkeypatch.setattr(claim, "who", lambda: "claude/lane-test")          # a branch, not a detached HEAD (#155)
    monkeypatch.setitem(claim.CONFIG["pacing"], "reserved", ["haiku", "deep"])
    monkeypatch.setattr(claim, "lane", lambda: "")
    assert not claim.deep_lane()
    for flag in ("--review", "--roadmap", "--refill"):
        assert claim.main(["0", flag]) == 1
    assert "the deep lane does the queue refill" in capsys.readouterr().out
    monkeypatch.setattr(claim, "lane", lambda: " lane deep")
    assert claim.deep_lane()
    monkeypatch.setitem(claim.CONFIG["pacing"], "reserved", ["haiku"])
    monkeypatch.setattr(claim, "lane", lambda: "")
    assert claim.deep_lane()                                                     # no deep lane: every run


def test_a_main_run_never_takes_a_deep_ticket():
    issues = [issue(1, "P0", "lane:deep"), issue(2, "P2")]
    assert [i["number"] for i in dashboard.candidates(issues, reserved=("haiku", "deep"))] == [2]
    assert [i["number"] for i in dashboard.candidates(issues, lane="deep")] == [1]
