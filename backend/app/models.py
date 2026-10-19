"""Domain models shared by the API, workers and device drivers.

The first slice keeps persistence behind repositories so the demo can run
without a database. These Pydantic models are the contract that a PostgreSQL
repository will persist in the next slice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReadQuality(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    UNKNOWN = "unknown"


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any | None
    observed_at: datetime | None
    received_at: datetime = Field(default_factory=utc_now)
    stale_after_seconds: int = Field(ge=1)
    source: Literal["snmp", "ssh", "netconf", "manual", "fixture"]
    quality: ReadQuality
    poll_id: UUID = Field(default_factory=uuid4)

    @property
    def freshness(self) -> Literal["fresh", "stale", "unknown"]:
        if self.observed_at is None:
            return "unknown"
        age = (utc_now() - self.observed_at).total_seconds()
        return "fresh" if age <= self.stale_after_seconds else "stale"


class PhysicalComponent(BaseModel):
    id: str
    kind: Literal["chassis", "stack_member", "module", "psu", "fan", "transceiver"]
    label: str
    serial: str | None = None
    slot: str | None = None


class PhysicalPort(BaseModel):
    id: str
    component_id: str
    label: str
    connector: Literal["rj45", "sfp", "qsfp", "management", "console", "unknown"]
    group: str
    ordinal: int
    verified_layout: bool = False
    parent_port_id: str | None = None
    description: str | None = None


class Interface(BaseModel):
    id: str
    name: str
    kind: Literal["ethernet", "svi", "loopback", "port_channel", "subinterface", "management"]
    if_index: int | None = None
    admin_up: Observation
    oper_up: Observation
    speed_mbps: Observation
    access_vlan: Observation | None = None


class PortBinding(BaseModel):
    id: str
    physical_port_id: str
    interface_id: str
    binding_quality: Literal["explicit", "inferred", "conflict"]


class Device(BaseModel):
    id: str
    name: str
    management_address: str
    site: str
    vendor: str
    platform: str
    model: str
    os_version: str
    serial: str
    read_only: bool = True
    support_status: Literal["demo_fixture", "generic_readonly", "lab_validated"]
    components: list[PhysicalComponent]
    physical_ports: list[PhysicalPort]
    interfaces: list[Interface]
    bindings: list[PortBinding]


class Job(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: Literal["connection_test", "inventory_read"]
    device_id: str
    status: Literal["queued", "running", "succeeded", "failed", "unknown"] = "queued"
    requested_by: str
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    priority: int = 100
    next_run_at: datetime = Field(default_factory=utc_now)
    attempt: int = 0
    max_attempts: int = Field(default=3, ge=1)
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    idempotency_key: str | None = None
    payload_ref: str | None = None
    result_code: str | None = None


class InterfaceObservation(BaseModel):
    interface_id: str
    interface_name: str
    admin_up: Observation
    oper_up: Observation
    speed_mbps: Observation
    access_vlan: Observation | None = None


class PollSnapshot(BaseModel):
    poll_id: UUID = Field(default_factory=uuid4)
    device_id: str
    observed_at: datetime
    received_at: datetime = Field(default_factory=utc_now)
    source: Literal["snmp", "ssh", "netconf", "manual", "fixture"]
    quality: ReadQuality
    observations: list[InterfaceObservation]
    error: str | None = None


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: UUID = Field(default_factory=uuid4)
