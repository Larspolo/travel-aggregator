"""The owner gate compares the PR head with its merge base, not with main (#1097): a branch that started before a change
of `owners` on main is not held when its own `agent.toml` does not change the owners."""
import os
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(__file__), "..", "tools")
sys.path.insert(0, os.path.abspath(TOOLS))

import owner_gate  # noqa: E402

OLD = 'owner = "Larspolo"\nowners = ["Larspolo"]\n'
NEW = 'owner = "Larspolo"\nowners = ["Larspolo", "Helper"]\n'
CHANGED = 'owner = "Larspolo"\nowners = ["Larspolo", "Intruder"]\n'


@pytest.fixture
def gate(monkeypatch):
    """Patch the GitHub reads: `texts` maps a ref to an agent.toml, `compare` is the compare call, `reviews` the reviews."""
    state = {"texts": {}, "compare": None, "reviews": []}

    def fake_gh(path):
        if path.startswith("compare/"):
            return state["compare"]
        if path.startswith("pulls/"):
            return state["reviews"]
        return None

    monkeypatch.setattr(owner_gate, "gh", fake_gh)
    monkeypatch.setattr(owner_gate, "toml_at", lambda ref: state["texts"].get(ref, ""))
    monkeypatch.setattr(owner_gate, "load", lambda: {})
    monkeypatch.setattr(owner_gate, "owners", lambda data: ["Larspolo"])
    return state


def compare_to(base):
    return {"merge_base_commit": {"sha": base}}


def test_old_branch_without_owner_change_passes(gate):
    # the branch started before main gave "Helper" an owner role: its own agent.toml keeps the old owners
    gate["texts"] = {"HEAD": OLD, "BASE": OLD, "main": NEW}
    gate["compare"] = compare_to("BASE")
    assert owner_gate.main(["1083", "HEAD"]) == 0


def test_pr_that_changes_owners_waits_without_approval(gate):
    gate["texts"] = {"HEAD": CHANGED, "BASE": OLD, "main": OLD}
    gate["compare"] = compare_to("BASE")
    assert owner_gate.main(["1", "HEAD"]) == 1


def test_pr_that_changes_owners_passes_with_owner_approval(gate):
    gate["texts"] = {"HEAD": CHANGED, "BASE": OLD, "main": OLD}
    gate["compare"] = compare_to("BASE")
    gate["reviews"] = [{"state": "APPROVED", "user": {"login": "Larspolo"}}]
    assert owner_gate.main(["1", "HEAD"]) == 0


def test_failed_compare_falls_back_to_main(gate):
    # no merge base: the gate compares with main as before, so a head that differs from main waits
    gate["texts"] = {"HEAD": OLD, "main": NEW}
    gate["compare"] = None
    assert owner_gate.main(["1", "HEAD"]) == 1
    gate["texts"]["main"] = OLD
    assert owner_gate.main(["1", "HEAD"]) == 0
