"""The pages use one CSS file with the colour tokens of DESIGN.md (#589)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

CSS = Path("app/web/static/app.css")
TOKENS = [
    "--bg", "--surface", "--text", "--muted", "--line", "--accent", "--accent-text", "--accent-soft", "--good",
    "--info", "--warn", "--danger", "--shadow", "--radius", "--radius-lg", "--text-sm", "--text-lg", "--text-xl",
]


def test_a_page_links_app_css_and_the_file_is_served():
    c = TestClient(app)
    page = c.get("/login").text
    assert 'href="/static/app.css"' in page and "<style" not in page
    r = c.get("/static/app.css")
    assert r.status_code == 200 and "text/css" in r.headers["content-type"]


def test_app_css_has_all_tokens_and_no_colour_outside_them():
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.S)
    root, rest = css.split("@media (prefers-color-scheme: dark)", 1)
    dark, rules = rest.split("}\n}", 1)
    rules = root.split("}", 1)[1] + rules
    for token in TOKENS:
        assert f"{token}:" in root.split("}", 1)[0], token
    for token in TOKENS[:13]:
        assert f"{token}:" in dark, token
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", rules)
    assert "max-width: 80rem" in rules and "tabular-nums" in rules
