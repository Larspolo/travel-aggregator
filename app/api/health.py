"""Health check of the app."""

import functools
import os

from fastapi import APIRouter

router = APIRouter()


@functools.cache
def _built() -> str:
    # The build time of the image, written by the Dockerfile; "dev" outside an image.
    try:
        with open(os.environ.get("BUILD_TIME_FILE", "/app/BUILD_TIME"), encoding="utf-8") as file:
            return file.readline().rstrip("\r\n")
    except FileNotFoundError:
        return "dev"


@router.get("/health")
def health() -> dict[str, str]:
    # The commit of the image (build argument GIT_SHA): /try and the owner see which version the preview runs.
    return {"status": "ok", "commit": os.environ.get("GIT_SHA", "dev"), "built": _built()}
