"""The refill sources of a project with no tools/release.py (#153): usage.py reads the roadmap and the epics itself,
and a missing docs/coverage.md counts 0 fallbacks, not a read error."""
import sys

import pytest
import usage

ROADMAP = """# Roadmap

## 1. Show the site

- [x] `site:skeleton` The home page
  - a sub-item with `code`
- [ ] `site:contact` The contact form
- [ ] `site:photos` Photos

## 2. The app

- [ ] `app:login` The login (#7)
"""


@pytest.fixture
def no_release(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "release", None)                  # `import release` raises ImportError
    (tmp_path / "ROADMAP.md").write_text(ROADMAP)
    monkeypatch.setitem(usage.CONFIG, "docs", {"roadmap": "ROADMAP.md"})
    return tmp_path


def epic(number, key=None):
    return {"number": number, "body": f"## Goal\nX.\n\nRoadmap: `{key}`\n" if key else "## Goal\nX."}


def test_roadmap_features_reads_the_goals_and_the_named_epics():
    assert usage.roadmap_features(ROADMAP) == {
        "site:skeleton": (1, True, set()), "site:contact": (1, False, set()), "site:photos": (1, False, set()),
        "app:login": (2, False, {7})}


def test_the_open_features_with_no_epic_are_a_source(no_release):
    epics = [epic(3, "site:skeleton"), epic(4, "site:photos")]
    free = lambda numbers: False                                         # noqa: E731
    assert usage.free_sources(no_release, epics=lambda: epics, holds=free) == ["2 roadmap features with no epic"]   # site:contact, app:login
    held = lambda numbers: 7 in numbers                                  # noqa: E731  the owner holds #7 (after-release)
    assert usage.free_sources(no_release, epics=lambda: epics, holds=held) == ["1 roadmap features with no epic"]   # site:contact


def test_no_source_when_each_open_feature_has_an_epic(no_release, capsys):
    epics = [epic(4, "site:photos"), epic(5, "site:contact"), epic(7)]   # #7: named on the line of app:login
    assert usage.free_sources(no_release, epics=lambda: epics) == []
    assert capsys.readouterr().err == ""                                 # no docs/coverage.md: 0 fallbacks, no error


def test_a_read_error_still_counts_as_a_source(no_release, capsys):
    def fail():
        raise OSError("GitHub is down")
    assert usage.free_sources(no_release, epics=fail) == ["read error"]
    assert "GitHub is down" in capsys.readouterr().err


def test_no_release_checks_and_no_error_line_without_release_py(no_release, capsys):
    assert usage.release_due() == []
    assert capsys.readouterr().err == ""


def test_cycle_start_prints_no_error_line_without_release_py(no_release, capsys):
    import cycle_start
    assert cycle_start.due_checks() == []
    assert capsys.readouterr().err == ""
