"""Per-query model-call accounting.

A counter is installed by the query service for the duration of one query.
Provider calls that are served from the content cache do not increment it:
reusing cached evidence is free, which is exactly the saving the milestone-2
budget report needs to make visible. The counter is a context variable so
parallel verification workers share one thread-safe total.
"""

from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass, field


@dataclass
class ModelCallCounter:
    count: int = 0
    cache_reused: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def increment(self) -> None:
        with self._lock:
            self.count += 1

    def note_cache_reuse(self) -> None:
        with self._lock:
            self.cache_reused += 1


_current: contextvars.ContextVar[ModelCallCounter | None] = contextvars.ContextVar(
    "spatialtrace_model_calls", default=None
)


def install_counter() -> tuple[ModelCallCounter, contextvars.Token]:
    counter = ModelCallCounter()
    return counter, _current.set(counter)


def restore_counter(token: contextvars.Token) -> None:
    _current.reset(token)


def count_model_call() -> None:
    counter = _current.get()
    if counter is not None:
        counter.increment()


def count_cache_reuse() -> None:
    counter = _current.get()
    if counter is not None:
        counter.note_cache_reuse()


def activate(counter: ModelCallCounter):
    """Make ``counter`` current in this thread (used by verification workers,
    which do not inherit the query thread's context variables)."""
    return _current.set(counter)


def deactivate(token) -> None:
    _current.reset(token)
