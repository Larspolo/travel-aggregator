"""framework/tools/new_repo.py adds the ruleset "Protect main" only when the repository has not got it (#4797)."""
import subprocess

import new_repo


def fake_gh(monkeypatch, names):
    """A `gh` that lists the ruleset names of `names` for the rulesets call, and fails for any other call."""
    def run(call, **kw):
        if call[:2] == ["gh", "api"] and call[2].endswith("/rulesets"):
            return subprocess.CompletedProcess(call, 0, "".join(f"{n}\n" for n in names), "")
        return subprocess.CompletedProcess(call, 1, "", "not faked")
    monkeypatch.setattr(new_repo.subprocess, "run", run)


def target(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "labels.txt").write_text("# name|color|description\nP0|b60205|Do next\n")
    return str(tmp_path)


def ruleset_posts(calls):
    return [c for c, _ in calls if c[:3] == ["gh", "api", "repos/me/demo/rulesets"] and "POST" in c]


def test_a_second_run_has_no_ruleset_post_when_the_ruleset_exists(monkeypatch, tmp_path):
    fake_gh(monkeypatch, [new_repo.RULESET["name"]])
    calls = new_repo.repo_calls(target(tmp_path), "me/demo", "main", exists=True)
    assert ruleset_posts(calls) == []


def test_a_ruleset_is_posted_when_the_repository_has_none(monkeypatch, tmp_path):
    fake_gh(monkeypatch, [])
    calls = new_repo.repo_calls(target(tmp_path), "me/demo", "main", exists=True)
    assert len(ruleset_posts(calls)) == 1


def test_a_ruleset_with_a_similar_name_is_not_the_ruleset(monkeypatch, tmp_path):
    fake_gh(monkeypatch, ["Protect", "Protect main 2"])
    calls = new_repo.repo_calls(target(tmp_path), "me/demo", "main", exists=True)
    assert len(ruleset_posts(calls)) == 1
