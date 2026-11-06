"""The release percent of a project with no tools/release.py: the done features of the goals 1 to 3 of the roadmap.
Before, `release_percent()` gave None there, and `health.py` printed "Release per 1 % of 7-day quota: -": the main
number of the process review was missing (improve skill, lever 10)."""
import sys

import pytest
import usage

ROADMAP = """# Roadmap

## 1. Show the site

- [x] `site:skeleton` The home page
- [ ] `site:contact` The contact form
- [ ] `site:photos` Photos

## 2. The app

- [ ] `app:login` The login (#7)

## 4. Later

- [ ] `later:shop` A shop
"""


@pytest.fixture
def no_release(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "release", None)                  # `import release` raises ImportError
    (tmp_path / "ROADMAP.md").write_text(ROADMAP)
    monkeypatch.setitem(usage.CONFIG, "docs", {"roadmap": "ROADMAP.md"})
    return tmp_path


def epic(number, state, key=None):
    return {"number": number, "state": state, "body": f"## Goal\nX.\n\nRoadmap: `{key}`\n" if key else "## Goal\nX."}


def test_a_ticked_feature_counts_and_goal_4_does_not(no_release):
    assert usage.release_percent(no_release, epics=lambda: []) == 25          # site:skeleton of 4 features


def test_a_closed_epic_counts_its_feature_an_open_one_does_not(no_release):
    epics = [epic(3, "closed", "site:contact"), epic(4, "open", "site:photos"), epic(7, "closed")]   # #7: named
    assert usage.release_percent(no_release, epics=lambda: epics) == 75


def test_a_read_error_gives_no_release_field(no_release, capsys):
    def fail():
        raise OSError("GitHub is down")
    assert usage.release_percent(no_release, epics=fail) is None
    assert "GitHub is down" in capsys.readouterr().err


def test_health_reads_the_percent_of_the_sample_line():
    import health
    usage_ = {"five_hour": (0.06, 0, "allowed"), "seven_day": (0.26, 0, "allowed")}
    line = usage.sample_line(usage_, 0, 3, 25.0)
    assert [p[1:] for p in health.weekly([{"body": line}])] == [(26.0, 25.0)]
