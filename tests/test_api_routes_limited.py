"""Every API route with require_token has both limits: the token limit (#411) and the address lock (#412).

The routes are found from the app, not from a fixed list, so a new route with require_token is tested too.
"""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import tokens
from app.auth import api_limiter, require_token, token_limiter
from app.main import app


def _walks_to_require_token(dependant) -> bool:
    for sub in dependant.dependencies:
        if sub.call is require_token or _walks_to_require_token(sub):
            return True
    return False


def _all_api_routes(routes, prefix: str = ""):
    """The APIRoutes of the app with their full path. FastAPI 0.162 wraps each included router (_IncludedRouter)."""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _all_api_routes(inner.routes, prefix + route.include_context.prefix)
        elif isinstance(route, APIRoute):
            yield prefix + route.path, route


def _limited_routes() -> list[tuple[str, str]]:
    found = []
    for path, route in _all_api_routes(app.routes):
        if _walks_to_require_token(route.dependant):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                found.append((method, path))
    return found


ROUTES = _limited_routes()


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    token_limiter.reset()
    api_limiter.reset()
    c = Clock()
    monkeypatch.setattr(token_limiter, "clock", c)
    monkeypatch.setattr(api_limiter, "clock", c)
    yield c
    token_limiter.reset()
    api_limiter.reset()


@pytest.fixture
def client(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
    return TestClient(app, client=("198.51.100.7", 50000)), {"Authorization": f"Bearer {token}"}


def _send(c, method, path, auth):
    kwargs = {"headers": auth}
    if method == "POST":
        kwargs["json"] = {}
    return c.request(method, path, **kwargs)


def test_finds_the_known_routes_with_require_token():
    found = set(ROUTES)
    for expected in [("POST", "/api/ingest"), ("GET", "/api/trips"), ("POST", "/api/trips")]:
        assert expected in found, f"{expected} has require_token but was not found in {sorted(found)}"


@pytest.mark.parametrize("method,path", ROUTES, ids=[f"{m} {p}" for m, p in ROUTES])
def test_token_limit_gives_429_with_retry_after(method, path, client, clock, monkeypatch):
    c, good = client
    monkeypatch.setattr(api_limiter, "MAX", 3)
    for i in range(3):
        r = _send(c, method, path, good)
        assert r.status_code not in (401, 429), f"{method} {path} request {i + 1} was limited early"
    r = _send(c, method, path, good)
    assert r.status_code == 429, f"{method} {path} over the token limit gave {r.status_code}"
    assert int(r.headers["Retry-After"]) > 0


@pytest.mark.parametrize("method,path", ROUTES, ids=[f"{m} {p}" for m, p in ROUTES])
def test_locked_address_gives_429_with_retry_after_even_with_valid_token(method, path, client, clock):
    c, good = client
    for _ in range(token_limiter.ADDRESS_MAX):
        token_limiter.failure("198.51.100.7")
    r = _send(c, method, path, good)
    assert r.status_code == 429, f"{method} {path} from a locked address gave {r.status_code}"
    assert int(r.headers["Retry-After"]) > 0
