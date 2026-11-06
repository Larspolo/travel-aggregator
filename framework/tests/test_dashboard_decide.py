"""A decision ticket ("Decide: ...") is never a candidate, also without `needs-human` (#1569)."""
import dashboard


def issue(n, title, *names):
    return dict(number=n, title=title, labels=[{"name": x} for x in ("P2",) + names], body="")


def test_a_decision_ticket_is_no_candidate():
    issues = [issue(1, "Decide: how does a gate open", "P0"), issue(2, "Train the camel rider"),
              issue(3, "Decide: the fog", "needs-human"), issue(4, "Check the decide button")]
    assert [i["number"] for i in dashboard.candidates(issues)] == [2, 4]
