"""`ship_pr.checks()` runs the test file that asserts a text that the branch removes from a page (#682, #653)."""
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "framework" / "tools"))

import merge_main  # noqa: E402
import ship_pr  # noqa: E402

DIFF = "--- a/app/web/templates/trip.html\n+++ b/app/web/templates/trip.html\n@@ -3 +3 @@\n-<span>🚌 Bus</span>\n+<span><svg></svg> Bus</span>\n"


def test_a_removed_page_text_runs_the_test_that_asserts_it(tmp_path, monkeypatch, capsys):
    (tmp_path / "app/web/templates").mkdir(parents=True)
    (tmp_path / "app/web/templates/trip.html").write_text("<span><svg></svg> Bus</span>\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_bus.py").write_text("def test_bus(page):\n    assert '🚌' in page\n", encoding="utf-8")
    (tmp_path / "tests/test_other.py").write_text("def test_other(page):\n    assert 'Trips' in page\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    out = types.SimpleNamespace
    monkeypatch.setattr(ship_pr, "git", lambda *a, **k: out(stdout="app/web/templates/trip.html\n"))
    monkeypatch.setattr(merge_main, "git", lambda *a, **k: out(stdout=DIFF))
    runs = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: runs.append(cmd) or out(returncode=0, stdout="1 passed", stderr=""))
    assert ship_pr.checks()
    assert len(runs) == 1 and "tests/test_bus.py" in runs[0] and "tests/test_other.py" not in runs[0]
    assert "tests of a removed page text: tests/test_bus.py" in capsys.readouterr().out
