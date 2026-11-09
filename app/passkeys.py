"""The passkeys of the owner: the registration of a WebAuthn credential on the settings page (#1558) and the login
with a stored passkey (#1559).

The challenge stays in the login session until the browser sends the new credential. The relying party id and the
origin come from the request (the reverse proxy sends X-Forwarded-Proto and Host), or from PASSKEY_ORIGIN.
"""

import json
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import webauthn
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement, UserVerificationRequirement)

from app.config import get_settings
from app.models import Passkey

CHALLENGE_KEY = "passkey_challenge"  # the login session key: the challenge and its time
LOGIN_CHALLENGE_KEY = "passkey_login_challenge"  # the same for the login page
CHALLENGE_MAX = 300  # seconds
USER_ID = b"travel-aggregator-owner"  # the app has one user
MAX_NAME = 100


class PasskeyError(ValueError):
    """The registration or the login is not correct: the message is for the owner."""


def origin(request: Request) -> str:
    return get_settings().passkey_origin or f"{request.url.scheme}://{request.url.netloc}"


def rp_id(request: Request) -> str:
    return urlsplit(origin(request)).hostname or ""


def listing(session: Session) -> list[Passkey]:
    return list(session.scalars(select(Passkey).order_by(Passkey.created_at, Passkey.id)))


def registration_options(request: Request, session: Session) -> str:
    """The options of navigator.credentials.create() as JSON; the challenge goes into the login session."""
    options = webauthn.generate_registration_options(
        rp_id=rp_id(request), rp_name="travel-aggregator", user_name="owner", user_id=USER_ID,
        user_display_name="Owner",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED, user_verification=UserVerificationRequirement.PREFERRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=p.credential_id) for p in listing(session)])
    request.session[CHALLENGE_KEY] = [bytes_to_base64url(options.challenge), time.time()]
    return webauthn.options_to_json(options)


def _challenge(request: Request, key: str = CHALLENGE_KEY) -> bytes:
    """The challenge of the last options, one time only."""
    saved = request.session.pop(key, None)
    if not isinstance(saved, list) or len(saved) != 2 or not 0 <= time.time() - saved[1] <= CHALLENGE_MAX:
        raise PasskeyError("The request is too old. Try again.")
    return webauthn.base64url_to_bytes(saved[0])


def register(request: Request, session: Session, name: str, credential: dict) -> Passkey:
    """Check the new credential against the challenge, the relying party id and the origin, then store it."""
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        raise PasskeyError(f"Give the passkey a name of 1 to {MAX_NAME} characters.")
    challenge = _challenge(request)
    try:
        verified = webauthn.verify_registration_response(
            credential=json.dumps(credential), expected_challenge=challenge, expected_rp_id=rp_id(request),
            expected_origin=origin(request))
    except (WebAuthnException, ValueError, TypeError, KeyError) as e:
        raise PasskeyError(f"The passkey is not correct: {e}") from e
    if session.scalar(select(Passkey).where(Passkey.credential_id == verified.credential_id)) is not None:
        raise PasskeyError("This passkey is already added.")
    row = Passkey(credential_id=verified.credential_id, public_key=verified.credential_public_key,
                  sign_count=verified.sign_count, name=name)
    session.add(row)
    session.commit()
    return row


def authentication_options(request: Request) -> str:
    """The options of navigator.credentials.get() as JSON: no list of credentials, the device offers its passkey."""
    options = webauthn.generate_authentication_options(
        rp_id=rp_id(request), user_verification=UserVerificationRequirement.PREFERRED)
    request.session[LOGIN_CHALLENGE_KEY] = [bytes_to_base64url(options.challenge), time.time()]
    return webauthn.options_to_json(options)


def authenticate(request: Request, session: Session, credential: dict) -> Passkey:
    """Check a login with a stored passkey; a good one gets the new sign count and the time of its last use."""
    challenge = _challenge(request, LOGIN_CHALLENGE_KEY)
    try:
        raw_id = webauthn.base64url_to_bytes(str(credential.get("rawId") or credential.get("id") or ""))
    except (ValueError, TypeError) as e:
        raise PasskeyError("The passkey is not correct.") from e
    row = session.scalar(select(Passkey).where(Passkey.credential_id == raw_id)) if raw_id else None
    if row is None:
        raise PasskeyError("This passkey is not known here. It was removed, or it is for another server.")
    try:
        verified = webauthn.verify_authentication_response(
            credential=json.dumps(credential), expected_challenge=challenge, expected_rp_id=rp_id(request),
            expected_origin=origin(request), credential_public_key=row.public_key,
            credential_current_sign_count=row.sign_count)
    except (WebAuthnException, ValueError, TypeError, KeyError) as e:
        raise PasskeyError(f"The passkey is not correct: {e}") from e
    row.sign_count = verified.new_sign_count
    row.last_used_at = datetime.now(timezone.utc)
    return row
