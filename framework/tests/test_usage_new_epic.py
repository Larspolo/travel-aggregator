"""An epic made less than 10 minutes ago gets no epic check from the refill (#328)."""
import usage

NOW = 1_800_000_000


def iso(seconds_before):
    import datetime
    t = datetime.datetime.fromtimestamp(NOW - seconds_before, datetime.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def epic(number, seconds_before):
    return {
        "number": number,
        "labels": [{"name": "epic"}],
        "sub_issues_summary": {"total": 0, "completed": 0},
        "created_at": iso(seconds_before),
        "body": "",
    }


def test_a_new_epic_gets_no_epic_check():
    assert "epic check" not in usage.refill_need(0, 16, [epic(9, 120)], now=NOW)


def test_an_older_epic_gets_the_epic_check():
    assert usage.refill_need(0, 16, [epic(9, 20 * 60)], now=NOW) == "epic check #9"
