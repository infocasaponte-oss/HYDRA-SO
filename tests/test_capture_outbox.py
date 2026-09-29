# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from hydra.core.capture_outbox import CaptureOutbox
from hydra.core.contracts import HydraRequest, Message
from hydra.runtime.outbox_worker import RetryPolicy


def _ask(text: str) -> HydraRequest:
    return HydraRequest(messages=[Message(role="user", content=text)], use_cache=False)


async def test_failed_ledger_write_is_deferred_and_replayed(runtime, monkeypatch):
    ledger = runtime.ledger
    real_append = ledger.append
    calls = {"n": 0}

    def flaky(event_type, payload, **options):
        if event_type == "TASK_EXECUTED" and calls["n"] == 0:
            calls["n"] += 1
            raise OSError("disk full")
        return real_append(event_type, payload, **options)

    monkeypatch.setattr(ledger, "append", flaky)
    response = await runtime.kernel.run(_ask("¿Cuánto es 20+22?"))
    task_id = response.meta.task_id
    assert "ledger" in response.learning["deferred"]
    assert runtime.capture_outbox.stats()["pending"] == 1
    assert not any(e.payload.get("task") == task_id for e in ledger.events())

    result = runtime.capture_outbox.drain()
    assert result.published == 1 and runtime.capture_outbox.stats()["pending"] == 0
    replayed = [e for e in ledger.events() if e.event_type == "TASK_EXECUTED" and e.payload.get("task") == task_id]
    assert len(replayed) == 1 and ledger.verify().ok


async def test_capture_without_failures_defers_nothing(runtime):
    response = await runtime.kernel.run(_ask("¿Cuánto es 1+1?"))
    assert "deferred" not in response.learning
    assert runtime.capture_outbox.stats() == {"pending": 0, "dead_letters": 0}


def test_capture_outbox_is_visible_through_the_api(settings):
    from fastapi.testclient import TestClient

    from hydra.api.main import create_app

    with TestClient(create_app(settings)) as client:
        assert client.get("/hydra/v1/capture/outbox").json() == {"pending": 0, "dead_letters": 0, "messages": []}


def test_persistent_failure_ends_in_dead_letter_queue(tmp_path):
    class BrokenLedger:
        def append(self, *args, **kwargs):
            raise OSError("read-only filesystem")

    outbox = CaptureOutbox(tmp_path / "capture_outbox.db", ledger=BrokenLedger(),
                           policy=RetryPolicy(max_attempts=2, base_delay_seconds=0))
    outbox.defer("capture.ledger", "task-1", {"event_type": "TASK_EXECUTED", "payload": {"task": "task-1"}})
    assert outbox.drain().retried == 1
    assert outbox.drain().dead_lettered == 1
    assert outbox.stats() == {"pending": 0, "dead_letters": 1}
    [dead] = outbox.dead_letters()
    assert dead["topic"] == "capture.ledger" and "read-only" in dead["last_error"]
