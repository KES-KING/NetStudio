"""Bounded numeric-OID SNMPv3 authPriv transport.

MIB mapping is intentionally absent here.  The reader owns all request, row,
varbind, byte and deadline limits so individual vendor/standard mappers cannot
accidentally weaken them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Protocol

from pysnmp.hlapi.v3arch import asyncio as snmp
from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject

from .ssh import ConnectionPolicyError, target_allowed
from .transport import TransportContext


OID = tuple[int, ...]
Operation = Literal["get", "getnext", "getbulk"]
MISSING = (EndOfMibView, NoSuchInstance, NoSuchObject)


def numeric_oid(value: str | Iterable[int] | Any) -> OID:
    """Parse an audited numeric OID and reject names, signs and empty arcs."""
    if isinstance(value, str):
        raw = value[1:] if value.startswith(".") else value
        parts = raw.split(".")
        if not raw or any(not part.isascii() or not part.isdigit() for part in parts):
            raise ConnectionPolicyError("snmp_malformed_oid")
        parsed = tuple(int(part) for part in parts)
    else:
        try:
            parsed = tuple(int(part) for part in value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ConnectionPolicyError("snmp_malformed_oid") from error
    if len(parsed) < 2 or parsed[0] not in {0, 1, 2} or parsed[1] > (39 if parsed[0] < 2 else 2**32 - 1):
        raise ConnectionPolicyError("snmp_malformed_oid")
    if any(part < 0 or part > 2**32 - 1 for part in parsed):
        raise ConnectionPolicyError("snmp_malformed_oid")
    return parsed


def oid_text(value: OID) -> str:
    return ".".join(str(part) for part in value)


@dataclass(frozen=True)
class SNMPLimits:
    requests: int = 128
    rows: int = 4096
    varbinds: int = 16384
    bytes: int = 2_000_000
    bulk_repetitions: int = 40
    response_seconds: float = 2

    def __post_init__(self):
        if min(self.requests, self.rows, self.varbinds, self.bytes, self.bulk_repetitions) <= 0 or self.response_seconds <= 0:
            raise ValueError("snmp_limits_invalid")


class SNMPSession(Protocol):
    async def request(self, operation: Operation, oids: tuple[OID, ...], *, max_repetitions: int) -> list[tuple[Any, Any]]: ...
    def close(self) -> None: ...


_AUTH_ERRORS = {
    "authenticationfailure", "unknownusername", "wrongdigest", "decryptionerror",
    "unsupportedsecuritylevel", "authorizationerror", "notintimewindow",
}
_CONTEXT_ERRORS = {"nosuchcontext", "unknowncontext"}


def safe_response_error(indication, status) -> str | None:
    """Map agent details to a finite public code; never return raw text."""
    if not indication and not status:
        return None
    names = {
        getattr(indication, "__class__", type(None)).__name__.casefold(),
        getattr(status, "__class__", type(None)).__name__.casefold(),
    }
    status_code = 0
    try:
        status_code = int(status or 0)
    except (TypeError, ValueError):
        pass
    if names & _CONTEXT_ERRORS:
        return "snmp_context_mismatch"
    if names & _AUTH_ERRORS or status_code in {6, 16}:
        return "snmp_authentication_failed"
    return "snmp_read_failed"


class PysnmpV3Session:
    """pysnmp binding restricted to v3 authPriv and AES-128 privacy."""

    def __init__(self, context: TransportContext, credentials: dict):
        target_allowed(context.store, context.device)
        self.context = context
        self.credentials = credentials
        self.engine = snmp.SnmpEngine()
        self.user = snmp.UsmUserData(
            credentials["username"], credentials["auth_password"], credentials["privacy_password"],
            authProtocol=(snmp.USM_AUTH_HMAC192_SHA256 if credentials["auth_protocol"] == "sha256"
                          else snmp.USM_AUTH_HMAC96_SHA),
            privProtocol=snmp.USM_PRIV_CFB128_AES,
        )
        self.context_data = snmp.ContextData(contextName=credentials.get("context", ""))
        self.context_name = credentials.get("context", "")
        self.target = None

    async def open(self):
        device = self.context.device
        transport_cls = snmp.Udp6TransportTarget if ":" in device.management_address else snmp.UdpTransportTarget
        self.target = await self.context.wait(
            transport_cls.create((device.management_address, self.credentials["port"]), timeout=2, retries=0),
            timeout_seconds=2,
        )
        return self

    async def request(self, operation: Operation, oids: tuple[OID, ...], *, max_repetitions: int):
        if self.target is None:
            raise RuntimeError("snmp_session_not_open")
        objects = tuple(snmp.ObjectType(snmp.ObjectIdentity(value)) for value in oids)
        args = (self.engine, self.user, self.target, self.context_data)
        if operation == "get":
            result = await snmp.get_cmd(*args, *objects, lookupMib=False)
        elif operation == "getnext":
            result = await snmp.next_cmd(*args, *objects, lookupMib=False)
        else:
            result = await snmp.bulk_cmd(*args, 0, max_repetitions, *objects, lookupMib=False)
        indication, status, _, bindings = result
        if code := safe_response_error(indication, status):
            raise ConnectionPolicyError(code)
        return list(bindings)

    def close(self):
        self.credentials.clear()
        self.engine.close_dispatcher()


class BoundedSNMPReader:
    def __init__(self, context: TransportContext, session: SNMPSession, allowed_roots: Iterable[str | OID],
                 limits: SNMPLimits = SNMPLimits()):
        self.context, self.session, self.limits = context, session, limits
        self.allowed_roots = tuple(numeric_oid(root) for root in allowed_roots)
        self.requests = self.rows = self.varbinds = self.bytes = 0

    def _allowed(self, value: OID) -> bool:
        return any(value[:len(root)] == root for root in self.allowed_roots)

    async def _request(self, operation: Operation, values: Iterable[str | OID]):
        oids = tuple(numeric_oid(value) for value in values)
        if not oids or any(not self._allowed(value) for value in oids):
            raise ConnectionPolicyError("snmp_oid_not_allowed")
        self.context.checkpoint()
        self.requests += 1
        if self.requests > self.limits.requests:
            raise ConnectionPolicyError("snmp_request_limit")
        try:
            bindings = await self.context.wait(
                self.session.request(operation, oids, max_repetitions=self.limits.bulk_repetitions),
                timeout_seconds=self.limits.response_seconds,
            )
        except ConnectionPolicyError as error:
            if str(error) in {"transport_timeout", "transport_deadline_exceeded"}:
                # A valid USM exchange against a configured non-default context
                # may be silently dropped by agents instead of returning a
                # noSuchContext report. Keep this typed and redacted.
                code = "snmp_context_mismatch" if getattr(self.session, "context_name", "") else "snmp_timeout"
                raise ConnectionPolicyError(code) from error
            raise
        self.varbinds += len(bindings)
        if self.varbinds > self.limits.varbinds:
            raise ConnectionPolicyError("snmp_varbind_limit")
        normalized = []
        for raw_oid, value in bindings:
            current = numeric_oid(raw_oid)
            self.bytes += len(oid_text(current).encode()) + len(str(value).encode(errors="replace"))
            if self.bytes > self.limits.bytes:
                raise ConnectionPolicyError("snmp_byte_limit")
            normalized.append((current, value))
        return normalized

    async def get(self, *oids: str | OID):
        return await self._request("get", oids)

    async def get_next(self, oid: str | OID):
        return await self._request("getnext", (oid,))

    async def walk(self, prefix: str | OID, *, bulk: bool = True) -> list[tuple[OID, Any]]:
        root = numeric_oid(prefix)
        if not self._allowed(root):
            raise ConnectionPolicyError("snmp_oid_not_allowed")
        cursor, values = root, []
        while True:
            bindings = await self._request("getbulk" if bulk else "getnext", (cursor,))
            if not bindings:
                break
            done = False
            for current, value in bindings:
                if isinstance(value, MISSING) or current[:len(root)] != root:
                    done = True
                    break
                if current <= cursor:
                    raise ConnectionPolicyError("snmp_non_increasing_oid")
                cursor = current
                values.append((current, value))
                self.rows += 1
                if self.rows > self.limits.rows:
                    raise ConnectionPolicyError("snmp_output_limit")
            if done:
                break
        return values

