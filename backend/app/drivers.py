"""Device driver boundary.

No driver method in this first slice opens a network socket. The fixture driver
is intentionally explicit so it cannot be confused with real Cisco support.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import Device, Job


class UnsupportedCapability(RuntimeError):
    """Raised instead of returning a fake successful result."""

    code = "unsupported_capability"


class DeviceDriver(Protocol):
    def discover_identity(self, session: object) -> dict: ...
    def discover_capabilities(self, session: object) -> dict: ...
    def read_inventory(self, session: object) -> Device: ...
    def read_interfaces(self, session: object) -> Device: ...
    def read_neighbors(self, session: object) -> list[dict]: ...
    def read_config(self, session: object, kind: str) -> dict: ...
    def build_plan(self, intent: object, baseline: object) -> object: ...
    def precheck(self, session: object, plan: object) -> object: ...
    def apply(self, session: object, plan: object) -> object: ...
    def verify(self, session: object, plan: object) -> object: ...
    def persist(self, session: object, plan: object) -> object: ...
    def rollback(self, session: object, plan: object) -> object: ...


class GenericReadOnlyDriver:
    """A driver which can expose inventory but cannot mutate a device."""

    driver_id = "generic_readonly"
    driver_version = "0.1.0"

    def __init__(self, device: Device):
        self.device = device

    def discover_identity(self, session: object) -> dict:
        return {
            "vendor": self.device.vendor,
            "platform": self.device.platform,
            "model": self.device.model,
            "serial": self.device.serial,
            "support_status": self.device.support_status,
        }

    def discover_capabilities(self, session: object) -> dict:
        return {
            "interfaces.read": {"support": "supported", "validation": "generic", "effective_allowed": True},
            "interface.description.set": {
                "support": "unknown",
                "validation": "not_tested",
                "effective_allowed": False,
                "denied_reason": "device_read_only",
            },
            "interface.access_vlan.set": {
                "support": "unsupported",
                "validation": "not_applicable",
                "effective_allowed": False,
                "denied_reason": "demo_fixture",
            },
        }

    def read_inventory(self, session: object) -> Device:
        return self.device

    def read_interfaces(self, session: object) -> Device:
        return self.device

    def read_neighbors(self, session: object) -> list[dict]:
        return []

    def read_config(self, session: object, kind: str) -> dict:
        raise UnsupportedCapability(f"config.read.{kind}")

    def build_plan(self, intent: object, baseline: object) -> object:
        raise UnsupportedCapability("config.plan")

    def precheck(self, session: object, plan: object) -> object:
        raise UnsupportedCapability("config.precheck")

    def apply(self, session: object, plan: object) -> object:
        raise UnsupportedCapability("config.apply")

    def verify(self, session: object, plan: object) -> object:
        raise UnsupportedCapability("config.verify")

    def persist(self, session: object, plan: object) -> object:
        raise UnsupportedCapability("config.persist")

    def rollback(self, session: object, plan: object) -> object:
        raise UnsupportedCapability("config.rollback")


@dataclass(frozen=True)
class FixtureDriver:
    """Deterministic local adapter used by tests and the demo profile."""

    device: Device
    driver_id: str = "fixture"
    driver_version: str = "0.1.0"

    def connection_test(self) -> dict:
        return {
            "reachable": False,
            "transport": "fixture",
            "message": "Demo profili gerçek ağ bağlantısı açmaz.",
            "driver_id": self.driver_id,
        }

    def run(self, job: Job) -> Job:
        return job.model_copy(update={"status": "succeeded", "result": self.connection_test(), "result_code": "fixture_unreachable"})
