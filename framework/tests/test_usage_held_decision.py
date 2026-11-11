"""A roadmap feature whose line names an open decision ticket is no refill source: the `roadmap` skill makes its epic
only after the owner's answer (#432: `trip:notify` named #418, and the pacer started deep refill runs for nothing)."""
import sys

import dashboard
import pytest
import usage

ROADMAP = """# Roadmap

## 3. Plan a trip

- [ ] `trip:notify` Notifications by the channel of the decision #418
- [ ] `trip:bus` A bus source with the payload of #419
"""

DECISION = "## Goal\nX.\n\n## For the owner\nKind: decision\n1. Reply with A or B."
INPUT = "## Goal\nX.\n\n## For the owner\nKind: outside\n1. Capture a payload."


def issue(state, labels, body):
    return {"state": state, "labels": [{"name": n} for n in labels], "body": body}


@pytest.fixture
def no_release(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "release", None)                  # `import release` raises ImportError
    (tmp_path / "ROADMAP.md").write_text(ROADMAP)
    monkeypatch.setitem(usage.CONFIG, "docs", {"roadmap": "ROADMAP.md"})
    return tmp_path


def stub(monkeypatch, issues):
    monkeypatch.setattr(dashboard, "api", lambda path: issues[int(path.rsplit("/", 1)[1])])


def test_an_open_decision_holds_the_feature(monkeypatch):
    stub(monkeypatch, {418: issue("open", ["needs-human", "for-jeroen"], DECISION)})
    assert usage.held({418})


def test_an_answered_or_closed_decision_does_not_hold_it(monkeypatch):
    stub(monkeypatch, {418: issue("open", ["feature"], DECISION), 420: issue("closed", ["needs-human"], DECISION)})
    assert not usage.held({418})                                         # the owner answered and removed `needs-human`
    assert not usage.held({420})


def test_an_owner_input_ticket_does_not_hold_it(monkeypatch):
    stub(monkeypatch, {419: issue("open", ["needs-human"], INPUT)})      # the epic starts with the input as sub-issue
    assert not usage.held({419})


def test_only_the_feature_with_the_open_decision_is_left_out(monkeypatch, no_release):
    stub(monkeypatch, {418: issue("open", ["needs-human"], DECISION), 419: issue("open", ["needs-human"], INPUT)})
    assert usage.free_sources(no_release, epics=lambda: []) == ["1 roadmap features with no epic"]   # trip:bus
    stub(monkeypatch, {418: issue("open", ["needs-human"], DECISION), 419: issue("open", ["after-release"], INPUT)})
    assert usage.free_sources(no_release, epics=lambda: []) == []
