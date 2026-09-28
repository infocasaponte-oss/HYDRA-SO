from fastapi.testclient import TestClient

from hydra import api
from hydra.security import SecurityConfig


def test_admin_metrics_requires_admin_token():
    original = api.security_config
    api.security_config = SecurityConfig(api_token=None, admin_token="admin-secret")
    try:
        with TestClient(api.app) as client:
            denied = client.get("/hydra/v1/admin/metrics")
            allowed = client.get(
                "/hydra/v1/admin/metrics",
                headers={"Authorization": "Bearer admin-secret"},
            )
    finally:
        api.security_config = original

    assert denied.status_code == 401
    assert allowed.status_code == 200
    body = allowed.json()
    assert "outbox_pending" in body
    assert "spans_total" in body
    assert "spans_by_name" in body
