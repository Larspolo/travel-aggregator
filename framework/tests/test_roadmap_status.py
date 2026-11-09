import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import roadmap_status  # noqa: E402

TEXT = """# Goals
- [ ] `a:done` Done but not marked
- [ ] `a:open` Epic still open
- [ ] `a:none` No epic
- [x] `a:old` (#5) Marked with number
- [x] `a:nonum` Marked with no number
"""
EPICS = [
    {"number": 10, "state": "closed", "state_reason": "completed", "body": "Roadmap: `a:done`"},
    {"number": 11, "state": "open", "body": "Goal\nRoadmap: `a:open`"},
    {"number": 5, "state": "closed", "state_reason": "completed", "body": "Roadmap: `a:old`"},
    {"number": 12, "state": "closed", "state_reason": "completed", "body": "Roadmap: `a:nonum`"},
]


def test_three_kinds():
    assert roadmap_status.status(TEXT, EPICS) == [
        "mark done: a:done (#10)", "no epic: a:none", "no number: a:nonum"]


def test_not_planned_is_not_done():
    epics = [{"number": 10, "state": "closed", "state_reason": "not_planned", "body": "Roadmap: `a:done`"}]
    assert "mark done: a:done (#10)" not in roadmap_status.status(TEXT, epics)
