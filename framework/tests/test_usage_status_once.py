"""framework/tools/usage.py --fire reads the status comments once, and its stderr line names a failed read (#3069)."""
import dashboard
import health
import pytest
import usage

NOW = 1_800_000_000


@pytest.fixture
def fake(monkeypatch):
    """Fakes for the CLI usage, the GitHub calls and the claims; returns the list of the status comment reads."""
    reads = []
    monkeypatch.setattr(usage, "read_usage", lambda: {"five_hour": (0.2, NOW + 3 * 3600, "allowed")})
    monkeypatch.setattr(dashboard, "pages", lambda path: [])
    monkeypatch.setattr(dashboard, "api", lambda path: {"total_count": 0})
    monkeypatch.setattr(health, "lane_claims", lambda now: {})
    monkeypatch.setattr(health, "claim_refs", lambda remote="origin": [])
    monkeypatch.setattr(health, "active_claims", lambda now: 0)
    monkeypatch.setattr(usage, "due_reviews", lambda **_: [])   # claim.review_slot reads the status issue and the lock refs
    monkeypatch.setattr(health, "status_comments", lambda *a, **kw: reads.append(1) or [])
    return reads


def test_fire_reads_the_status_comments_once(fake, capsys):
    usage.main(["--fire"])
    assert len(fake) == 1
    assert "failed" not in capsys.readouterr().err


def test_a_failed_read_gives_the_default_burns_and_names_the_error(fake, monkeypatch, capsys):
    def fail(*a, **kw):
        fake.append(1)
        raise RuntimeError("HTTP 502 from the API")
    monkeypatch.setattr(health, "status_comments", fail)
    usage.main(["--fire"])
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[0].isdigit() and any(line.startswith("haiku ") for line in lines[1:])
    assert len(fake) == 1
    assert f"burn {usage.BURN:.3f}" in err and f"burn7 {usage.BURN7:.4f}" in err
    assert "status comments failed (RuntimeError: HTTP 502 from the API)" in err
    assert "haiku" in err and "(start)" in err                            # the start weights of the lanes
