"""Each field of the trip, delete, manual offer and source forms has a label above it in a .field (#629)."""

import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Trip

GUARDS = ("app/web/templates/*.html",)   # ship_pr runs this file for these changes, also with --tested: no import leads to it (#730, #1328)

PASSWORD = "pw"


class _Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.fields, self.labels, self.buttons = [], [], {}, []
        self._label = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("input", "select", "textarea") and a.get("type") != "hidden":
            in_field = any("field" in (c or "").split() for _, c in self.stack)
            self.fields.append((a.get("name"), a.get("id"), in_field, self._last_label))
        if tag == "label":
            self._label = a.get("for")
        if tag in ("button", "a") and "btn" in (a.get("class") or "").split():
            self.buttons.append(a.get("class").split())
        if tag not in ("input", "br", "img", "meta", "link"):
            self.stack.append((tag, a.get("class")))

    _last_label = None

    def handle_endtag(self, tag):
        if tag == "label":
            self._last_label, self._label = self._label, None
        while self.stack:
            if self.stack.pop()[0] == tag:
                break


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": tok})
    return c


@pytest.fixture
def tid(sessions):
    with Session(sessions.kw["bind"]) as s:
        t = Trip(title="Berlin", travelers=1)
        s.add(t)
        s.commit()
        return t.id


def _parse(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    p = _Form()
    p.feed(r.text)
    return r.text, p


@pytest.mark.parametrize("path", ["/trips/new", "/trips/{t}/edit", "/trips/{t}/offers/new", "/sources/new"])
def test_each_field_has_a_label_above_it(client, tid, path):
    _, p = _parse(client, path.format(t=tid))
    assert p.fields
    for name, id_, in_field, label in p.fields:
        assert id_ and in_field and label == id_, name
    assert sum("btn-primary" in b for b in p.buttons) == 1


def test_delete_page_has_the_danger_button(client, tid):
    html, p = _parse(client, f"/trips/{tid}/delete")
    assert 'name="csrf_token"' in html
    assert any("btn-danger" in b for b in p.buttons)
    assert not any("btn-primary" in b for b in p.buttons)
