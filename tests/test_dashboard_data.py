"""The data files of the owner's dashboard have the columns that its page reads (from the dashboard of aoe2mc)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import dashboard_data as dd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = open(os.path.join(ROOT, "tools", "dashboard_artifact", "index.html")).read()


def label(*names):
    return [{"name": n} for n in names]


ISSUES = [
    {"number": 5, "title": "Epic", "state": "open", "created_at": "2026-10-25T10:00:00Z", "closed_at": None,
     "labels": label("epic", "P2", "feature", "size:L"), "body": "Roadmap: `rank:door`",
     "sub_issues_summary": {"completed": 1, "total": 3}},
    {"number": 6, "title": "Fix", "state": "closed", "created_at": "2026-10-25T11:00:00Z",
     "closed_at": "2026-10-25T12:00:00Z", "labels": label("P1", "bug", "size:S", "in-progress"), "body": None},
    {"number": 7, "title": "A PR", "state": "closed", "pull_request": {}, "labels": [], "created_at": "", "closed_at": ""},
]
PULLS = [
    {"number": 8, "title": "Fix", "head": {"ref": "claude/x"}, "created_at": "2026-10-25T11:00:00Z",
     "merged_at": "2026-10-25T11:30:00Z"},
    {"number": 9, "title": "Closed", "head": {"ref": "claude/y"}, "created_at": "2026-10-25T11:00:00Z", "merged_at": None},
]
ROADMAP = """# Roadmap

## 2. Rank offers by effective cost

- [x] `rank:base` Base formula (epic #138)
- [ ] `rank:door` The `door-to-door` access times (#820, #967)

## Notes

- [ ] `not-a-feature` Text
"""


def test_merged_prs_keep_only_merges_with_the_minutes_open():
    rows = dd.merged_prs(PULLS)
    assert [r["number"] for r in rows] == [8] and rows[0]["minutes_open"] == 30.0
    assert set(rows[0]) >= {"number", "title", "branch", "merged_at", "minutes_open"}


def test_tickets_have_the_priority_and_flow_columns():
    rows = dd.tickets(ISSUES)
    assert [r["number"] for r in rows] == [5, 6]
    assert rows[0]["priority"] == "P2" and rows[0]["epic"] and rows[0]["subs_total"] == 3
    assert rows[1]["priority"] == "P1" and rows[1]["size"] == "S" and rows[1]["in_progress"]
    # The bands of "Open tickets over time" (page version 7) read the priority column.
    assert "open_p0" in PAGE and "r.priority" in PAGE
    assert set(rows[0]) >= {"state", "created_at", "closed_at", "kind", "status_issue", "needs_human", "muted"}


def test_epics_read_the_roadmap_key():
    rows = dd.epics(ISSUES)
    assert rows == [dict(number=5, title="Epic", state="open", closed_at="", key="rank:door", subs_done=1, subs_total=3)]


def test_roadmap_reads_the_features_of_the_goals_only():
    rows = dd.roadmap(ROADMAP)
    assert [(r["goal"], r["key"], r["checked"], r["refs"]) for r in rows] == [
        ("rank", "rank:base", True, "138"), ("rank", "rank:door", False, "820 967")]
    assert rows[1]["feature"] == "The door-to-door access times"


def test_usage_reads_the_usage_lines(monkeypatch):
    body = "Usage: 2026-10-26T16:45:08Z · usage 6.0% · resets 2026-10-26T21:30:00Z · runs 4 · week 5.0%"
    monkeypatch.setattr(dd.health, "status_comments", lambda hours: [{"body": body}])
    assert dd.usage() == [dict(at="2026-10-26T16:45:08Z", usage=0.06, resets="2026-10-26T21:30:00Z", runs=4, haiku=0,
                                week=0.05, week_resets=None, track=None)]


def test_main_writes_each_data_file(tmp_path, monkeypatch):
    monkeypatch.setattr(dd, "pages", lambda path: ISSUES if path.startswith("issues") else PULLS)
    monkeypatch.setattr(dd, "usage", lambda: [])
    monkeypatch.setattr(dd, "tokens", lambda: [])
    monkeypatch.setattr(dd, "accounts", lambda: [])
    monkeypatch.setattr(dd, "spend", lambda process: [])
    monkeypatch.setattr(dd, "reviews", lambda merges: [])
    dd.main(str(tmp_path))
    assert sorted(os.listdir(tmp_path)) == sorted(dd.DATASETS.values())
    setup = json.load(open(tmp_path / dd.DATASETS["setup"]))
    assert setup and all(set(r) == {"part", "group", "when", "does", "where"} for r in setup)
    assert json.load(open(tmp_path / dd.DATASETS["release_bar"])) == []   # no RELEASE.md: the full roadmap only
