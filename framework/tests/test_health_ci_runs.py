"""`health.quick_ci_runs` reads the quick CI runs apart from the 10 pages of all runs (#1800): on the window of 100 merged
PRs the cut list lost the CI runs of the first hours, and 2 "red CI" takeovers counted as "after the report"."""
import health


def test_ci_runs_adds_only_the_runs_that_the_list_of_all_runs_cut(monkeypatch):
    calls = []

    def api(path):
        calls.append(path)
        page = int(path.split("page=")[2].split("&")[0])
        return {"workflow_runs": [{"id": i} for i in range(100)] if page == 1 else [{"id": 100}, {"id": 101}]}

    monkeypatch.setattr(health, "api", api)
    got = health.quick_ci_runs(">=2026-11-09T16:00:00Z", {5, 101})
    assert [r["id"] for r in got] == [i for i in range(101) if i != 5]
    assert len(calls) == 2 and all("actions/workflows/ci.yml/runs?" in c and "created=>=2026-11-09" in c for c in calls)
