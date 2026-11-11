"""framework/tools/dashboard.py `api()` tries a GET again after a 5xx error of GitHub, and never a write (#2348: one
502 in about 450 calls stopped `health.py --compare` after 2 minutes)."""
import io
import json
import subprocess
import urllib.error

import pytest

import dashboard


def fake_urlopen(codes):
    """An `urlopen` that raises an HTTPError for each code of `codes` in turn, then returns `{"ok": 1}`."""
    calls = []

    def urlopen(req):
        calls.append(req.get_method())
        if len(calls) <= len(codes):
            raise urllib.error.HTTPError(req.full_url, codes[len(calls) - 1], "error", {}, None)
        return io.BytesIO(json.dumps({"ok": 1}).encode())
    return urlopen, calls


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setattr(dashboard.time, "sleep", lambda s: None)


def test_a_get_is_tried_again_after_a_502(monkeypatch):
    urlopen, calls = fake_urlopen([502, 503])
    monkeypatch.setattr(dashboard.urllib.request, "urlopen", urlopen)
    assert dashboard.api("issues/1") == {"ok": 1}
    assert calls == ["GET"] * 3


def test_a_get_stops_after_3_tries(monkeypatch):
    urlopen, calls = fake_urlopen([502, 502, 502])
    monkeypatch.setattr(dashboard.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        dashboard.api("issues/1")
    assert len(calls) == 3


@pytest.mark.parametrize("method, code", [("POST", 502), ("PATCH", 503), ("GET", 404)])
def test_a_write_or_a_client_error_is_not_tried_again(monkeypatch, method, code):
    urlopen, calls = fake_urlopen([code])
    monkeypatch.setattr(dashboard.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        dashboard.api("issues/1", method, {} if method != "GET" else None)
    assert len(calls) == 1


def test_gh_api_gives_the_status_on_stderr():
    error = lambda text: subprocess.CalledProcessError(1, ["gh"], stderr=text)
    assert dashboard.server_error(error("gh: Bad Gateway (HTTP 502)"))
    assert not dashboard.server_error(error("gh: Not Found (HTTP 404)"))
