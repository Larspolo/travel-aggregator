"""framework/tools/health.py shows the gaps of the pacer loop and the runs that GitHub held or a person started again: the
owner found a dead loop (#4647) and held runs (#4645) by hand, and no health line showed them."""
import datetime

import health

T = datetime.datetime(2026, 10, 30, 8, tzinfo=datetime.timezone.utc)
h = lambda x: T + datetime.timedelta(hours=x)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")


def run(start, end=None, name="Pacer", status="completed", conclusion="success", attempt=1):
    return {"name": name, "run_started_at": iso(start), "updated_at": iso(end or start), "status": status,
            "conclusion": conclusion if status == "completed" else None, "run_attempt": attempt}


def test_the_gaps_between_the_live_runs():
    runs = [run(h(-2), h(2.8), conclusion="failure"),       # started before the period
            run(h(5.3), status="in_progress"),               # lives to the end of the period
            run(h(4), h(4.1), status="queued")]              # never started: no live run
    longest, total = health.loop_gaps(runs, T, h(8))
    assert round(longest, 2) == 2.5 and round(total, 2) == 2.5
    assert health.loop_gaps([], T, h(8)) == (8.0, 8.0)
    assert health.loop_gaps([run(h(-1), h(9))], T, h(8)) == (0.0, 0)


def test_held_runs_and_runs_started_again():
    runs = [run(h(1), name="Pacer", status="action_required"), run(h(2), name="CI", conclusion="action_required"),
            run(h(3), name="CI", status="waiting"), run(h(4), name="Pacer", attempt=2), run(h(5), name="CI")]
    assert health.held_runs(runs) == ({"CI": 2, "Pacer": 1}, {"Pacer": 1})


def test_the_report_has_the_lines():
    text = health.report(T, [run(h(4), name="Pacer", attempt=2)], [], [], [], [], [], loop=(2.5, 3.0, 8.0))
    lines = text.splitlines()
    assert "Pacer loop gaps (no live run, #4647): longest 2.5 h, sum 3.0 h of 8.0 h" in lines
    assert "Runs held by GitHub (#4645): 0 · started again by hand: Pacer 1" in lines
    assert not any(x.startswith("Pacer loop") for x in health.report(T, [], [], [], [], [], []).splitlines())
