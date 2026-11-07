"""Each page follows the rules of the page checklist of DESIGN.md section 10 that the HTML can show (#634)."""

import re
from html.parser import HTMLParser

from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Trip

PASSWORD = "pw"
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⭕]")
NO_LABEL = {"hidden", "submit", "button", "reset", "image"}


class _Page(HTMLParser):
    """Collects the form fields with no label and the icon links of a page."""

    def __init__(self):
        super().__init__()
        self.label_depth = 0
        self.label_for = set()
        self.fields = []  # (tag, attrs, inside a <label>)
        self.icons = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "label":
            self.label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        elif tag in ("input", "select", "textarea") and a.get("type", "text") not in NO_LABEL:
            self.fields.append((tag, a, self.label_depth > 0))
        elif tag == "use":
            self.icons.append(a.get("href") or a.get("xlink:href") or "")

    def handle_endtag(self, tag):
        if tag == "label" and self.label_depth:
            self.label_depth -= 1


def problems(html):
    """Give the rules of the checklist that the page breaks."""
    found = []
    if html.count("<h1") != 1 or not re.search(r'<header class="page-header">\s*<div>\s*(<a class="back"[^>]*>[^<]*'
                                               r'</a>\s*)?<h1>', html):
        found.append("not exactly one <h1> in the page header")
    if len(re.findall(r'class="[^"]*\bbtn-primary\b', html)) > 1:
        found.append("more than one primary button")
    if re.search(r"<[a-zA-Z][^>]*\sstyle=", html):
        found.append("a style= attribute")
    if EMOJI.search(html):
        found.append("an emoji")
    page = _Page()
    page.feed(html)
    for tag, a, wrapped in page.fields:
        if not (wrapped or a.get("id") in page.label_for or a.get("aria-label")):
            found.append(f"a {tag} {a.get('name')!r} with no label")
    found += [f"an icon not from icons.svg: {h}" for h in page.icons if not h.startswith("/static/icons.svg#")]
    return found


def _client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    with sessions() as s:
        trip = Trip(title="T", origin_text="A", destination_text="B")
        s.add(trip)
        s.commit()
        return c, trip.id


def test_each_page_follows_the_page_checklist(sessions, monkeypatch):
    c, tid = _client(sessions, monkeypatch)
    paths = ["/", "/?archived=1", f"/trips/{tid}", "/trips/new", f"/trips/{tid}/edit", f"/trips/{tid}/delete",
             f"/trips/{tid}/offers/new", "/sources/new", "/captures", f"/trips/{tid}/captures", "/profiles",
             "/places", "/settings", "/rates", "/tokens"]
    found = {}
    for path in paths:
        r = c.get(path)
        assert r.status_code == 200, path
        if problems(r.text):
            found[path] = problems(r.text)
    assert found == {}


def test_the_checks_find_each_broken_rule():
    good = '<header class="page-header"><div><h1>T</h1></div></header>'
    assert problems(good) == []
    assert problems(good + "<h1>Two</h1>")
    assert problems(good + '<a class="btn btn-primary">A</a><button class="btn-primary">B</button>')
    assert problems(good + '<p style="color: red">x</p>')
    assert problems(good + "<p>✈️</p>")
    assert problems(good + '<input name="q">')
    assert problems(good + '<svg><use href="/other.svg#x"></use></svg>')
    assert problems(good + '<label>Q <input name="q"></label><label for="r">R</label><input id="r" name="r">'
                    '<input type="hidden" name="h"><svg><use href="/static/icons.svg#plus"></use></svg>') == []
