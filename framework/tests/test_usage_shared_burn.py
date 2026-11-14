"""framework/tools/usage.py: a project that shares its account uses the fixed burns. Its `Usage:` lines divide the usage of
all projects by its own runs: one project measured 27 times the real burn and got no run (street-quiz, 2026-11-14)."""
import usage


def test_a_project_that_shares_its_account_uses_the_fixed_burns(monkeypatch):
    monkeypatch.setattr(usage, "measured_burn", lambda comments, account=None: 0.8)
    monkeypatch.setattr(usage, "measured_burn7", lambda comments, account=None: 0.1)
    assert usage.burns([], shared=True) == (usage.BURN, usage.BURN7)
    assert usage.burns([], 0.05, shared=True) == (0.05, usage.BURN7)      # a given burn (--burn) stays
    assert usage.burns([], shared=False) == (0.8, 0.1)                   # a project with an account of its own measures


def test_the_share_of_the_week_tells_if_the_account_is_shared(monkeypatch):
    monkeypatch.setattr(usage, "measured_burn", lambda comments, account=None: 0.8)
    monkeypatch.setattr(usage, "measured_burn7", lambda comments, account=None: 0.1)
    monkeypatch.setattr(usage, "SHARE7", 0.25)
    assert usage.burns([]) == (usage.BURN, usage.BURN7)
    monkeypatch.setattr(usage, "SHARE7", 1.0)
    assert usage.burns([]) == (0.8, 0.1)
