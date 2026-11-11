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
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    # The new-issue form of the "Report on GitHub" link (#929): a fork reports to its own repository.
    issues_url: str = "https://github.com/Larspolo/travel-aggregator/issues/new"
    # The origin of the passkeys (#1558), for example https://travel.example.com: empty is the origin of the request.
    passkey_origin: str = ""


def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", ""),
        secret_key=os.environ.get("SECRET_KEY", ""),
        owner_password_hash=os.environ.get("OWNER_PASSWORD_HASH", ""),
        vapid_public_key=os.environ.get("VAPID_PUBLIC_KEY", ""),
        vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY", ""),
        vapid_subject=os.environ.get("VAPID_SUBJECT", ""),
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=int(os.environ.get("SMTP_PORT") or 587),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_from=os.environ.get("SMTP_FROM", ""),
        issues_url=os.environ.get("ISSUES_URL") or "https://github.com/Larspolo/travel-aggregator/issues/new",
        passkey_origin=os.environ.get("PASSKEY_ORIGIN", "").rstrip("/"),
    )
