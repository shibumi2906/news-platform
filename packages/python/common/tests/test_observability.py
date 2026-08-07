from common.observability import MetricsRegistry, trace_context


def test_metrics_registry_renders_prometheus_text() -> None:
    registry = MetricsRegistry()
    registry.increment("jobs_total", status="ok")
    registry.increment("jobs_total", status="ok")
    assert 'jobs_total{status="ok"} 2' in registry.render()


def test_trace_context_preserves_valid_trace_id_and_rejects_invalid() -> None:
    trace_id, header = trace_context("00-0123456789abcdef0123456789abcdef-0123456789abcdef-01")
    assert trace_id == "0123456789abcdef0123456789abcdef"
    assert header.startswith(f"00-{trace_id}-")
    generated, _ = trace_context("personal text must not reach logs")
    assert generated != trace_id
    assert len(generated) == 32
