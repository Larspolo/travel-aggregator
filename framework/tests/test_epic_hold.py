"""A single epic check gets no run of its own (owner, option B of #1513, #1596): the pacer starts it with a second
epic, with other refill or review work, when it waited more than `epic_hold_hours`, or when no ticket is ready."""
import datetime

import claim
import usage

NOW = 1_800_000_000


def iso(seconds_before):
    t = datetime.datetime.fromtimestamp(NOW - seconds_before, datetime.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def epic(n, seconds_before=3600):
    return {"number": n, "labels": [{"name": "epic"}], "created_at": iso(seconds_before + 86400),
            "updated_at": iso(seconds_before), "body": "", "sub_issues_summary": {"total": 2, "completed": 2}}


def test_one_young_epic_with_ready_tickets_and_no_other_work_gets_no_run():
    assert usage.refill_need(3, 8, [epic(9)], now=NOW) == ""
    assert usage.refill_need(3, 8, [epic(9)], free=lambda: [], now=NOW) == ""


def test_two_epics_get_one_check():
    assert usage.refill_need(3, 8, [epic(9), epic(12)], now=NOW) == "epic check #9, #12"


def test_one_epic_with_other_work_gets_the_check():
    assert usage.refill_need(3, 8, [epic(9)], reviews=lambda: ["process review"], now=NOW) == "epic check #9"
    assert usage.refill_need(3, 8, [epic(9)], due=lambda: [1], now=NOW) == "epic check #9"
    assert usage.refill_need(3, 8, [epic(9)], free=lambda: ["roadmap"], now=NOW) == "epic check #9"
    assert usage.refill_need(8, 8, [epic(9)], free=lambda: ["roadmap"], now=NOW) == ""   # R >= N: no free source
    rank = {"number": 20, "labels": [{"name": "rank"}], "body": ""}
    assert usage.refill_need(3, 8, [epic(9), rank], now=NOW) == "epic check #9"


def test_one_epic_older_than_the_limit_or_no_ready_ticket_gets_the_check():
    assert usage.refill_need(3, 8, [epic(9, usage.EPIC_HOLD + 60)], now=NOW) == "epic check #9"
    assert usage.refill_need(0, 8, [epic(9)], now=NOW) == "epic check #9"
    partial = {k: v for k, v in epic(9).items() if k not in ("created_at", "updated_at")}
    assert usage.refill_need(3, 8, [partial], now=NOW) == "epic check #9"            # no time: an old epic


def test_a_held_close_check_and_the_pacer_split():
    deep = epic(10)
    deep["labels"].append({"name": "lane:deep"})
    assert usage.refill_need(3, 8, [deep], now=NOW) == ""
    assert usage.refill_need(3, 8, [deep], reviews=lambda: ["roadmap review"], now=NOW) == "close check #10"


def test_a_held_check_is_still_a_refill_source():
    assert usage.refill_need(3, 8, [epic(9)], now=NOW, hold=False) == "epic check #9"
    assert "hold=False" in open(claim.__file__).read()                            # refill_starved: not starved


def test_the_limit_is_a_value_of_pacing():
    assert usage.EPIC_HOLD == usage.CONFIG["pacing"].get("epic_hold_hours", 3) * 3600
