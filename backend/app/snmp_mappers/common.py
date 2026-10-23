"""Small validation helpers shared by numeric-OID mappers."""
from __future__ import annotations

import re
from typing import Any, Iterable

from ..snmp_transport import OID, numeric_oid
from ..ssh import ConnectionPolicyError


def text_value(value: Any, *, maximum: int = 512) -> str:
    if hasattr(value, "asOctets"):
        raw = value.asOctets().decode("utf-8", errors="replace")
    else:
        raw = str(value)
    # Control characters and terminal escapes are not evidence fields.
    cleaned = " ".join(re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", raw).split())
    return cleaned[:maximum]


def int_value(value: Any) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ConnectionPolicyError("snmp_value_invalid") from error
    if result < 0:
        raise ConnectionPolicyError("snmp_value_invalid")
    return result


def scalar_map(bindings: Iterable[tuple[OID, Any]]) -> dict[str, Any]:
    return {".".join(str(part) for part in oid): value for oid, value in bindings}


def column_map(bindings: Iterable[tuple[OID, Any]], prefix: str) -> dict[tuple[int, ...], Any]:
    root = numeric_oid(prefix)
    values: dict[tuple[int, ...], Any] = {}
    for oid, value in bindings:
        current = numeric_oid(oid)
        suffix = current[len(root):]
        if current[:len(root)] != root or not suffix:
            raise ConnectionPolicyError("snmp_malformed_oid")
        if suffix in values:
            raise ConnectionPolicyError("snmp_duplicate_oid")
        values[suffix] = value
    return values

