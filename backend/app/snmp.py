"""SNMPv3 authPriv only, registered IPs, bounded IF-MIB numeric OIDs."""
import asyncio
from uuid import uuid4

from pysnmp.hlapi.v3arch import asyncio as snmp
from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject
import sqlalchemy as sa

from .collection import ReadResult, metadata
from .contracts import InterfaceSample
from . import cisco, huawei
from .ssh import ConnectionPolicyError, target_allowed

SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
IF = "1.3.6.1.2.1.2.2.1."
IFX = "1.3.6.1.2.1.31.1.1.1."
COLUMNS = {
    "name": IFX + "1", "admin_up": IF + "7", "oper_up": IF + "8",
    "capacity": IFX + "15", "in_octets": IFX + "6", "out_octets": IFX + "10",
    "in32": IF + "10", "out32": IF + "16", "errors": IF + "14",
    "discards": IF + "13", "tx_errors": IF + "20", "tx_discards": IF + "19",
    "discontinuity": IFX + "19",
}


def parse_if_mib(device, columns, uptime, previous=None):
    previous = previous or {}
    epoch = previous.get("snmp_epoch") or str(uuid4())
    if uptime < previous.get("snmp_uptime_ticks", 0):
        epoch = str(uuid4())
    canonical = huawei.canonical if (device.resolved_collector or device.collector) == "huawei_vrp" else cisco.canonical
    names = {canonical(i.name): i for i in device.interfaces}
    seen, samples = set(), []
    for index, name in columns.get("name", {}).items():
        interface = names.get(canonical(str(name)))
        if not interface:
            continue  # ifIndex is never used as the persistent identity.
        if interface.id in seen:
            raise ConnectionPolicyError("snmp_ambiguous_interface")
        seen.add(interface.id)
        def value(key):
            result = columns.get(key, {}).get(index)
            return int(result) if result is not None else None
        incoming, outgoing = value("in_octets"), value("out_octets")
        bits = 64
        if incoming is None or outgoing is None:
            incoming, outgoing, bits = value("in32"), value("out32"), 32
        disc = value("discontinuity")
        capacity = value("capacity")
        samples.append(InterfaceSample(interface_id=interface.id,
            admin_up={1: True, 2: False, 3: False}.get(value("admin_up")),
            oper_up={1: True, 2: False, 3: False, 4: False, 5: False, 6: False, 7: False}.get(value("oper_up")),
            capacity_bps=capacity * 1_000_000 if capacity else None,
            in_octets=incoming, out_octets=outgoing, counter_bits=bits, source="snmp", vrf_known=False,
            discontinuity=f"{epoch}:{index}:{disc}", counter_epoch_known=disc is not None,
            errors=value("errors"), discards=value("discards"), tx_errors=value("tx_errors"), tx_discards=value("tx_discards")))
    if not samples:
        raise ConnectionPolicyError("snmp_interface_identity_missing")
    complete = {i.id for i in device.interfaces if i.kind == "ethernet"}.issubset(seen)
    return {"interfaces": [s.model_dump(mode="json") for s in samples],
            "snmp_epoch": epoch, "snmp_uptime_ticks": uptime}, complete


async def collect_snmp(store, vault, device, authorize=lambda: None):
    authorize()
    target_allowed(store, device)
    credentials = vault.get_protocol(device.id, "snmp")
    engine = snmp.SnmpEngine()
    try:
        user = snmp.UsmUserData(credentials["username"], credentials["auth_password"], credentials["privacy_password"],
            authProtocol=snmp.USM_AUTH_HMAC192_SHA256 if credentials["auth_protocol"] == "sha256" else snmp.USM_AUTH_HMAC96_SHA,
            privProtocol=snmp.USM_PRIV_CFB128_AES)
        transport_cls = snmp.Udp6TransportTarget if ":" in device.management_address else snmp.UdpTransportTarget
        target = await transport_cls.create((device.management_address, credentials["port"]), timeout=2, retries=0)
        context = snmp.ContextData(contextName=credentials.get("context", ""))
        requests = 0

        async def request(oid, bulk=False):
            nonlocal requests
            authorize()
            target_allowed(store, device)
            requests += 1
            if requests > 128:
                raise ConnectionPolicyError("snmp_request_limit")
            obj = snmp.ObjectType(snmp.ObjectIdentity(tuple(int(n) for n in oid.split("."))))
            args = (engine, user, target, context)
            result = await (snmp.bulk_cmd(*args, 0, 40, obj, lookupMib=False) if bulk else snmp.get_cmd(*args, obj, lookupMib=False))
            indication, status, _, bindings = result
            if indication or status:
                # Error text may contain usernames/engine details; never expose it.
                auth_errors = {"authenticationFailure", "unknownUserName", "wrongDigest", "decryptionError",
                               "unsupportedSecurityLevel", "authorizationError"}
                name = getattr(indication, "__class__", type(None)).__name__
                error = "snmp_authentication_failed" if name[0:1].lower() + name[1:] in auth_errors or int(status or 0) == 16 else "snmp_read_failed"
                raise ConnectionPolicyError(error)
            return bindings

        async with asyncio.timeout(25):
            uptime_bindings = await request(SYS_UPTIME)
            uptime = int(uptime_bindings[0][1])
            columns = {}
            for name, prefix in COLUMNS.items():
                values, cursor = {}, prefix
                while True:
                    bindings = await request(cursor, True)
                    done = False
                    for oid, value in bindings:
                        key = ".".join(str(n) for n in oid)
                        if isinstance(value, (EndOfMibView, NoSuchInstance, NoSuchObject)) or not key.startswith(prefix + "."):
                            done = True
                            break
                        if tuple(oid) <= tuple(int(n) for n in cursor.split(".")):
                            raise ConnectionPolicyError("snmp_non_increasing_oid")
                        index = int(key[len(prefix) + 1:])
                        values[index] = str(value) if name == "name" else int(value)
                        cursor = key
                        if len(values) > 4096:
                            raise ConnectionPolicyError("snmp_output_limit")
                    if done or not bindings:
                        break
                columns[name] = values
        with store.engine.connect() as conn:
            previous = conn.execute(sa.select(store.collection_groups.c.payload).where(
                store.collection_groups.c.device_id == device.id, store.collection_groups.c.group_name == "fast")).scalar_one_or_none()
        payload, complete = parse_if_mib(device, columns, uptime, previous)
        return ReadResult(device, payloads={"fast": payload}, reboot_detected=bool(previous and
            previous.get("snmp_epoch") and previous["snmp_epoch"] != payload["snmp_epoch"]),
            metadata={"fast": metadata("fast", "snmp_if_mib",
            source="snmp", quality="ok" if complete else "partial", complete=complete,
            reason=None if complete else "snmp_missing_interfaces")})
    finally:
        credentials.clear()
        engine.close_dispatcher()
