"""`new_tickets.py`: several tickets, their labels and sub-issue links in one call (owner, 2026-11-06)."""
import pytest

import new_tickets

FILE = """# Make the epic
labels: epic, P2

## Goal
All of it.

## Acceptance criteria
- [ ] All parts.

## Cases
- part one: #new2
- part two: #new3

# Make the first part
labels: P2, feature, size:S, lane:haiku
parent: #new1

## Goal
Part one.

## Acceptance criteria
- [ ] One.

# Make the second part
labels: P2, size:S
lane: main the row needs a screenshot
parent: new1

## Goal
Part two.

## Acceptance criteria
- [ ] Two.

Depends on: #new2
"""


def fake_api():
    calls = []

    def api(path, method="GET", data=None):
        calls.append((path, method, data))
        if path == "issues":
            n = 100 + sum(1 for p, *_ in calls if p == "issues")
            return {"number": n, "id": n * 10}
        return {}
    return api, calls


def test_parse_reads_the_blocks():
    ts = new_tickets.parse(FILE)
    assert [t["title"] for t in ts] == ["Make the epic", "Make the first part", "Make the second part"]
    assert ts[1]["labels"] == ["P2", "feature", "size:S", "lane:haiku"] and ts[1]["parent"] == "new1"
    assert ts[0]["parent"] is None and ts[2]["body"].startswith("## Goal\nPart two.")


def test_make_links_the_new_numbers():
    api, calls = fake_api()
    lines = []
    new_tickets.make(new_tickets.parse(FILE), api=api, out=lines.append)
    assert ("issues/101/sub_issues", "POST", {"sub_issue_id": 1020}) in calls
    assert ("issues/101/sub_issues", "POST", {"sub_issue_id": 1030}) in calls
    third = [d for p, m, d in calls if p == "issues"][2]
    assert "Depends on: #102" in third["body"] and third["labels"] == ["P2", "size:S"]
    assert lines == ["#101 Make the epic", "#102 Make the first part (sub-issue of #101)",
                     "#103 Make the second part (sub-issue of #101)"]


def spec(title, extra="", body="g"):
    return f"# {title}\n{extra}\n## Goal\n{body}\n\n## Acceptance criteria\n- [ ] c\n\n"


def test_a_body_names_a_later_ticket_and_is_patched_once():
    text = spec("A", body="See #new3.") + spec("B") + spec("C")
    api, calls = fake_api()
    new_tickets.make(new_tickets.parse(text), api=api, out=lambda s: None)
    assert len([c for c in calls if c[0] == "issues"]) == 3
    patches = [c for c in calls if c[1] == "PATCH"]
    assert len(patches) == 1 and patches[0][0] == "issues/101"
    assert "See #103." in patches[0][2]["body"] and "#new3" not in patches[0][2]["body"]


def test_a_number_beyond_the_file_makes_no_call(tmp_path, monkeypatch, capsys):
    path = tmp_path / "t.md"
    path.write_text(spec("A", body="See #new9.") + spec("B") + spec("C"))
    monkeypatch.setattr(new_tickets.dashboard, "api", lambda *a, **k: pytest.fail("a call was made"))
    assert new_tickets.main([str(path), "--dry-run"]) == 1
    assert "#new9 in ticket 1" in capsys.readouterr().err
    assert capsys.readouterr().out == ""


def test_a_later_parent_stops_all():
    api, calls = fake_api()
    with pytest.raises(ValueError, match="parent: #new2 in ticket 1"):
        new_tickets.make(new_tickets.parse(spec("A", "parent: #new2") + spec("B")), api=api, out=lambda s: None)
    assert calls == []


def test_a_self_reference_stops_all():
    api, calls = fake_api()
    with pytest.raises(ValueError, match="#new1 in ticket 1"):
        new_tickets.make(new_tickets.parse(spec("A", body="See #new1.") + spec("B")), api=api, out=lambda s: None)
    assert calls == []


def test_text_before_the_first_title_stops():
    with pytest.raises(ValueError, match="before the first"):
        new_tickets.parse("labels: P2\n# A\n")


def test_an_existing_parent():
    api, calls = fake_api()
    new_tickets.make(new_tickets.parse("# A\nparent: #94\n\n## Goal\ng\n\n## Acceptance criteria\n- [ ] c\n"), api=api, out=lambda s: None)
    assert calls[-1] == ("issues/94/sub_issues", "POST", {"sub_issue_id": 1010})


def test_a_ticket_without_the_spec_stops_all():
    with pytest.raises(ValueError, match="'B': a new issue needs"):
        new_tickets.parse("# A\n\n## Goal\ng\n\n## Acceptance criteria\n- [ ] c\n\n# B\n\n## Goal\nonly a goal\n")
