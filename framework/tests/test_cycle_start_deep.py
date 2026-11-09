"""framework/tools/cycle_start.py names the work of a deep run with no ticket (#1377)."""
import cycle_start as start

HEAD = ("pacer.yml starts the runs: the session starts no run · five_hour 14% (resets Mon 07:00 UTC, 1.1 h, allowed)"
        " · max 16 runs · target 8 runs · claims 1 (0.05 Opus runs) · ready 2 · ")
TAIL = " · paused False · flow ok: 0 waiting PRs, CI queue 0 · max_fire 8 · weights haiku 0.05 (cost)"


def work(refill):
    return start.deep_work(HEAD + refill + TAIL)


def test_a_due_review_names_its_lock():
    got = work("refill 1 (process review due)")
    assert got[0] == "target 8 · claims 1 · refill 1: process review due"
    assert "claim.py 0 --review" in got[1] and len(got) == 2
    got = work("refill 1 (process review and roadmap review due)")
    assert "--review" in got[1] and "--roadmap" in got[2]


def test_an_epic_check_names_the_lock_of_each_epic():
    got = work("refill 2 (epic check #1348, #1352; roadmap review waits for the idle stretch)")
    assert [x.split("`")[1] for x in got[1:]] == ["python3 framework/tools/claim.py 1348 --refill",
                                                   "python3 framework/tools/claim.py 1352 --refill"]


def test_the_whole_refill_takes_the_refill_lock():
    for reason in ("ready 0 < target 16: roadmap trip:find", "rank 2 tickets after the release", "3 release checks"):
        got = work(f"refill 1 ({reason})")
        assert "claim.py 0 --refill" in got[1], reason


def test_no_work_says_go_to_the_report():
    for reason in ("ready 2, target 8: no refill source", "1 refill runs live"):
        assert work(f"refill 0 ({reason})")[1] == "no deep work: go to step 8 (report)"
    assert work("refill 0 (ready 2, target 8: no refill source (x))")[0].endswith("no refill source (x)")


def test_a_broken_line_is_shown():
    assert start.deep_work("usage: error 403")[0].startswith("- (no refill line")
