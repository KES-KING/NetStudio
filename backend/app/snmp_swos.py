"""Strict SwOS identity and logical-interface mapping from standard MIB data."""
from __future__ import annotations

from hashlib import sha256
import re

from .database import now
from .models import Interface, Observation
from .snmp_mappers.common import text_value
from .ssh import ConnectionPolicyError


SWOS_IDENTITY = re.compile(
    r"\bMikroTik\s+(?P<model>CSS[0-9A-Za-z+._-]+)\s+SwOS\s+(?P<version>[0-9][0-9A-Za-z._-]*)\b",
    re.I,
)


def identity(sys_descr: str | None) -> dict[str, str]:
    match = SWOS_IDENTITY.search(sys_descr or "")
    if not match:
        raise ConnectionPolicyError("snmp_swos_identity_mismatch")
    return {
        "vendor": "MikroTik",
        "model": match.group("model")[:160],
        "version": match.group("version")[:160],
    }


def interfaces(device, names: dict[int, object]):
    """Create stable logical identities; never infer chassis port geometry."""
    if not names or len(names) > 4096:
        raise ConnectionPolicyError("snmp_interface_identity_missing")
    at = now()
    unknown = lambda: Observation(
        value=None, observed_at=at, source="snmp", quality="unknown",
        stale_after_seconds=120,
    )
    existing = {item.name.casefold(): item for item in device.interfaces}
    mapped, seen = [], set()
    for raw_index, raw_name in sorted(names.items()):
        try:
            index = int(raw_index)
        except (TypeError, ValueError, OverflowError) as error:
            raise ConnectionPolicyError("snmp_malformed_oid") from error
        name = text_value(raw_name, maximum=160)
        canonical = name.casefold()
        if not name or canonical in seen:
            raise ConnectionPolicyError("snmp_ambiguous_interface")
        seen.add(canonical)
        previous = existing.get(canonical)
        if previous and previous.if_index not in {None, index}:
            raise ConnectionPolicyError("snmp_ambiguous_ifindex")
        identifier = previous.id if previous else (
            f"{device.id}:mikrotik_swos:if:"
            f"{sha256(canonical.encode()).hexdigest()[:20]}"
        )
        kind = "svi" if re.match(r"^(?:bridge|vlan)\d*$", canonical) else "ethernet"
        mapped.append(Interface(
            id=identifier, name=name, kind=kind, if_index=index,
            admin_up=previous.admin_up if previous else unknown(),
            oper_up=previous.oper_up if previous else unknown(),
            speed_mbps=previous.speed_mbps if previous else unknown(),
        ))
    return device.model_copy(update={
        "interfaces": mapped,
        "inventory_source": "snmp",
        "inventory_observed_at": at,
    })
