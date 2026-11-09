"""A small software authenticator for the passkey tests (#1559): an ES256 key, "none" attestation.

`create()` gives the answer of navigator.credentials.create() and `get()` the answer of navigator.credentials.get(),
in the form of PublicKeyCredential.toJSON().
"""

import hashlib
import json
import os

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url


def _b64(data: bytes) -> str:
    return bytes_to_base64url(data)


class Device:
    def __init__(self, credential_id: bytes | None = None):
        self.credential_id = credential_id or os.urandom(16)
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.count = 0

    def _client_data(self, kind: str, challenge: str, origin: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False}).encode()

    def create(self, options: dict, origin: str, challenge: str | None = None) -> dict:
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})
        auth_data = (hashlib.sha256(options["rp"]["id"].encode()).digest() + bytes([0x45]) + (0).to_bytes(4, "big")
                     + bytes(16) + len(self.credential_id).to_bytes(2, "big") + self.credential_id + cose)
        client_data = self._client_data("webauthn.create", challenge or options["challenge"], origin)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {"id": _b64(self.credential_id), "rawId": _b64(self.credential_id), "type": "public-key",
                "clientExtensionResults": {},
                "response": {"clientDataJSON": _b64(client_data), "attestationObject": _b64(attestation)}}

    def get(self, options: dict, origin: str, challenge: str | None = None) -> dict:
        self.count += 1
        auth_data = hashlib.sha256(options["rpId"].encode()).digest() + bytes([0x05]) + self.count.to_bytes(4, "big")
        client_data = self._client_data("webauthn.get", challenge or options["challenge"], origin)
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": _b64(self.credential_id), "rawId": _b64(self.credential_id), "type": "public-key",
                "clientExtensionResults": {},
                "response": {"clientDataJSON": _b64(client_data), "authenticatorData": _b64(auth_data),
                             "signature": _b64(signature), "userHandle": _b64(b"travel-aggregator-owner")}}
