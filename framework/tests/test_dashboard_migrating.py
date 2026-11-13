"""A ticket that adds a migration waits while another migration is in progress (#2679), with fixture data."""
import dashboard

MIG = "Add `part` to `Fare` in `app/models.py`, and a new migration after `migrations/HEAD`."


def issue(n, *names, body="", **kw):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": x} for x in names], body=body, **kw)


def test_migrates():
    assert dashboard.migrates(issue(1, "feature", body=MIG))
    assert not dashboard.migrates(issue(2, "process", body=MIG))       # a process ticket only names the file
    assert not dashboard.migrates(issue(3, "feature", body="Change `app/ingest.py`."))
    assert not dashboard.migrates(issue(4, "feature", body=None))


def test_work_marks_a_migration_in_progress():
    claimed = issue(1, "P3", "in-progress", body=MIG)
    assert dashboard.MIGRATING in dashboard.work([claimed], {})
    assert dashboard.MIGRATING not in dashboard.work([issue(1, "P3", body=MIG)], {})     # not claimed
    pr, held = issue(9, pull_request={}), issue(9, "hold", pull_request={})
    files = {9: ["app/models.py", "migrations/HEAD", "migrations/versions/0075_x.py"]}
    assert dashboard.MIGRATING in dashboard.work([pr], files)
    assert dashboard.MIGRATING not in dashboard.work([held], files)          # a held PR does not stop the others
    assert dashboard.MIGRATING not in dashboard.work([pr], {9: ["app/models.py"]})
    assert dashboard.MIGRATING not in dashboard.names(f"`{dashboard.MIGRATING}`")


def test_a_second_migration_ticket_waits():
    issues = [issue(5, "P3", "feature", body=MIG), issue(6, "P3", "feature", body="Change `app/ingest.py`."),
              issue(7, "P1", "process", body=MIG)]
    busy = dashboard.work([issue(1, "P3", "in-progress", body=MIG)], {})
    assert [i["number"] for i in dashboard.candidates(issues, busy)] == [7, 6]
    assert [i["number"] for i in dashboard.candidates(issues, {"models.py"})] == [7, 6, 5]   # no migration in progress
