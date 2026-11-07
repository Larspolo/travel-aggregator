"""The pacer starts one refill run per refill source with work, and none for a source with no work (#378)."""
import usage

NOW = 1_800_000_000
OLD = "2026-01-01T00:00:00Z"


def epic(n, open_subs=0):
    return {"number": n, "labels": [{"name": "epic"}], "created_at": OLD, "body": "",
            "sub_issues_summary": {"total": open_subs + 1, "completed": 1}}


# One epic waits for its check; four epics have open sub-issues that wait for the owner (2026-11-06: "refill 3").
ISSUES = [epic(345)] + [epic(n, open_subs=2) for n in (151, 248, 315, 327)]


def test_an_epic_check_with_no_free_source_gets_one_run():
    epics, whole = usage.refill_sources(0, 15, ISSUES, now=NOW)
    assert (epics, whole) == (1, False)
    assert usage.refill_count(0, 15, 0, epics, whole=whole, per=4, most=8) == 1


def test_a_free_source_adds_the_run_of_the_whole_refill():
    epics, whole = usage.refill_sources(0, 15, ISSUES, free=lambda: ["trip:links"], now=NOW)
    assert (epics, whole) == (1, True)
    assert usage.refill_count(0, 15, 0, epics, whole=whole, per=4, most=8) == 2


def test_a_full_queue_does_not_use_the_free_sources():
    assert usage.refill_sources(20, 15, ISSUES, free=lambda: ["trip:links"], now=NOW) == (1, False)


def test_a_release_check_or_a_rank_ticket_is_work_of_the_whole_refill():
    assert usage.refill_sources(20, 15, ISSUES, due=lambda: ["check"], now=NOW) == (1, True)
    ranked = {"number": 9, "labels": [{"name": "rank"}], "created_at": OLD, "body": ""}
    assert usage.refill_sources(20, 15, ISSUES + [ranked], now=NOW) == (1, True)


def test_an_epic_that_closes_by_itself_is_no_source():
    assert usage.refill_sources(0, 15, ISSUES, now=NOW, closing=lambda e: e == 345) == (0, False)
    assert usage.refill_count(0, 15, 0, 0, whole=False) == 0       # a due review gets its run from `fire`
