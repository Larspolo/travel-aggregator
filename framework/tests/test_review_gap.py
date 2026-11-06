"""framework/tools/claim.py --review: the process review waits for merged PRs, never for hours (owner, 2026-10-29; #3465 had a
4-hour floor)."""
import claim

LAST = "2026-10-28T12:00:00Z"


def test_the_review_slot_counts_only_merged_prs():
    assert claim.pr_slot(LAST, 200, 199) is None                                     # too few PRs
    assert claim.pr_slot(LAST, 200, 200) == "200pr-20261028T120000Z-1"              # at once, at any time
    assert claim.pr_slot(None, 200, 200) == "200pr-none-1"                          # no review yet


def test_an_unfinished_review_at_a_small_gap_opens_again_after_the_first_gap():
    assert claim.pr_slot(LAST, 10, 89, 80) == claim.pr_slot(LAST, 10, 10, 80) == "10pr-20261028T120000Z-1"
    assert claim.pr_slot(LAST, 10, 90, 80) == "10pr-20261028T120000Z-2"            # not a second review at 20 PRs
