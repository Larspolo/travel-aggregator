"""The tools of the `capture` skill (`tools/capture.py`): the scrub removes the personal data of a HAR, and the
publish pushes only a clean HAR to the capture branch. No test opens a travel site (P1)."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import capture  # noqa: E402


def entry(url, body, request=None, started="2026-11-06T10:00:00.000Z"):
    return {"startedDateTime": started, "time": 12,
            "request": {"method": "POST", "url": url, "cookies": [{"name": "sid", "value": "x"}],
                        "headers": [{"name": "Cookie", "value": "sid=x"}, {"name": "Content-Type",
                                                                          "value": "application/json"}],
                        "postData": {"mimeType": "application/json", "text": json.dumps(request or {})}},
            "response": {"status": 200, "cookies": [], "headers": [{"name": "Set-Cookie", "value": "a=b"}],
                         "content": {"mimeType": "application/json", "text": json.dumps(body)}}}


def har_file(tmp_path, name, *entries):
    path = tmp_path / name
    path.write_text(json.dumps({"log": {"version": "1.2", "entries": list(entries)}}), "utf-8")
    return path


ANGEBOTE = "https://int.bahn.de/web/api/angebote/fahrplan"
BODY = {"verbindungen": [{"angebotsPreis": {"betrag": 29.99}, "reisender": {"vorname": "Jeroen",
                                                                            "email": "j@example.nl"}},
                         {"hinweis": "Mail an j@example.nl", "halt": "Köln Hbf"}]}


def test_scrub_removes_cookies_headers_and_personal_values(tmp_path):
    raw = har_file(tmp_path, "raw.har", entry(ANGEBOTE, BODY, {"kundenkonto": "123", "klasse": "KLASSE_2"}))
    har, replaced = capture.scrub([raw], identity=False)
    e = har["log"]["entries"][0]
    assert e["request"]["cookies"] == [] and e["response"]["cookies"] == []
    assert e["request"]["headers"] == [{"name": "content-type", "value": "application/json"}]
    assert e["response"]["headers"] == []
    body = json.loads(e["response"]["content"]["text"])
    assert body["verbindungen"][0]["reisender"] == {"vorname": "REDACTED", "email": "REDACTED"}
    assert body["verbindungen"][0]["angebotsPreis"] == {"betrag": 29.99}
    assert body["verbindungen"][1] == {"hinweis": "Mail an REDACTED", "halt": "Köln Hbf"}
    assert json.loads(e["request"]["postData"]["text"]) == {"kundenkonto": "REDACTED", "klasse": "KLASSE_2"}
    assert replaced == 4
    assert capture.problems(har, identity=False) == []


def test_scrub_replaces_the_private_words_in_any_place(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_PRIVATE", "Jeroen van Berg")
    raw = har_file(tmp_path, "raw.har", entry(ANGEBOTE + "?name=jeroen", {"text": "Hallo JEROEN, Berg"}))
    har, _ = capture.scrub([raw], identity=False)
    text = json.dumps(har)
    assert "eroen" not in text.lower() and "Berg" not in text
    assert capture.problems(har, identity=False) == []


def test_scrub_keeps_only_matching_urls_of_several_files_in_time_order(tmp_path):
    a = har_file(tmp_path, "a.har", entry(ANGEBOTE, {"n": 2}, started="2026-11-06T10:00:02.000Z"),
                 entry("https://int.bahn.de/web/api/reiseloesung/orte", {"n": 0}))
    b = har_file(tmp_path, "b.har", entry(ANGEBOTE, {"n": 1}, started="2026-11-06T10:00:01.000Z"))
    har, _ = capture.scrub([a, b], match=r"/web/api/angebote/", identity=False)
    assert [json.loads(e["response"]["content"]["text"])["n"] for e in har["log"]["entries"]] == [1, 2]


def test_problems_refuse_a_raw_har(tmp_path):
    raw = json.loads(har_file(tmp_path, "raw.har", entry(ANGEBOTE, BODY)).read_text())
    found = " ".join(capture.problems(raw, identity=False))
    assert "cookies" in found and "headers" in found and "e-mail" in found
    assert capture.problems({"log": {"entries": []}}) == ["the HAR has no entries"]


def test_cli_scrub_writes_the_file_and_a_summary(tmp_path, monkeypatch, capsys):
    raw = har_file(tmp_path, "raw.har", entry(ANGEBOTE, {"verbindungen": []}))
    out = tmp_path / "out" / "bahn.de-169.har"
    assert capture.main(["scrub", str(raw), "--out", str(out), "--match", "angebote"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["entries"] == 1 and report["problems"] == [] and report["requests"][0]["url"] == ANGEBOTE
    assert json.loads(out.read_text())["log"]["entries"][0]["response"]["status"] == 200


def test_hook_has_the_pattern_as_a_javascript_string():
    js = capture.hook(r"/web/api/angebote/")
    assert 'new RegExp("/web/api/angebote/")' in js and js.startswith("(() =>")
    with pytest.raises(Exception):
        capture.hook("(")


def run(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def clone(tmp_path):
    """A clone with an origin that has a main branch, as the clone of the user."""
    origin = tmp_path / "origin.git"
    run("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    work = tmp_path / "work"
    run("clone", "-q", str(origin), str(work), cwd=tmp_path)
    run("config", "user.name", "Test", cwd=work)
    run("config", "user.email", "test@example.org", cwd=work)
    (work / "README.md").write_text("x\n")
    run("add", "README.md", cwd=work)
    run("commit", "-q", "-m", "init", cwd=work)
    run("push", "-q", "origin", "main", cwd=work)
    return origin, work


def test_publish_pushes_a_clean_har_to_the_capture_branch(tmp_path, clone):
    origin, work = clone
    raw = har_file(tmp_path, "raw.har", entry(ANGEBOTE, {"verbindungen": []}))
    clean = tmp_path / "bahn.de-fare-classes.har"
    clean.write_text(json.dumps(capture.scrub([raw], identity=False)[0]))
    branch, target, commit = capture.publish(clean, 169, "bahn.de", root=work, identity=False)
    assert branch == "owner/bahn-captures" and target == "captures/bahn.de/169-bahn.de-fare-classes.har"
    assert run("rev-parse", branch, cwd=origin) == commit
    assert json.loads(run("show", f"{commit}:{target}", cwd=origin))["log"]["entries"]
    assert run("status", "--porcelain", cwd=work) == "" and run("branch", "--show-current", cwd=work) == "main"
    second = tmp_path / "169-again.har"
    second.write_text(clean.read_text())
    _, target2, commit2 = capture.publish(second, 169, "bahn.de", root=work, identity=False)
    assert run("rev-parse", f"{commit2}^", cwd=origin) == commit and target2 == "captures/bahn.de/169-again.har"


def test_publish_refuses_a_raw_har(tmp_path, clone):
    origin, work = clone
    raw = har_file(tmp_path, "raw.har", entry(ANGEBOTE, BODY))
    with pytest.raises(SystemExit, match="Not published"):
        capture.publish(raw, 169, "bahn.de", root=work, identity=False)
    assert "owner/bahn-captures" not in run("branch", "--list", cwd=origin)
