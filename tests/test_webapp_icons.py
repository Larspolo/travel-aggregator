"""The app has icons for the home screen of a phone (#796), drawn from app/web/static/icon.svg."""

import pathlib
import struct

import pytest
from fastapi.testclient import TestClient

from app.main import app

STATIC = pathlib.Path(__file__).resolve().parent.parent / "app" / "web" / "static"


@pytest.mark.parametrize(
    "name,size",
    [("icon-192.png", 192), ("icon-512.png", 512), ("icon-maskable-512.png", 512), ("apple-touch-icon.png", 180)],
)
def test_icon_has_size(name, size):
    data = (STATIC / name).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (size, size)


def test_icon_source_is_kept():
    assert "<svg" in (STATIC / "icon.svg").read_text()


def test_login_has_apple_touch_icon(sessions):
    html = TestClient(app).get("/login").text
    assert '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">' in html
