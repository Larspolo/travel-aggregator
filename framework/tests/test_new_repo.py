"""framework/tools/new_repo.py makes and sets up the GitHub repository of a new project (the `new-project` skill)."""
import json
import subprocess

import new_repo


def project(tmp_path, weights="{ haiku = 0.25, deep = 4 }"):
    (tmp_path / "steering" / "system").mkdir(parents=True)
    (tmp_path / "steering" / "system" / "system.toml").write_text(f"[pacing]\nweights = {weights}\n")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "labels.txt").write_text("# name|color|description\nP0|b60205|Do next\n")
    return tmp_path


def test_secrets_have_a_url_and_a_token_for_each_task(tmp_path):
    names = new_repo.secret_names(str(project(tmp_path)))
    assert names[0] == "CLAUDE_CODE_OAUTH_TOKEN"
    assert {"PACER_URL_MAIN", "PACER_TOKEN_MAIN", "PACER_URL_HAIKU", "PACER_TOKEN_DEEP"} <= set(names)
    assert new_repo.secret_names(str(tmp_path / "none")) == ["CLAUDE_CODE_OAUTH_TOKEN", "PACER_URL_MAIN", "PACER_TOKEN_MAIN"]


def test_a_new_repository_is_made_public_and_pushed_once(tmp_path):
    calls = [c for c, _ in new_repo.repo_calls(str(project(tmp_path)), "me/demo", "main", "A demo")]
    assert calls[0][:3] == ["gh", "repo", "create"] and "--public" in calls[0] and "--push" in calls[0]
    assert not any(c[:2] == ["git", "-C"] for c in calls)
    again = [c for c, _ in new_repo.repo_calls(str(tmp_path), "me/demo", "main", exists=True)]
    assert again[0][-2:] == ["origin", "main"] and not any(c[:3] == ["gh", "repo", "create"] for c in again)


def test_the_settings_protect_the_branch_and_let_the_workflows_merge(tmp_path):
    calls = new_repo.repo_calls(str(project(tmp_path)), "me/demo", "main")
    rules = [json.loads(s) for c, s in calls if c[2] == "repos/me/demo/rulesets"]
    assert {r["type"] for r in rules[0]["rules"]} == {"deletion", "non_fast_forward"}
    assert any("default_workflow_permissions=write" in c for c, _ in calls)
    assert calls[-1][0][2] == "repos/me/demo/issues" and any(c[2] == "repos/me/demo/labels" for c, _ in calls)


def test_a_step_that_is_done_already_is_ok():
    done = subprocess.CompletedProcess([], 1, stdout='{"errors":[{"code":"already_exists"}]}', stderr="")
    assert new_repo.ok(["gh", "api", "repos/me/demo/labels"], done)
    assert not new_repo.ok(["gh", "api", "repos/me/demo/issues"], done)


def test_secrets_come_from_the_environment_or_a_prompt_and_never_print(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(new_repo.subprocess, "run", lambda c, input, **k: sent.append((c[3], input)) or
                        subprocess.CompletedProcess(c, 0, "", ""))
    asked = iter(["typed-value", ""])
    done = new_repo.set_secrets("me/demo", ["A", "B", "C"], {"A": "env-value"}, ask=lambda _: next(asked))
    assert done == ["A", "B"] and sent == [("A", "env-value"), ("B", "typed-value")]
    out = capsys.readouterr().out
    assert "env-value" not in out and "typed-value" not in out


def test_the_check_names_each_missing_step(tmp_path, monkeypatch):
    project(tmp_path, "{}")
    monkeypatch.setattr(new_repo, "status_exists", lambda repo: True)
    answers = {"secret": "CLAUDE_CODE_OAUTH_TOKEN\nPACER_URL_MAIN\n", "repo": "{}", "run": ""}
    gh = lambda args: answers.get(args[0], "write" if "workflow" in args[1] else "Protect main")
    rows = {name: good for name, good, _ in new_repo.checks(str(tmp_path), "me/demo", gh)}
    missing = sorted(n for n, good in rows.items() if not good)
    assert missing == ["a run of the workflow Pacer", "secret PACER_TOKEN_MAIN", "trigger in steering/system/system.toml"]
