"""A ticket with a "Start after:" line is no candidate before that time (#496)."""
import datetime

import dashboard


def issue(n, body=""):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": "P2"}], body=body)


def test_start_after():
    issues = [issue(1, "## Goal\nStart after: 2026-10-27 05:15 UTC\n"), issue(2), issue(3, "Start after: 2026-10-28"),
              issue(4, 'Text: "Start after: 2099-01-01" in a sentence.')]
    utc = datetime.timezone.utc
    pick = lambda t: [i["number"] for i in dashboard.candidates(issues, now=t)]
    assert pick(datetime.datetime(2026, 10, 27, 5, 14, tzinfo=utc)) == [2, 4]
    assert pick(datetime.datetime(2026, 10, 27, 5, 15, tzinfo=utc)) == [1, 2, 4]
    assert pick(datetime.datetime(2026, 10, 28, 0, 0, tzinfo=utc)) == [1, 2, 3, 4]
    assert dashboard.start_after(issues[1]) is None
