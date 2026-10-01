# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Provision/revoke application keys without displaying credentials."""
import argparse
import json
import re
import secrets
from pathlib import Path

from hydra.api.client_keys import digest
from hydra.core.atomic import write_text_atomic


def provision(client, limit, revoke=False):
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,63}', client) or not 1 <= limit <= 10000:
        raise ValueError('Invalid client ID or rate limit')
    registry = Path('data/keys/api-clients.json')
    delivery = Path('data/secrets/client-credentials') / (client + '.env')
    registry.parent.mkdir(parents=True, exist_ok=True)
    delivery.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(registry.read_text(encoding='utf-8')) if registry.exists() else {'clients': []}
    existing = next((row for row in data['clients'] if row['id'] == client), None)
    if revoke:
        if existing is None:
            raise ValueError('Unknown client')
        existing['enabled'] = False
    elif existing:
        raise ValueError('Client already exists; explicit revocation required before creating a new ID')
    else:
        if delivery.exists():
            raise ValueError('Credential file already exists')
        token = 'hydra_' + secrets.token_urlsafe(32)
        write_text_atomic(delivery, 'HYDRA_BASE_URL=http://127.0.0.1:18088/v1\nHYDRA_API_KEY=' + token + '\n')
        data['clients'].append({'id': client, 'sha256': digest(token), 'enabled': True,
                                'requests_per_minute': limit, 'scope': 'inference'})
    write_text_atomic(registry, json.dumps(data, indent=2))
    print(json.dumps({'client': client, 'revoked': revoke, 'credential_file': str(delivery.resolve()),
                      'registry': str(registry.resolve())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('client')
    parser.add_argument('--limit', type=int, default=30)
    parser.add_argument('--revoke', action='store_true')
    args = parser.parse_args()
    provision(args.client, args.limit, args.revoke)
