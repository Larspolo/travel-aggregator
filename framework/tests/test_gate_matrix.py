"""The job `browser` of ci.yml is a matrix of 2 jobs (#1062): its check runs are `browser (1)` and `browser (2)`.
The gate `browser` of `[ci] gates` covers both (framework/tools/ship_pr.py), and framework/tools/health.py counts their
steps as one job, so that the median of `browser / Browser tests` stays comparable."""
import dashboard
import health
import ship_pr as ship


def test_a_red_part_of_a_matrix_gate_is_a_red_gate(monkeypatch):
    monkeypatch.setattr(ship, "GATES", ("browser",))
    one = {"id": 1, "name": "browser (1)", "status": "completed", "conclusion": "success"}
    two = {"id": 2, "name": "browser (2)", "status": "in_progress", "conclusion": None}
    other = {"id": 3, "name": "browsers", "status": "completed", "conclusion": "failure"}   # not the gate `browser`
    monkeypatch.setattr(dashboard, "api", lambda path: {"check_runs": [one, two, other]})
    assert ship.red_gate("abc") is None
    two.update(status="completed", conclusion="failure")
    assert ship.red_gate("abc") == two


def test_the_gate_of_a_check_run():
    assert ship.gate("browser (2)") == "browser"
    assert ship.gate("browser") == "browser"
    assert ship.gate(None) == ""


def test_the_jobs_of_a_matrix_count_as_one_job():
    def job(name, minutes):
        return dict(name=name, steps=[dict(name="Browser tests", started_at="2026-11-08T13:00:00Z",
                                           completed_at=f"2026-11-08T13:{minutes:02d}:00Z")])
    jobs = [job("browser (1)", 1), job("browser (2)", 3), job("browser", 2)]
    assert health.slow_steps(jobs, 3) == [(2.0, "browser / Browser tests")]
