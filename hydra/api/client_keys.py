# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Hashed, revocable application keys. Clients receive inference access only."""
from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from fastapi import HTTPException

INFERENCE_ROUTES = {
    ('POST', '/v1/chat/completions'), ('POST', '/v1/responses'),
    ('GET', '/v1/models'),
}


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def lookup(path, token):
    if not token or not Path(path).exists():
        return None
    try:
        rows = json.loads(Path(path).read_text(encoding='utf-8'))['clients']
        for row in rows:
            if secrets.compare_digest(digest(token), row['sha256']):
                if not row.get('enabled', False):
                    raise HTTPException(401, 'client key revoked')
                return row
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'client key registry unavailable') from None
    return None


def client_route(identity, method, path):
    if identity.startswith('client:') and (method, path) not in INFERENCE_ROUTES:
        raise HTTPException(403, 'client key permits inference only')
