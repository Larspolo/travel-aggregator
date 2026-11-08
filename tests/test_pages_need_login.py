"""Each page needs the owner login, except a short list of public routes (#996).

The preview has no Traefik basic auth in front of the pages (owner, #996: option 3): the app login is the only
protection, as on the real instance (`deploy/traefik/`). A new page route without `require_login` then shows its
data to anyone who opens the URL. This test finds such a route at once."""

from fastapi.routing import APIRoute

from app.auth import require_login
from app.main import app

# The routes that work with no login, and why. Add a route here only with a reason.
PUBLIC = {
    ("GET", "/login"): "the login form",
    ("POST", "/login"): "the login itself (CSRF token)",
    ("GET", "/logout"): "ends the session",
    ("POST", "/logout"): "ends the session",
    ("GET", "/sw.js"): "the service worker script of the installed app, no data",
    ("GET", "/manifest.webmanifest"): "the app manifest, no data",
    ("GET", "/s/{token}"): "a share link: the random token is the access",
    ("GET", "/userscripts/{name}"): "the userscript install for Tampermonkey, no data",
    # The docs of FastAPI: only the schema, the repository is public.
    ("GET", "/openapi.json"): "FastAPI schema",
    ("GET", "/docs"): "FastAPI docs",
    ("GET", "/docs/oauth2-redirect"): "FastAPI docs",
    ("GET", "/redoc"): "FastAPI docs",
}


def _routes(routes, prefix="", deps=()):
    """Yield (path, route, dependencies of the include) for each route, also in the included routers."""
    for route in routes:
        context = getattr(route, "include_context", None)
        if context is not None:
            yield from _routes(route.original_router.routes, prefix + context.prefix,
                               deps + tuple(context.dependencies))
        else:
            yield prefix + getattr(route, "path", ""), route, deps


def _calls(dependant):
    for sub in dependant.dependencies:
        yield sub.call
        yield from _calls(sub)


def _page_routes():
    for path, route, deps in _routes(app.routes):
        if path.startswith("/api") or not hasattr(route, "methods"):
            continue  # the API has its own tokens (require_token); /static is a mount of files
        for method in sorted(route.methods - {"HEAD"}):
            yield method, path, route, deps


def test_the_walk_finds_the_pages():
    found = {(m, p) for m, p, _, _ in _page_routes()}
    assert ("GET", "/") in found and ("GET", "/login") in found
    assert not any(p.startswith("/api") for _, p in found)


def test_each_page_needs_the_login():
    open_routes = []
    for method, path, route, deps in _page_routes():
        if (method, path) in PUBLIC:
            continue
        calls = {d.dependency for d in deps}
        if isinstance(route, APIRoute):
            calls |= set(_calls(route.dependant))
        if require_login not in calls:
            open_routes.append(f"{method} {path}")
    assert not open_routes, f"routes with no require_login (add it, or add the route to PUBLIC with a reason): {open_routes}"


def test_the_public_list_has_no_old_routes():
    found = {(m, p) for m, p, _, _ in _page_routes()}
    assert not set(PUBLIC) - found, f"PUBLIC names routes that do not exist: {set(PUBLIC) - found}"
