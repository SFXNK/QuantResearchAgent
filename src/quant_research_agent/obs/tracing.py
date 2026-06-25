"""OpenTelemetry tracing setup.

Defaults to a no-op tracer so the harness has zero overhead and no external
dependencies at runtime. Set QRA_TRACE=console to print spans, or wire
an OTLP exporter in your own deployment.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from collections.abc import Iterator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

_CONFIGURED = False


def configure_tracing() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    provider = TracerProvider()
    if os.environ.get("QRA_TRACE") == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _CONFIGURED = True


def get_tracer(name: str = "quant_research_agent"):  # noqa: ANN201
    configure_tracing()
    return trace.get_tracer(name)


@contextmanager
def span(name: str, **attributes: object) -> Iterator[None]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            s.set_attribute(k, v)  # type: ignore[arg-type]
        yield
