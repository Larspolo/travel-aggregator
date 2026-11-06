"""README.md stays up to date with the code (owner, 2026-11-06): each API route of the app and each setting of the
.env.example files has a line in the README. A new route or setting with no README line fails here."""
import pathlib
import re

from app.main import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()


def test_each_api_route_is_in_the_readme():
    # the OpenAPI schema: app.routes holds included routers with no path in newer FastAPI versions
    routes = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() if p.startswith("/api") for m in ops}
    assert routes, "the app has no /api route"
    missing = sorted(f"`{m} {p}`" for m, p in routes if f"`{m} {p}`" not in README)
    assert not missing, f"add these routes to the API table of README.md: {missing}"


def test_each_setting_is_in_the_readme():
    names = {m for f in ROOT.glob("**/.env.example") if "framework" not in f.parts
             for m in re.findall(r"^([A-Z][A-Z0-9_]*)=", f.read_text(), re.M)}
    assert names, "no .env.example found"
    missing = sorted(n for n in names if f"`{n}`" not in README)
    assert not missing, f"add these settings to the Configuration table of README.md: {missing}"
