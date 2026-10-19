"""Validated management contracts. Missing measurements are never defaults of zero."""
from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import ip_address, ip_interface
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from .models import Device, Interface, PhysicalComponent, PhysicalPort, PortBinding


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Credentials(StrictModel):
    username: str = Field(min_length=1, max_length=128, pattern=r"^[^\s\x00-\x1f]+$")
    method: Literal["password", "private_key"] = "password"
    password: SecretStr | None = None
    private_key: SecretStr | None = None
    passphrase: SecretStr | None = None

    @model_validator(mode="after")
    def bound_secrets(self):
        for value in (self.password, self.private_key, self.passphrase):
            if value and len(value.get_secret_value()) > 32768:
                raise ValueError("secret_too_large")
        return self


Collector = Literal["external", "linux_ssh", "huawei_vrp"]
SSHProfile = Literal["standard", "huawei_legacy"]


class ConnectionSettings(StrictModel):
    collector: Collector = "external"
    ssh_profile: SSHProfile = "standard"
    legacy_ssh_confirmed: bool = False


class DeviceCreate(ConnectionSettings):
    name: str = Field(min_length=1, max_length=160)
    management_address: str = Field(max_length=255)
    site: str = Field(min_length=1, max_length=160)
    device_type: Literal["switch", "router", "firewall", "server", "other"] = "switch"
    vendor: str = Field(default="", max_length=120)
    model: str = Field(default="", max_length=160)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    credentials: Credentials | None = None

    @field_validator("management_address")
    @classmethod
    def valid_address(cls, value):
        # Inventory stores an IP, not a URL/hostname which can change after approval.
        address = ip_address(value)
        address = getattr(address, "ipv4_mapped", None) or address
        if address.is_unspecified or address.is_multicast or address.is_link_local or "%" in value:
            raise ValueError("invalid_management_address")
        return str(address)


class ManagedDevice(Device):
    device_type: Literal["switch", "router", "firewall", "server", "other"] = "switch"
    ssh_port: int = 22
    collector: Collector = "external"
    ssh_profile: SSHProfile = "standard"
    credential_configured: bool = False
    host_key_fingerprint: str | None = None
    inventory_observed_at: datetime | None = None
    inventory_source: str | None = None


class Inventory(StrictModel):
    components: list[PhysicalComponent] = Field(default_factory=list, max_length=256)
    physical_ports: list[PhysicalPort] = Field(default_factory=list, max_length=4096)
    interfaces: list[Interface] = Field(default_factory=list, max_length=8192)
    bindings: list[PortBinding] = Field(default_factory=list, max_length=8192)
    os_version: str = Field(default="", max_length=160)
    serial: str = Field(default="", max_length=160)
    source: Literal["ssh", "snmp", "netconf", "manual"] = "manual"
    observed_at: datetime

    @model_validator(mode="after")
    def references(self):
        ports = {p.id for p in self.physical_ports}
        interfaces = {i.id for i in self.interfaces}
        components = {c.id for c in self.components}
        if len(ports) != len(self.physical_ports) or len(interfaces) != len(self.interfaces):
            raise ValueError("duplicate_inventory_id")
        for port in self.physical_ports:
            if port.component_id not in components or (port.parent_port_id and port.parent_port_id not in ports):
                raise ValueError("invalid_port_reference")
            if port.parent_port_id and next(p for p in self.physical_ports if p.id == port.parent_port_id).parent_port_id:
                raise ValueError("nested_breakout_not_supported")
        for binding in self.bindings:
            if binding.physical_port_id not in ports or binding.interface_id not in interfaces:
                raise ValueError("invalid_binding")
        if any(o.source == "fixture" for i in self.interfaces for o in (i.admin_up, i.oper_up, i.speed_mbps)):
            raise ValueError("fixture_not_allowed")
        validate_time(self.observed_at)
        return self


def validate_time(value: datetime):
    if value.tzinfo is None or (value - datetime.now(timezone.utc)).total_seconds() > 30:
        raise ValueError("invalid_observation_time")
    return value


class InterfaceSample(StrictModel):
    interface_id: str = Field(max_length=160)
    admin_up: bool | None = None
    oper_up: bool | None = None
    capacity_bps: float | None = Field(default=None, gt=0)
    rx_bps: float | None = Field(default=None, ge=0)
    tx_bps: float | None = Field(default=None, ge=0)
    rate_interval_seconds: int | None = Field(default=None, ge=1, le=86400)
    in_octets: int | None = Field(default=None, ge=0, le=2**64 - 1)
    out_octets: int | None = Field(default=None, ge=0, le=2**64 - 1)
    discontinuity: str | None = Field(default=None, max_length=160)
    counter_epoch_known: bool = True
    quality: Literal["ok", "partial", "unknown", "unsupported", "error"] = "ok"
    duplex: Literal["full", "half", "unknown"] = "unknown"
    errors: int | None = Field(default=None, ge=0)
    discards: int | None = Field(default=None, ge=0)
    tx_errors: int | None = Field(default=None, ge=0)
    tx_discards: int | None = Field(default=None, ge=0)
    access_vlan: int | None = Field(default=None, ge=1, le=4094)
    pvid: int | None = Field(default=None, ge=1, le=4094)
    vlan_mode: Literal["access", "trunk", "unknown"] = "unknown"
    poe_watts: float | None = Field(default=None, ge=0)
    transceiver_present: bool | None = None
    transceiver_model: str | None = Field(default=None, max_length=160)
    addresses: list[str] = Field(default_factory=list, max_length=128)
    vrf: str | None = Field(default=None, max_length=160)
    vrf_known: bool = True

    @field_validator("addresses")
    @classmethod
    def valid_addresses(cls, values):
        return [str(ip_interface(value)) for value in values]


class Health(StrictModel):
    status: Literal["ok", "warning", "critical", "unknown", "unsupported"] = "unknown"
    # A collector must explain its evaluation; no invented thresholds/scores.
    evaluation: str | None = Field(default=None, max_length=400)
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    memory_percent: float | None = Field(default=None, ge=0, le=100)
    temperature_c: float | None = Field(default=None, ge=-100, le=250)
    uptime_seconds: int | None = Field(default=None, ge=0)
    fan: str | None = Field(default=None, max_length=160)
    power_supply: str | None = Field(default=None, max_length=160)
    poe_watts: float | None = Field(default=None, ge=0)
    alerts: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def evaluation_required(self):
        if self.status in {"ok", "warning", "critical"} and not self.evaluation:
            raise ValueError("health_evaluation_required")
        if any(len(a) > 500 for a in self.alerts):
            raise ValueError("alert_too_long")
        return self


class Neighbor(StrictModel):
    id: str = Field(max_length=160)
    interface_id: str = Field(max_length=160)
    label: str = Field(max_length=160)
    relation: Literal["physical", "l2"]
    evidence: str = Field(min_length=1, max_length=300)
    # Explicit collector references only; labels and ARP addresses are not cables.
    remote_device_id: str | None = Field(default=None, min_length=1, max_length=64)
    remote_interface_id: str | None = Field(default=None, min_length=1, max_length=160)


class EndpointObservation(StrictModel):
    id: str = Field(min_length=1, max_length=160)
    interface_id: str = Field(min_length=1, max_length=160)
    mac: str = Field(pattern=r"^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
    addresses: list[str] = Field(default_factory=list, max_length=32)
    vlan: int | None = Field(default=None, ge=1, le=4094)
    discovery: Literal["fdb", "arp", "ndp"]
    state: Literal["reachable", "stale", "static", "unknown"] = "unknown"
    evidence: str = Field(min_length=1, max_length=300)

    @field_validator("mac")
    @classmethod
    def unicast_mac(cls, value):
        if int(value[:2], 16) & 1 or value.lower() == "00:00:00:00:00:00":
            raise ValueError("invalid_endpoint_mac")
        return value.lower()

    @field_validator("addresses")
    @classmethod
    def endpoint_addresses(cls, values):
        addresses = [ip_address(value) for value in values]
        if any(a.is_multicast or a.is_unspecified or a.is_loopback for a in addresses):
            raise ValueError("invalid_endpoint_address")
        return sorted({str(a) for a in addresses})


class EndpointCollection(StrictModel):
    status: Literal["ok", "partial", "unknown", "unsupported", "error"] = "unknown"
    entries: list[EndpointObservation] = Field(default_factory=list, max_length=2048)

    @model_validator(mode="after")
    def valid_entries(self):
        if self.entries and self.status not in {"ok", "partial"}:
            raise ValueError("endpoint_status_conflict")
        if len({e.id for e in self.entries}) != len(self.entries):
            raise ValueError("duplicate_endpoint_id")
        return self


class Telemetry(StrictModel):
    observed_at: datetime
    source: Literal["ssh", "snmp", "netconf", "manual"]
    stale_after_seconds: int = Field(default=120, ge=10, le=86400)
    reachability: Literal["reachable", "unreachable", "unknown"] = "unknown"
    error: str | None = Field(default=None, max_length=160)
    interfaces: list[InterfaceSample] = Field(default_factory=list, max_length=8192)
    health: Health = Field(default_factory=Health)
    neighbors: list[Neighbor] = Field(default_factory=list, max_length=1024)
    endpoints: EndpointCollection = Field(default_factory=EndpointCollection)

    @model_validator(mode="after")
    def valid(self):
        validate_time(self.observed_at)
        ids = [i.interface_id for i in self.interfaces]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_interface_sample")
        if len({n.id for n in self.neighbors}) != len(self.neighbors):
            raise ValueError("duplicate_neighbor_id")
        return self
