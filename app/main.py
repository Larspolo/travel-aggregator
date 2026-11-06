"""The FastAPI app of travel-aggregator."""

import secrets

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api import health
from app.config import get_settings
from app.web import pages

app = FastAPI(title="travel-aggregator")
# With no SECRET_KEY, a random key: the sessions then end at each restart.
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().secret_key or secrets.token_hex(32),
    same_site="lax",
)
app.include_router(health.router, prefix="/api")
app.include_router(pages.router)
