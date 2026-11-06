"""ship_pr.py runs the lint command of the project, also with --tested: a Biome error went to CI with only ruff."""
import ship_pr as ship
from test_ship_pr import fake_github, repo


def test_a_lint_error_stops_the_push_also_with_tested(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo(tmp_path))
    fake_github(monkeypatch, open_prs=[{"number": 9}], lint=False)
    monkeypatch.setattr(ship, "LINT", "echo 'biome: 2 errors' && false")
    monkeypatch.setattr(ship, "push", lambda n: (_ for _ in ()).throw(AssertionError("pushed")))
    assert ship.main(["5", "--tested"]) == 2
    assert "biome: 2 errors" in capsys.readouterr().out


def test_the_lint_is_the_command_of_agent_toml():
    assert ship.LINT == ship.CONFIG["commands"]["lint"]
