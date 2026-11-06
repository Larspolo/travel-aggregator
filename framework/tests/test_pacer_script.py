"""The workflow pacer (#3193): `framework/tools/pacer.py` starts the runs of `usage.fire` with the API triggers of the tasks."""
import http.server
import threading

import pacer
import pytest


@pytest.fixture
def server():
    """A fake API trigger: records (path, Authorization) of each POST; the path "/limit" answers 429, "/down" 500."""
    got = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            got.append((self.path, self.headers["Authorization"], self.headers["anthropic-beta"]))
            code = {"/limit": 429, "/down": 500}.get(self.path, 200)
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b'{"type": "routine_fire"}')

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", got
    httpd.shutdown()


def run(monkeypatch, k, runs, env, argv=()):
    monkeypatch.setattr(pacer.usage, "read_usage", lambda: {"five_hour": (0.2, 0, "allowed")})
    monkeypatch.setattr(pacer.usage, "fire", lambda *a, skip=(), status=None, **kw: (k, {t: 0 if t in skip else n for t, n in runs.items()}, "x"))
    monkeypatch.setattr(pacer.usage, "read_status", lambda: ([], ""))
    with pytest.raises(SystemExit) as e:
        pacer.main(list(argv), env=env)
    return e.value.code


def test_the_lane_runs_go_to_the_lane_task_and_the_rest_to_the_main_task(monkeypatch, server):
    url, got = server
    env = {"PACER_URL_MAIN": f"{url}/main", "PACER_TOKEN_MAIN": "tm", "PACER_URL_HAIKU": f"{url}/haiku",
           "PACER_TOKEN_HAIKU": "th"}
    assert run(monkeypatch, 8, {"haiku": 5, "deep": 0}, env) == 0
    assert sorted(got) == sorted([("/haiku", "Bearer th", pacer.BETA)] * 5 + [("/main", "Bearer tm", pacer.BETA)] * 3)


def test_a_lane_without_a_url_gets_no_call(monkeypatch, server, capsys):
    url, got = server
    env = {"PACER_URL_MAIN": f"{url}/main", "PACER_TOKEN_MAIN": "tm"}
    assert run(monkeypatch, 3, {"haiku": 0, "deep": 1}, env) == 0
    assert [p for p, *_ in got] == ["/main"] * 2
    assert "no URL for deep" in capsys.readouterr().out


def test_a_failed_call_gives_exit_1_and_a_429_stops_only_its_task(monkeypatch, server, capsys):
    url, got = server
    env = {"PACER_URL_HAIKU": f"{url}/limit", "PACER_TOKEN_HAIKU": "th"}
    assert run(monkeypatch, 4, {"haiku": 4}, env) == 0            # the hourly limit is no failure; no main URL
    assert len(got) == 1 and "hourly limit: haiku" in capsys.readouterr().out
    env = {"PACER_URL_MAIN": f"{url}/down", "PACER_TOKEN_MAIN": "tm"}
    assert run(monkeypatch, 1, {}, env) == 1


def test_a_dry_run_sends_nothing(monkeypatch, server, capsys):
    url, got = server
    env = {"PACER_URL_MAIN": f"{url}/main", "PACER_TOKEN_MAIN": "tm"}
    assert run(monkeypatch, 2, {"haiku": 0}, env, ["--dry-run"]) == 0
    assert got == [] and 'Would start {"haiku": 0, "main": 2}' in capsys.readouterr().out


def test_a_session_gets_no_run_from_fire(monkeypatch, capsys):
    monkeypatch.setattr(pacer.usage, "read_usage", lambda: {"five_hour": (0.2, 0, "allowed")})
    monkeypatch.setattr(pacer.usage, "fire", lambda *a, status=None, **kw: (8, {"haiku": 5}, "inputs"))
    monkeypatch.setattr(pacer.usage, "read_status", lambda: ([], ""))
    pacer.usage.main(["--fire"])
    out, err = capsys.readouterr()
    assert out.split() == ["0", "haiku", "0"] and "the session starts no run" in err


def test_the_main_task_gets_the_runs_of_a_lane_at_its_limit(monkeypatch, server, capsys):
    url, got = server
    env = {"PACER_URL_HAIKU": f"{url}/limit", "PACER_TOKEN_HAIKU": "th", "PACER_URL_MAIN": f"{url}/main",
           "PACER_TOKEN_MAIN": "tm"}
    assert run(monkeypatch, 5, {"haiku": 4}, env) == 0            # 1 main run, then 4 blocked haiku runs to main
    assert [p for p, *_ in got] == ["/limit"] + ["/main"] * 5
    assert '"main": 5' in capsys.readouterr().out
