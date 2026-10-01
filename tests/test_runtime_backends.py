# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""F3: the runtime line's hash chains (events, provenance) on the event log, files or PostgreSQL.

PostgreSQL cases need HYDRA_IT_POSTGRES (``pg_url`` in conftest gives each test its own database)."""
from __future__ import annotations

import threading
from uuid import uuid4

import pytest

from hydra.core.eventlog import FileLog, LogSpace
from hydra.runtime.events import JsonlEventStore
from hydra.runtime.provenance import ProvenanceLedger, ProvenanceRecord


def _event(store, aggregate, i, source=None):
    return store.append(event_type="hydra.test", aggregate_id=aggregate, producer="test", trace_id=f"t{i}",
                        payload={"i": i}, source_message_id=source)


def _record(i, source=None):
    return ProvenanceRecord(task_id=uuid4(), trace_id=f"t{i}", action="test", inputs={"i": i},
                            source_message_id=source)


@pytest.fixture(params=["file", "postgres"])
def logs(request, tmp_path):
    if request.param == "file":
        yield None
        return
    space = LogSpace(request.getfixturevalue("pg_url"), label="runtime")
    yield space
    space.close()


def _stores(logs, tmp_path):
    if logs is None:
        return JsonlEventStore(tmp_path / "events.jsonl"), ProvenanceLedger(tmp_path / "provenance.jsonl")
    return (JsonlEventStore(tmp_path / "events.jsonl", log=logs.open(tmp_path / "events.jsonl", JsonlEventStore.STREAM)),
            ProvenanceLedger(tmp_path / "provenance.jsonl",
                             log=logs.open(tmp_path / "provenance.jsonl", ProvenanceLedger.STREAM)))


def test_chain_contract_on_both_backends(logs, tmp_path):
    events, provenance = _stores(logs, tmp_path)
    aggregate, source = uuid4(), uuid4()
    first = _event(events, aggregate, 1, source)
    assert _event(events, aggregate, 2, source) == first  # idempotent by source message
    second = _event(events, aggregate, 3)
    assert (first.sequence, second.sequence, second.previous_hash) == (1, 2, first.event_hash)
    assert events.head == second.event_hash and events.verify_integrity().valid
    assert [e.sequence for e in events.for_aggregate(aggregate)] == [1, 2]
    r1 = provenance.append(_record(1, source))
    assert provenance.append(_record(2, source)).record_hash == r1.record_hash
    r2 = provenance.append(_record(3))
    assert r2.previous_hash == r1.record_hash and provenance.head == r2.record_hash
    assert provenance.verify_integrity().valid and provenance.verify_integrity().records == 2


def test_several_instances_on_one_file_keep_one_chain(tmp_path):
    a, b = JsonlEventStore(tmp_path / "e.jsonl"), JsonlEventStore(tmp_path / "e.jsonl")
    aggregate = uuid4()
    _event(a, aggregate, 1)
    _event(b, aggregate, 2)  # b sees a's event before chaining
    _event(a, aggregate, 3)
    report = JsonlEventStore(tmp_path / "e.jsonl").verify_integrity()
    assert report.valid and report.records == 3
    assert len(FileLog(tmp_path / "e.jsonl")) == 3


def test_nodes_build_one_valid_chain_without_duplicates(pg_url, tmp_path):
    nodes = [_stores(LogSpace(pg_url, label="runtime"), tmp_path / f"n{k}") for k in range(4)]
    shared_source = uuid4()
    aggregate = uuid4()

    def work(k):
        events, provenance = nodes[k]
        for i in range(10):
            _event(events, aggregate, i)
            provenance.append(_record(i))
        _event(events, aggregate, 99, shared_source)  # the same outbox message replayed by every node
        provenance.append(_record(99, shared_source))

    threads = [threading.Thread(target=work, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    events, provenance = nodes[0]
    report = events.verify_integrity()
    assert report.valid and report.records == 41
    assert [e.sequence for e in events.for_aggregate(aggregate)] == list(range(1, 42))
    assert provenance.verify_integrity().valid and provenance.verify_integrity().records == 41
    assert {n[0].head for n in nodes} == {events.head}


def test_existing_chain_files_are_imported_and_continue(pg_url, tmp_path):
    local_events, local_provenance = _stores(None, tmp_path)
    aggregate = uuid4()
    last = _event(local_events, aggregate, 1)
    local_provenance.append(_record(1))
    space = LogSpace(pg_url, label="runtime")
    events, provenance = _stores(space, tmp_path)
    assert events.head == last.event_hash
    nxt = _event(events, aggregate, 2)
    assert nxt.sequence == 2 and nxt.previous_hash == last.event_hash and events.verify_integrity().valid
    assert provenance.verify_integrity().records == 1
    space.close()


def test_runtime_backend_follows_the_settings(monkeypatch):
    from hydra.core.config import Settings
    from hydra.runtime.config import Settings as RuntimeSettings

    monkeypatch.setenv("HYDRA_RUNTIME_BACKEND", "postgres")
    monkeypatch.setenv("HYDRA_POSTGRES_URL", "postgresql://x/y")
    view = RuntimeSettings.from_platform(Settings(_env_file=None))
    assert (view.runtime_backend, view.postgres_url) == ("postgres", "postgresql://x/y")


def test_file_log_rereads_a_rewritten_file(tmp_path):
    path = tmp_path / "x.jsonl"
    log = FileLog(path)
    for i in range(3):
        log.append(f'{{"i": {i}}}')
    assert [s for s, _ in log.read(2)] == [3]  # resumes from the cached tail
    path.write_text('{"i":   "rewritten history, longer than before"}\n', encoding="utf-8")
    assert len(log) == 1 and [line for _, line in log.read()] == ['{"i":   "rewritten history, longer than before"}']
    assert log.append('{"i": 9}')[0] == 2
