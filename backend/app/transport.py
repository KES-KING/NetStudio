"""Shared, fenced execution contract for read-only collection transports."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import time
from typing import Awaitable, Callable, Literal, Protocol, TypeVar

from .collection import ReadResult
from .contracts import ManagedDevice
from .ssh import ConnectionPolicyError


TransportKind = Literal["ssh", "snmp", "api"]
T = TypeVar("T")


@dataclass(frozen=True)
class TransportContext:
    """One collection attempt's immutable target, deadline, and fence callback.

    The callback is deliberately synchronous: it performs the same durable job
    lease/session/target checks already used by the worker.  Every transport
    checks it immediately before and after network waits.
    """

    store: object
    vault: object
    device: ManagedDevice
    authorize: Callable[[], None] = field(default=lambda: None, repr=False)
    deadline: float = field(default_factory=lambda: time.monotonic() + 180)

    @classmethod
    def create(cls, store, vault, device, authorize=lambda: None, *, timeout_seconds: float = 180):
        if timeout_seconds <= 0:
            raise ValueError("transport_deadline_invalid")
        return cls(store, vault, device, authorize, time.monotonic() + timeout_seconds)

    def checkpoint(self) -> None:
        self.authorize()
        if self.remaining <= 0:
            raise ConnectionPolicyError("transport_deadline_exceeded")

    @property
    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def bounded(self, timeout_seconds: float) -> "TransportContext":
        if timeout_seconds <= 0:
            raise ValueError("transport_deadline_invalid")
        return TransportContext(
            self.store, self.vault, self.device, self.authorize,
            min(self.deadline, time.monotonic() + timeout_seconds),
        )

    async def wait(self, operation: Awaitable[T], *, timeout_seconds: float | None = None) -> T:
        self.checkpoint()
        timeout = self.remaining
        if timeout_seconds is not None:
            timeout = min(timeout, timeout_seconds)
        if timeout <= 0:
            if hasattr(operation, "close"):
                operation.close()  # Avoid an un-awaited coroutine on an expired deadline.
            raise ConnectionPolicyError("transport_deadline_exceeded")
        try:
            result = await asyncio.wait_for(operation, timeout)
        except asyncio.TimeoutError as error:
            raise ConnectionPolicyError("transport_timeout") from error
        self.checkpoint()
        return result


class TransportAdapter(Protocol):
    """Common protocol implemented by SSH, SNMP and future API adapters."""

    kind: TransportKind

    async def collect(self, context: TransportContext, groups: set[str]) -> ReadResult: ...


class SSHTransportAdapter:
    kind: Literal["ssh"] = "ssh"

    async def collect(self, context: TransportContext, groups: set[str]) -> ReadResult:
        # Import lazily to avoid coupling the protocol to a concrete driver set.
        from .drivers import collect

        context.checkpoint()
        result = await context.wait(
            collect(context.store, context.vault, context.device, groups, context.checkpoint)
        )
        context.checkpoint()
        return result

