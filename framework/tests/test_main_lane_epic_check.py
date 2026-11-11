"""The main lane does the epic checks, the deep lane only the close check of an epic (#1595, decision #1513): a main
run that finds all criteria met adds `lane:deep`, and a deep run checks again and closes."""
import claim
import cycle_start
import usage
from test_claim import clones  # noqa: F401 (fixture)

NOW = 1_800_000_000
LANES = [("haiku", 0, 0.25), ("deep", 0, 4.0)]


def epic(n, *names):
    return {"number": n, "labels": [{"name": x} for x in ("epic", *names)], "created_at": "2026-01-01T00:00:00Z",
            "body": "", "sub_issues_summary": {"total": 2, "completed": 2}}


def test_a_main_run_locks_an_epic_check_but_not_the_deep_work(clones, monkeypatch, capsys):  # noqa: F811
    monkeypatch.chdir(clones[0])
    monkeypatch.setitem(claim.CONFIG["pacing"], "reserved", ["haiku", "deep"])
    monkeypatch.setattr(claim, "lane", lambda: "")
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    issues = {9: epic(9), 10: epic(10, "lane:deep"), 11: {"number": 11, "labels": [{"name": "size:L"}]}}
    monkeypatch.setattr(claim, "api", lambda path: issues[int(path.rsplit("/", 1)[1])])
    assert not claim.deep_lane()
    assert claim.main(["9", "--refill", "--state", "2"]) == 0                    # the epic check
    assert "claimed refill 9-2" in capsys.readouterr().out
    assert claim.main(["10", "--refill", "--state", "2"]) == 1                   # the close check: deep
    assert "the deep lane does the close check or split" in capsys.readouterr().out
    assert claim.main(["11", "--refill", "--state", "0"]) == 1                   # the split of a size:L ticket: deep
    assert claim.main(["0", "--refill"]) == 1                                    # the whole refill: deep
    assert "the deep lane does the queue refill" in capsys.readouterr().out


def test_main_check_reads_the_labels():
    assert claim.main_check(epic(9))
    assert not claim.main_check(epic(9, "lane:deep"))
    assert not claim.main_check({"labels": [{"name": "size:L"}]})
    assert not claim.main_check(None)


def test_the_pacer_plans_a_main_run_for_an_epic_check_and_a_deep_run_for_a_close_check():
    main = usage.refill_split(0, 8, [epic(9)], [], NOW)
    assert main == (0, 1)
    assert usage.plan(8, 0, 0, LANES, False, refill=main[0], refill_lane="deep", main_refill=main[1]) == (
        1, {"haiku": 0, "deep": 0})                                              # one main run
    deep = usage.refill_split(0, 8, [epic(9, "lane:deep")], [], NOW)
    assert deep == (1, 0)
    assert usage.plan(8, 0, 0, LANES, False, refill=deep[0], refill_lane="deep", main_refill=deep[1]) == (
        1, {"haiku": 0, "deep": 1})                                              # one deep run
    assert usage.refill_need(0, 8, [epic(9), epic(10, "lane:deep")], now=NOW) == "epic check #9; close check #10"
    assert usage.refill_split(0, 8, [epic(9)], [], NOW, refill_lane=None) == (1, 0)   # no deep lane: as before


def test_each_lane_counts_only_its_own_live_refill_locks():
    lines = [f"refill-9-2 {NOW - 60} Claim refill 9-2 by ccr-main (1)",
             f"refill-0-x {NOW - 60} Claim refill 0-x by ccr-deep (2) lane deep"]
    assert usage.refill_live(lines, NOW) == 2
    assert usage.refill_live(lines, NOW, lane="main") == 1
    assert usage.refill_live(lines, NOW, lane="deep") == 1
    assert usage.refill_split(0, 8, [epic(9), epic(10, "lane:deep")], lines[:1], NOW) == (1, 0)   # 9 is live
    assert usage.pending({"main": 1}, lines[:1], NOW) == {}                      # the main run of the check claimed


def test_cycle_start_gives_a_main_run_the_epic_checks_only():
    line = ("target 8 runs · claims 1 (0.05 Opus runs) · ready 0 · refill 2 (epic check #9, #12; close check #10)"
            " · paused False · flow ok")
    got = cycle_start.deep_work(line, "main")
    assert [x.split("`")[1] for x in got[1:]] == ["python3 framework/tools/claim.py 9 --refill",
                                                   "python3 framework/tools/claim.py 12 --refill"]
    assert [x.split("`")[1] for x in cycle_start.deep_work(line)[1:]] == ["python3 framework/tools/claim.py 10 --refill"]
    assert cycle_start.deep_work(line.replace("epic check #9, #12; ", ""), "main")[1] == \
        "no epic check: go to step 8 (report)"
