"""A deep run does the close checks of the epics in batches (#2178, option 3 of #1746)."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "framework" / "tools"))
import usage  # noqa: E402

NOW = datetime.datetime(2026, 11, 11, 12, 0, tzinfo=datetime.timezone.utc).timestamp()


def epic(n, minutes):
    at = datetime.datetime.fromtimestamp(NOW - minutes * 60, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"number": n, "updated_at": at, "created_at": "2026-11-01T00:00:00Z",
            "labels": [{"name": "epic"}, {"name": "lane:deep"}]}


def test_one_new_epic_waits():
    assert usage.close_batch([1], [epic(1, 30)], NOW) == []
    assert "close check" not in usage.refill_need(5, 5, [epic(1, 30)], now=NOW, hold=False)


def test_two_epics_get_one_check():
    issues = [epic(1, 30), epic(2, 10)]
    assert usage.close_batch([1, 2], issues, NOW) == [1, 2]
    assert usage.refill_need(5, 5, issues, now=NOW, hold=False) == "close check #1, #2"


def test_one_old_epic_gets_its_check():
    assert usage.close_batch([1], [epic(1, 121)], NOW) == [1]
    assert usage.refill_need(5, 5, [epic(1, 121)], now=NOW, hold=False) == "close check #1"
