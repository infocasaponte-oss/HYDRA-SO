# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from hydra.api import native_access
from hydra.audit import access
from hydra.runtime import api, security, security_audit


def test_facade_and_legacy_imports_share_access_control():
    assert security is native_access
    assert api.require_api_access is native_access.require_api_access
    assert api.require_admin_access is native_access.require_admin_access


def test_audit_implementation_is_shared():
    assert security_audit is access
    assert api.SecurityAudit is access.SecurityAudit
