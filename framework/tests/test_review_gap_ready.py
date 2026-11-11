"""framework/tools/claim.py: the floor of the process review gap follows the ready queue (#1597, P9). Many ready tickets:
a review takes quota from them, so it comes later; few: a review costs no ticket."""
import claim


def test_a_change_at_the_floor_gives_the_count_of_ready_tickets_between_the_limits():
    assert claim.next_gap(10, True, 3) == 10               # few ready tickets: min_gap
    assert claim.next_gap(10, True, 25) == 25
    assert claim.next_gap(10, True, 60) == 40              # many ready tickets: max_min_gap
    assert claim.next_gap(10, True, None) == 10            # GitHub cannot be read


def test_a_gap_above_the_floor_halves_down_to_it_and_no_change_still_doubles():
    assert claim.next_gap(80, True, 25) == 40
    assert claim.next_gap(40, True, 25) == 25
    assert claim.next_gap(20, True, 3) == 10
    assert claim.next_gap(25, False, 25) == 80             # below `gap`: back to `gap`
    assert claim.next_gap(320, False, 60) == 640
    assert claim.next_gap(640, False, 60) == 640           # max_gap


def test_the_state_keeps_each_gap_of_the_new_rule():
    assert claim.review_gap({"review_prs": 25}) == 25
    assert claim.review_gap({"review_prs": 40}) == 40
    assert claim.review_gap({"review_prs": 10}) == 10
    assert claim.review_gap({"review_prs": 200}) == 80     # an earlier rule: back to `gap`


def test_the_review_stores_the_gap_of_the_ready_queue():
    body = '<!-- agent-state: {"review_prs": 10} -->'
    assert claim.agent_state(claim.reviewed(body, True, ready=25))["review_prs"] == 25
    assert claim.agent_state(claim.reviewed(body, True))["review_prs"] == 10
