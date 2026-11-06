"""Settings of the app from the environment."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    owner_password_hash: str


def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", ""),
        secret_key=os.environ.get("SECRET_KEY", ""),
        owner_password_hash=os.environ.get("OWNER_PASSWORD_HASH", ""),
    )
