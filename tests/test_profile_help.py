"""The profile pages explain the score and the basic weights (#2832)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import ScoreProfile
from app.profiles import to_config
from app.ranking import Weights

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


@pytest.fixture
def profile_id(sessions):
    with sessions() as s:
        p = ScoreProfile(name="Mine", config_json=to_config(Weights()))
        s.add(p)
        s.commit()
        return p.id


def test_edit_pages_show_score_card(client, profile_id):
    for path in ("/profiles/new", f"/profiles/{profile_id}"):
        html = client.get(path).text
        assert "How the score works" in html
        assert "€49 + €75 + €10 = €134" in html
        assert html.index("How the score works") < html.index('<form class="profile-edit"')
        for field in ("hour_markup", "transfer_markup"):
            assert f'aria-describedby="{field}-help"' in html
            assert re.search(rf'<p class="help" id="{field}-help">[^<]+</p>', html)
        assert "Each setting has a working default" in html


def test_profiles_page_explains_default(client, profile_id):
    html = client.get("/profiles").text
    assert "The default profile scores all trips that have no own profile" in html
