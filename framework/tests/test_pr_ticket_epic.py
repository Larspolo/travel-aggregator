"""A body that names its epic with "Part of #E" still closes the ticket of the PR (#5144)."""
from framework.tools.pr_ticket import ticket


def test_epic_part_of_closes_title_ticket():
    assert ticket("Part of #4526. Ticket: #5100.", "", "x (#5100)", {}) == (5100, True)


def test_epic_part_of_closes_claim_ticket():
    assert ticket("Ticket #4970. Part of #4831.", "Part of #4831", "x", {4970: "Claim #4970 by b"}) == (4970, True)


def test_part_of_the_ticket_keeps_it_open():
    assert ticket("Part of #4", "Part of #4", "x (#4)", {4: "Claim #4 by b"}) == (None, False)
    assert ticket("Part of #4", "fixes #4", "x", {}) == (None, False)
