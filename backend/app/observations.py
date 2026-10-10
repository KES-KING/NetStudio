"""Observation and counter-rate helpers for collectors.

Only pure calculations and a deterministic fixture collector live here. SSH or
SNMP transports will be injected behind the same collector contract later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from .models import Device, InterfaceObservation, PollSnapshot, ReadQuality


@dataclass(frozen=True)
class CounterSample:
    interface_id: str
    in_octets: int
    out_octets: int
    observed_at: datetime
    discontinuity_at: datetime | None = None


@dataclass(frozen=True)
class CounterRate:
    rx_bps: float | None
    tx_bps: float | None
    quality: Literal["ok", "unknown"]
    reason: str | None = None


def calculate_counter_rate(previous: CounterSample | None, current: CounterSample) -> CounterRate:
    """Return a safe rate; never turn a missing/reset counter into zero."""

    if previous is None:
        return CounterRate(None, None, "unknown", "baseline_required")
    elapsed = (current.observed_at - previous.observed_at).total_seconds()
    if elapsed <= 0:
        return CounterRate(None, None, "unknown", "invalid_interval")
    if current.discontinuity_at != previous.discontinuity_at:
        return CounterRate(None, None, "unknown", "counter_discontinuity")
    if current.in_octets < previous.in_octets or current.out_octets < previous.out_octets:
        return CounterRate(None, None, "unknown", "counter_reset")
    return CounterRate(
        8 * (current.in_octets - previous.in_octets) / elapsed,
        8 * (current.out_octets - previous.out_octets) / elapsed,
        "ok",
    )


class FixtureCollector:
    source = "fixture"

    def collect(self, device: Device) -> PollSnapshot:
        observed_at = datetime.now(timezone.utc)
        poll_id = uuid4()

        def refreshed(observation):
            return observation.model_copy(update={"observed_at": observed_at, "received_at": observed_at, "poll_id": poll_id})

        observations = [
            InterfaceObservation(
                interface_id=interface.id,
                interface_name=interface.name,
                admin_up=refreshed(interface.admin_up),
                oper_up=refreshed(interface.oper_up),
                speed_mbps=refreshed(interface.speed_mbps),
                access_vlan=refreshed(interface.access_vlan) if interface.access_vlan else None,
            )
            for interface in device.interfaces
            if interface.kind == "ethernet"
        ]
        return PollSnapshot(
            poll_id=poll_id,
            device_id=device.id,
            observed_at=observed_at,
            source="fixture",
            quality=ReadQuality.OK,
            observations=observations,
        )
