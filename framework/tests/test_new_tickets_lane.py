"""`new_tickets.py` stops a `size:S` ticket with no lane (#2129: the `ticket` skill, "Model lanes")."""
import pytest

import new_tickets


def block(labels, extra=""):
    return f"# The ticket\nlabels: {labels}\n{extra}\n## Goal\ng\n\n## Acceptance criteria\n- [ ] c\n"


def test_a_size_s_ticket_with_no_lane_stops_before_any_ticket():
    text = block("P2, docs, size:M") + block("P2, docs, size:S")
    with pytest.raises(ValueError, match="'The ticket': a size:S ticket gets lane:haiku"):
        new_tickets.parse(text)


@pytest.mark.parametrize("labels", ["P2, size:S, lane:haiku", "P2, size:S, lane:deep", "P2, size:M",
                                    "P2, size:S, epic", "P2, size:S, decision, needs-human"])
def test_a_lane_label_another_size_an_epic_or_a_decision_passes(labels):
    assert new_tickets.parse(block(labels))[0]["labels"] == [x.strip() for x in labels.split(",")]


def test_lane_main_with_a_reason_passes_and_adds_no_label():
    t = new_tickets.parse(block("P2, feature, size:S", "lane: main the row needs a screenshot"))[0]
    assert t["labels"] == ["P2", "feature", "size:S"] and t["lane"] == "main the row needs a screenshot"
    assert t["body"].startswith("## Goal")


@pytest.mark.parametrize("line", ["lane: main", "lane: haiku", "lane:"])
def test_a_lane_line_without_main_and_a_reason_stops(line):
    with pytest.raises(ValueError, match="write 'lane: main <reason>'"):
        new_tickets.parse(block("P2, feature, size:S", line))


def test_main_prints_the_error_and_makes_nothing(tmp_path, capsys):
    f = tmp_path / "t.md"
    f.write_text(block("P2, size:S"))
    assert new_tickets.main([str(f)]) == 1
    assert "lane:haiku" in capsys.readouterr().err
