"""Settings of the app from the environment."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    owner_password_hash: str
    # Web Push (#514): the VAPID key pair (base64url, raw) and the contact of the sender (a mailto: address).
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""


def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", ""),
        secret_key=os.environ.get("SECRET_KEY", ""),
        owner_password_hash=os.environ.get("OWNER_PASSWORD_HASH", ""),
        vapid_public_key=os.environ.get("VAPID_PUBLIC_KEY", ""),
        vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY", ""),
        vapid_subject=os.environ.get("VAPID_SUBJECT", ""),
    )
