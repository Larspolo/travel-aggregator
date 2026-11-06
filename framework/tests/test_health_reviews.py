"""The review slots in framework/tools/health.py: each process review starts in time, after its gap of merged PRs (#942, #2039)."""
import datetime

import health

T = 1793000000                                  # a unix time
at = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc)


def test_review_delays_from_the_claim_refs():
    lines = [f"review-100pr-20261026T073320Z-1 {T + 3600} Claim review by b",
             f"review-50pr-none-1 {T} Claim review by a",
             f"1704 {T + 60} Claim 1704 by c",                               # a ticket claim: not a review
             "review-90m-332042 1792990000 Claim review 90m-332042 by d",   # a time slot before #2039: not counted
             f"review-200pr-20261026T083320Z-1 {T + 7200} Claim review by e"]
    merged = [at(T + 60 * m) for m in range(1, 120)]                       # one PR each minute
    d = health.review_delays(lines, merged, at(T))
    assert [(g, late) for _, g, late in d] == [(50, None), (100, -40), (200, -141)]
    assert d[0][0] == at(T)
    late = [x for *_, x in health.review_delays(lines, merged, at(T + 1800))]
    assert late == [None, None, -141]                                      # the lock at T is before the period
    assert [x for *_, x in health.review_delays(lines)] == [None, None, None]


def test_the_report_has_the_review_slots():
    since = at(T - 3600)
    reviews = health.review_delays([f"review-50pr-none-1 {T} s", f"review-50pr-x-1 {T + 3600} s"],
                                   [at(T + 60 * m) for m in range(1, 71)], since)
    text = health.report(since, [], [], [], [], [], [], reviews=reviews)
    line = next(x for x in text.splitlines() if x.startswith("Review slots"))
    assert line == f"Review slots (taken UTC, gap PRs, PRs late): {at(T):%m-%d %H:%M} 50 -; {at(T + 3600):%m-%d %H:%M} 50 +10"
    assert "Review slots" not in health.report(since, [], [], [], [], [], [])
