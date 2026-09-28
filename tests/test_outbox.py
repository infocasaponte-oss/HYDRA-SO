from uuid import uuid4

import pytest

from hydra.outbox import TransactionalOutbox


def test_outbox_commit_persists_message(tmp_path):
    outbox = TransactionalOutbox(tmp_path / "hydra.db")
    with outbox.transaction() as connection:
        outbox.enqueue(
            connection,
            topic="hydra.task.completed",
            aggregate_id=uuid4(),
            trace_id="trace",
            payload={"ok": True},
        )
    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0].payload == {"ok": True}


def test_outbox_rollback_is_atomic(tmp_path):
    outbox = TransactionalOutbox(tmp_path / "hydra.db")
    with pytest.raises(RuntimeError), outbox.transaction() as connection:
        outbox.enqueue(
            connection,
            topic="hydra.task.completed",
            aggregate_id=uuid4(),
            trace_id="trace",
            payload={"ok": True},
        )
        raise RuntimeError("boom")
    assert outbox.pending() == []
