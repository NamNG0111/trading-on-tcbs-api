"""In-process counter/timer primitives (Phase 6).

`record_metric(name, value, **labels)` writes one structured log event
on the `v2.metrics` logger. The first iteration is intentionally
log-shaped — every metric is just a JSON line you can grep — because
that's enough to answer "what did the system do in the last hour?"
without standing up Prometheus today.

Phase-7+ can flip the implementation to a real counter registry without
changing call sites: the same `record_metric` call would also `inc()`
the underlying counter.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from .logger import get_logger, log_event

_metrics_logger = get_logger("metrics")


def record_metric(name: str, value: float = 1.0, **labels: Any) -> None:
    """Emit one metric event on the `v2.metrics` logger.

    Args:
        name: Stable metric id (e.g. `"data.fetch.hit"`,
            `"orders.placed"`). Use dotted, lowercase names.
        value: Numeric value. For counters pass the increment (default 1);
            for gauges/timers pass the current reading.
        labels: Free-form dimensions (`symbol="HPG"`, `strategy="RSI"`).
    """
    log_event(_metrics_logger, "metric", metric=name, value=value, **labels)


@contextmanager
def timed(name: str, **labels: Any) -> Iterator[None]:
    """Context manager that emits a duration metric on exit.

    Example:
        >>> with timed("scan.duration_ms", n_symbols=len(symbols)):
        ...     scanner.scan(symbols)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        record_metric(name, value=elapsed_ms, **labels)
