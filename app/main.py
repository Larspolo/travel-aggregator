"""The FastAPI app of travel-aggregator."""

from fastapi import FastAPI

from app.api import health

app = FastAPI(title="travel-aggregator")
app.include_router(health.router, prefix="/api")
