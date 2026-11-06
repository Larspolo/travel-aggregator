"""framework/tools/owner_tasks.py takes the words of a play test from agent.toml, section [owner_tasks] (#1900)."""
import owner_tasks


def test_the_play_text_of_the_project_makes_a_play_test(monkeypatch):
    i = {"number": 3, "title": "Look at the boats", "labels": [{"name": "needs-human"}], "body": "Use a real client."}
    monkeypatch.setattr(owner_tasks, "PLAY", None)
    assert owner_tasks.kind(i) == "question"
    monkeypatch.setattr(owner_tasks, "PLAY", "real client")
    assert owner_tasks.kind(i) == "play"
