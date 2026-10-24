"""Installation and device policy for the narrowly scoped SNMPv2c exception."""
from __future__ import annotations

import os

from .ssh import ConnectionPolicyError


SNMP_V2C_PROFILE = "mikrotik_swos"


def snmp_v2c_enabled(value: str | None = None) -> bool:
    """Require an exact affirmative value; malformed values fail closed."""
    configured = os.getenv("NETSTUDIO_ALLOW_SNMP_V2C", "0") if value is None else value
    return configured == "1"


def device_profile_id(device) -> str | None:
    return device.resolved_profile_id or device.configured_profile_id


def require_snmp_v2c_device(device) -> None:
    if not snmp_v2c_enabled():
        raise ConnectionPolicyError("snmp_v2c_installation_disabled")
    if device_profile_id(device) != SNMP_V2C_PROFILE or device.collector != SNMP_V2C_PROFILE:
        raise ConnectionPolicyError("snmp_v2c_profile_not_allowed")


def require_snmp_v2c_runtime(device) -> None:
    require_snmp_v2c_device(device)
    if not device.snmp_v2c_risk_accepted:
        raise ConnectionPolicyError("snmp_v2c_device_approval_required")


def require_snmp_v3_device(device) -> None:
    if device_profile_id(device) == SNMP_V2C_PROFILE or device.collector == SNMP_V2C_PROFILE:
        raise ConnectionPolicyError("snmp_v3_not_supported_by_profile")
