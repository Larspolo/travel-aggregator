"""The FastAPI app of travel-aggregator."""

import re
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import metrics
from app.api import health, ingest, trips
from app.config import get_settings
from app.schemas import MAX_BODY_BYTES, MAX_HAR_BYTES
from app.web import booking_upload, calendar, export, manual, pages, passes, pinned, reparse, settings_export, share, sources, spend, trip_import, trip_merge, upcoming, userscripts

app = FastAPI(title="travel-aggregator")
# With no SECRET_KEY, a random key: the sessions then end at each restart.
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().secret_key or secrets.token_hex(32),
    same_site="lax",
)


# The upload of the captures page also takes a HAR file (#1563): its route checks the file size; the margin is the
# multipart form around the file.
UPLOAD_PATH = re.compile(r"/trips/\d+/captures/upload")
UPLOAD_MARGIN = 100_000


@app.middleware("http")
async def limit_body(request: Request, call_next):
    """A body with a method that sends one needs a Content-Length of at most MAX_BODY_BYTES (P5). The check comes
    before the body is read: FastAPI reads the whole body before the dependencies of a route."""
    if request.method in ("POST", "PUT", "PATCH"):
        size = request.headers.get("content-length")
        if size is None:
            return JSONResponse({"detail": "Content-Length is required"}, status_code=411)
        limit = MAX_HAR_BYTES + UPLOAD_MARGIN if UPLOAD_PATH.fullmatch(request.url.path) else MAX_BODY_BYTES
        if not size.isdigit() or int(size) > limit:
            return JSONResponse({"detail": f"the body is larger than {limit} bytes"}, status_code=413)
    return await call_next(request)


app.include_router(health.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(trip_import.router)  # before pages: /trips/{trip_id} also matches /trips/import
app.include_router(settings_export.router)  # before pages
app.include_router(trip_merge.router)  # before pages: /trips/{trip_id}/merge
app.include_router(metrics.router)  # before pages
app.include_router(pages.router)
app.include_router(booking_upload.router)
app.include_router(share.router)
app.include_router(manual.router)
app.include_router(sources.router)
app.include_router(reparse.router)
app.include_router(export.router)
app.include_router(calendar.router)
app.include_router(upcoming.router)
app.include_router(spend.router)
app.include_router(pinned.router)
app.include_router(passes.router)
app.include_router(userscripts.router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")
