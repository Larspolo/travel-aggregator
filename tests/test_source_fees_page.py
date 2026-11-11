"""The booking fees page of Settings and the table `source_fees` (#1142)."""

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.fees import load_fees
from app.main import app
from app.models import SourceFee

PASSWORD = "pw"


def _token(c, path="/fees"):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _rows(sessions):
    with sessions() as s:
        return {r.source: r.amount for r in s.scalars(select(SourceFee))}


def _save(c, source, amount):
    return c.post("/fees", data={"source": source, "amount": amount, "csrf_token": _token(c)})


def test_needs_login(sessions):
    r = TestClient(app).get("/fees", follow_redirects=False)
    assert r.status_code in (303, 401)


def test_lists_all_sources_with_zero(client):
    from app.parsers import parser_classes
    text = client.get("/fees").text
    for source in [*parser_classes(), "manual"]:
        assert f'value="{source}"' in text
    assert "NS International" in text
    assert "€0.00" in text


def test_save_and_show(client, sessions):
    assert _save(client, "thetrainline.com", "1.50").status_code == 200
    assert _rows(sessions) == {"thetrainline.com": Decimal("1.50")}
    assert "€1.50" in client.get("/fees").text
    _save(client, "thetrainline.com", "2")
    with sessions() as s:
        assert load_fees(s) == {"thetrainline.com": Decimal("2.00")}


def test_zero_deletes(client, sessions):
    _save(client, "manual", "3")
    _save(client, "manual", "0")
    assert _rows(sessions) == {}


@pytest.mark.parametrize("source,amount", [("thetrainline.com", "-1"), ("thetrainline.com", "abc"),
                                           ("thetrainline.com", "1000.01"), ("thetrainline.com", "1.234"),
                                           ("thetrainline.com", ""), ("thetrainline.com", "  "),
                                           ("thetrainline.com", "NaN"), ("example.com", "1")])
def test_bad_input(client, sessions, source, amount):
    r = _save(client, source, amount)
    assert r.status_code == 422
    assert 'class="error"' in r.text
    assert _rows(sessions) == {}


def test_settings_links_to_fees(client):
    assert 'href="/fees"' in client.get("/rates").text


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0023")
    engine = create_engine(empty_database_url)
    try:
        assert "source_fees" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0022")
        assert "source_fees" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
