"""Health check of the app."""

import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    # The commit of the image (build argument GIT_SHA): /try and the owner see which version the preview runs.
    return {"status": "ok", "commit": os.environ.get("GIT_SHA", "dev")}
