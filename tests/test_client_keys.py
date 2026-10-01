# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from hydra.api.client_keys import client_route, digest
from hydra.api.security import authenticate


def test_client_keys_revocation_and_scope(tmp_path):
    path = tmp_path / 'keys.json'
    row = {'id': 'celtia', 'sha256': digest('secret'), 'enabled': True}
    path.write_text(json.dumps({'clients': [row]}))
    settings = SimpleNamespace(client_keys_file=path, api_key='operator')
    assert authenticate(settings, '10.0.0.2', 'secret') == 'client:celtia'
    client_route('client:celtia', 'POST', '/v1/chat/completions')
    for route in ['/hydra/v1/goals', '/hydra/v1/edge/sync/import', '/v1/hydra']:
        with pytest.raises(HTTPException) as error:
            client_route('client:celtia', 'POST', route)
        assert error.value.status_code == 403
    row['enabled'] = False
    path.write_text(json.dumps({'clients': [row]}))
    with pytest.raises(HTTPException):
        authenticate(settings, '127.0.0.1', 'secret')


def test_unknown_token_does_not_gain_local_access(tmp_path):
    settings = SimpleNamespace(client_keys_file=tmp_path / 'missing', api_key='')
    with pytest.raises(HTTPException) as error:
        authenticate(settings, '127.0.0.1', 'wrong')
    assert error.value.status_code == 401
    assert authenticate(settings, '127.0.0.1', None).startswith('local:')


def test_gateway_blocks_client_before_admin_or_task_execution(tmp_path):
    from fastapi.testclient import TestClient
    from hydra.api.main import create_app
    from hydra.core.config import Settings

    path = tmp_path / 'clients.json'
    path.write_text(json.dumps({'clients': [
        {'id': 'nova-ai', 'sha256': digest('nova-secret'), 'enabled': True,
         'requests_per_minute': 30}]}))
    settings = Settings(client_keys_file=path, api_key='', admin_token='', runtime_api=False)
    # No lifespan: blocked requests must never reach the engine or its state.
    client = TestClient(create_app(settings))
    response = client.post('/hydra/v1/goals', headers={'X-API-Key': 'nova-secret'},
                           json={'goal': 'do something'})
    assert response.status_code == 403
    assert response.json()['detail'] == 'client key permits inference only'
