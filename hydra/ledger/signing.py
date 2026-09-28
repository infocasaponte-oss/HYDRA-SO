# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Ed25519 signing for ledger events, release manifests, model artifacts and edge deltas.

Private keys live in ``<data_dir>/keys`` (or an external KMS/HSM in production: pass a
``Signer`` subclass). Workers only receive public keys."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from hydra.core.hashing import sha256_hex


class Signer:
    algorithm = "Ed25519"

    def __init__(self, private_key: Ed25519PrivateKey, key_id: str | None = None) -> None:
        self._key = private_key
        self.public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.key_id = key_id or f"hydra-{sha256_hex(self.public_pem)[:16]}"

    @classmethod
    def generate(cls) -> Signer:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def load_or_create(cls, directory: Path, name: str = "hydra-ed25519") -> Signer:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.pem"
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            assert isinstance(key, Ed25519PrivateKey)
            return cls(key)
        key = Ed25519PrivateKey.generate()
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        signer = cls(key)
        (directory / f"{name}.pub.pem").write_text(signer.public_pem, encoding="utf-8")
        return signer

    def sign(self, data: bytes | str) -> str:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return base64.b64encode(self._key.sign(data)).decode()

    def envelope(self, digest: str) -> dict:
        return {"algorithm": self.algorithm, "key_id": self.key_id, "digest": digest,
                "signature": self.sign(digest), "public_key": self.public_pem}


def verify_signature(public_pem: str, data: bytes | str, signature_b64: str) -> bool:
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        key = serialization.load_pem_public_key(public_pem.encode())
        assert isinstance(key, Ed25519PublicKey)
        key.verify(base64.b64decode(signature_b64), data)
        return True
    except (InvalidSignature, ValueError, AssertionError):
        return False


def verify_envelope(env: dict, trusted_keys: set[str] | None = None) -> bool:
    """Check a signature envelope; ``trusted_keys`` restricts which public keys are accepted."""
    if trusted_keys is not None and env.get("public_key") not in trusted_keys:
        return False
    return verify_signature(env.get("public_key", ""), env.get("digest", ""), env.get("signature", ""))
