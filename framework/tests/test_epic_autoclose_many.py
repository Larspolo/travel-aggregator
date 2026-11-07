"""An epic check that waits for more than one ticket ends with `Close this epic when #N and #M merge.` (#617): the epic
closes by itself when all of them merged, and the pacer skips its check then."""
import epic_autoclose
from test_epic_autoclose import NOW, agent, epic

TWO = "Epic check: criteria 1 to 5 are met. Open: the whole test (#609) and the README (#610).\n\n" \
      "Close this epic when #609 and #610 merge."


def select(body, closed):
    return [(e, ns, prs) for e, ns, prs, _ in epic_autoclose.select([epic()], lambda e: [agent(body)], closed.get, now=NOW)]


def test_two_merged_tickets_close_the_epic():
    assert select(TWO, {609: 613, 610: 614}) == [(9, (609, 610), (613, 614))]


def test_one_open_ticket_of_two_keeps_the_epic_check():
    assert select(TWO, {609: 613}) == []
    assert select(TWO, {610: 614}) == []


def test_the_forms_of_a_list():
    for line, ns in [("Close this epic when #1, #2 and #3 merge.", (1, 2, 3)),
                     ("Close this epic when #1, #2, and #3 merge.", (1, 2, 3)),
                     ("Close this epic after #4 and #5 merge.", (4, 5)),
                     ("Close this epic when #6 merges.", (6,))]:
        assert epic_autoclose.close_line([agent(line)]) == ns, line


def test_the_evidence_names_each_ticket_and_pr():
    text = epic_autoclose.evidence((609, 610), (613, 614), {"html_url": "https://x/c/2"})
    assert "#609 and #610" in text and "PR #613 and PR #614" in text and "merged them" in text


def test_ready_needs_each_ticket(monkeypatch):
    monkeypatch.setattr(epic_autoclose, "comments_of", lambda e: [agent(TWO)])
    monkeypatch.setattr(epic_autoclose, "merged_pr", {609: 613}.get)
    assert epic_autoclose.ready(9) is None
    monkeypatch.setattr(epic_autoclose, "merged_pr", {609: 613, 610: 614}.get)
    assert epic_autoclose.ready(9) == ((609, 610), (613, 614))
