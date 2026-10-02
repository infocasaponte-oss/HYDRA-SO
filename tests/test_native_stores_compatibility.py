# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from hydra.core import native_stores
from hydra.runtime import api, pg_stores


def test_legacy_and_http_facade_share_store_factory():
    assert pg_stores is native_stores
    assert api.open_runtime_stores is native_stores.open_runtime_stores
