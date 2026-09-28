from hydra.observability import CognitiveTracer, TraceStore
from hydra.operating_metrics import collect_operating_metrics
from hydra.outbox import TransactionalOutbox


def test_operating_metrics_aggregate_spans_and_outbox(tmp_path):
    traces = tmp_path / "traces.jsonl"
    tracer = CognitiveTracer(TraceStore(traces))
    with tracer.span("routing", trace_id="trace"):
        pass
    with tracer.span("execution", trace_id="trace"):
        pass

    metrics = collect_operating_metrics(
        outbox=TransactionalOutbox(tmp_path / "hydra.db"),
        trace_path=traces,
    )

    assert metrics.outbox_pending == 0
    assert metrics.spans_total == 2
    assert metrics.spans_error == 0
    assert metrics.spans_by_name == {"execution": 1, "routing": 1}
    assert metrics.avg_span_duration_ms is not None
