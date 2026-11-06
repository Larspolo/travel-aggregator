"""The FastAPI app of travel-aggregator."""

import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api import health, ingest, trips
from app.config import get_settings
from app.schemas import MAX_BODY_BYTES
from app.web import manual, pages, reparse, sources

app = FastAPI(title="travel-aggregator")
# With no SECRET_KEY, a random key: the sessions then end at each restart.
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().secret_key or secrets.token_hex(32),
    same_site="lax",
)


@app.middleware("http")
async def limit_body(request: Request, call_next):
    """A body with a method that sends one needs a Content-Length of at most MAX_BODY_BYTES (P5). The check comes
    before the body is read: FastAPI reads the whole body before the dependencies of a route."""
    if request.method in ("POST", "PUT", "PATCH"):
        size = request.headers.get("content-length")
        if size is None:
            return JSONResponse({"detail": "Content-Length is required"}, status_code=411)
        if not size.isdigit() or int(size) > MAX_BODY_BYTES:
            return JSONResponse({"detail": f"the body is larger than {MAX_BODY_BYTES} bytes"}, status_code=413)
    return await call_next(request)


app.include_router(health.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(pages.router)
app.include_router(manual.router)
app.include_router(sources.router)
app.include_router(reparse.router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")
