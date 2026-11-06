"""framework/tools/owner_tasks.py --wait wakes the `human` session when a new needs-human ticket opens (#1025)."""
import owner_tasks


def issue(n, title, labels=("needs-human",)):
    return {"number": n, "title": title, "labels": [{"name": x} for x in labels], "body": "", "state": "open"}


def fake(monkeypatch, lists):
    """pages(): the needs-human list of each check in turn (the last one repeats), and the comments of a ticket."""
    calls = []

    def pages(path):
        calls.append(path)
        if "/comments" in path:
            return [{"body": "Agent check done.\n\nIs the bot fast enough?"}]
        return lists[min(sum("labels=" in c for c in calls) - 1, len(lists) - 1)]
    monkeypatch.setattr(owner_tasks, "pages", pages)
    return calls


def test_wait_prints_the_new_ticket_and_exits_0(monkeypatch, capsys):
    old = [issue(10, "Decide: the cheats")]
    calls = fake(monkeypatch, [old, old + [issue(11, "Muted", ("needs-human", "muted"))],
                               old + [issue(11, "Muted", ("needs-human", "muted")), issue(12, "Check the bot")]])
    assert owner_tasks.main(["--wait", "--every", "0", "--hours", "1"]) == 0
    assert capsys.readouterr().out.strip() == "#12 [play] Check the bot – Is the bot fast enough?"
    assert calls == ["issues?state=open&labels=needs-human"] * 3 + ["issues/12/comments"]   # one request per check


def test_wait_ignores_old_and_muted_tickets_and_exits_1_after_the_hours(monkeypatch, capsys):
    t = [0.0]

    def sleep(s):
        t[0] += 600
    fake(monkeypatch, [[issue(10, "Decide: the cheats")],
                       [issue(10, "Decide: the cheats"), issue(11, "Muted", ("needs-human", "muted"))]])
    assert owner_tasks.wait(every=0, hours=1, clock=lambda: t[0], sleep=sleep) is None
    monkeypatch.setattr(owner_tasks, "wait", lambda every, hours: None)
    assert owner_tasks.main(["--wait", "--hours", "0.5"]) == 1
    assert capsys.readouterr().out.strip() == "No new ticket in 0.5 hours."
