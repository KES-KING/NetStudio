"""SNMPv2-MIB system identity mapper using audited numeric OIDs."""
from __future__ import annotations

from pydantic import Field, field_validator
from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject

from ..contracts import StrictModel
from ..snmp_transport import numeric_oid
from ..ssh import ConnectionPolicyError
from .common import int_value, scalar_map, text_value


SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
SYSTEM_SCALARS = (SYS_OBJECT_ID, SYS_DESCR, SYS_NAME, SYS_UPTIME)


class SystemIdentity(StrictModel):
    sys_object_id: str | None = None
    sys_descr: str | None = Field(default=None, max_length=512)
    sys_name: str | None = Field(default=None, max_length=255)
    sys_uptime_ticks: int = Field(ge=0, le=2**32 - 1)

    @field_validator("sys_object_id")
    @classmethod
    def valid_object_id(cls, value):
        if value is None:
            return value
        numeric_oid(value)
        return value.removeprefix(".")


def parse_system_mib(bindings) -> SystemIdentity:
    values = scalar_map(bindings)
    missing = (EndOfMibView, NoSuchInstance, NoSuchObject)
    if SYS_UPTIME not in values or isinstance(values[SYS_UPTIME], missing):
        raise ConnectionPolicyError("snmp_system_identity_missing")
    def optional(oid, *, maximum):
        value = values.get(oid)
        return None if value is None or isinstance(value, missing) else text_value(value, maximum=maximum)
    object_id = optional(SYS_OBJECT_ID, maximum=255)
    return SystemIdentity(
        sys_object_id=object_id.removeprefix(".") if object_id else None,
        sys_descr=optional(SYS_DESCR, maximum=512),
        sys_name=optional(SYS_NAME, maximum=255),
        sys_uptime_ticks=int_value(values[SYS_UPTIME]),
    )

