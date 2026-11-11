"""`new_tickets.py` stops an epic with sub-issues in the file and no `## Cases` map (#2415: 5 of 6 deep close checks
found a case of the whole goal that no sub-issue named)."""
import pytest

import new_tickets


def epic(cases=""):
    return f"# The epic\nlabels: epic, P3\n\n## Goal\ng\n\n## Acceptance criteria\n- [ ] all cases\n{cases}\n"


def sub(title="The part", parent="new1"):
    return (f"# {title}\nlabels: P3, size:M\nparent: {parent}\n\n## Goal\ng\n\n## Acceptance criteria\n- [ ] c\n")


def test_an_epic_with_sub_issues_and_no_cases_stops():
    with pytest.raises(ValueError, match="epic 1 'The epic': add '## Cases'"):
        new_tickets.check(new_tickets.parse(epic() + sub()))


def test_a_case_that_names_no_sub_issue_of_the_epic_stops():
    text = epic("\n## Cases\n- the form: #new2\n- the next trip copies it\n") + sub()
    with pytest.raises(ValueError, match="the case 'the next trip copies it' names no sub-issue"):
        new_tickets.check(new_tickets.parse(text))


def test_a_case_that_names_another_ticket_of_the_file_stops():
    text = epic("\n## Cases\n- the form: #new3\n") + sub() + sub("Other", parent="2396")
    with pytest.raises(ValueError, match="its sub-issues: #new2"):
        new_tickets.check(new_tickets.parse(text))


def test_each_case_with_a_sub_issue_or_an_open_issue_passes():
    text = epic("\n## Cases\n- the form: #new2\n- the export: #new3\n- the README: #2401\n") + sub() + sub("B")
    new_tickets.check(new_tickets.parse(text))


def test_an_epic_alone_and_sub_issues_of_an_older_epic_pass():
    new_tickets.check(new_tickets.parse(epic()))
    new_tickets.check(new_tickets.parse(sub(parent="2396") + sub("B", parent="2396")))


def test_main_prints_the_error_and_makes_nothing(tmp_path, capsys):
    f = tmp_path / "t.md"
    f.write_text(epic() + sub())
    assert new_tickets.main([str(f)]) == 1
    assert "## Cases" in capsys.readouterr().err
