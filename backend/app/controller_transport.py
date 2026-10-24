"""Bounded read-only HTTPS collection for controller-managed switch profiles."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import ssl
from typing import Callable
from urllib.parse import parse_qsl, quote, urljoin, urlsplit, urlunsplit

import httpx
import sqlalchemy as sa

from .collection import ReadResult, metadata
from .contracts import Health, InterfaceSample, Telemetry
from .database import now
from .driver_catalog import SUPPORTED
from .models import Interface, Observation, PhysicalComponent, PhysicalPort, PortBinding
from .ssh import ConnectionPolicyError
from .transport import TransportContext


MAX_RESPONSE_BYTES = 2_000_000
MAX_PAGES = 20
MAX_ROWS = 8192
MAX_RETRY_AFTER = 30
MAX_RATE_RETRIES = 1

CLOUD_ORIGINS = {
    "global": "https://api.meraki.com",
    "canada": "https://api.meraki.ca",
    "india": "https://api.meraki.in",
    "china": "https://api.meraki.cn",
}
PROFILE_ID = {
    "meraki_dashboard": "cisco_meraki_ms",
    "fortinet_fortilink_api": "fortinet_fortiswitch_fortilink",
    "unifi_api": "ubiquiti_unifi_switch",
    "unifi_no_snmp_api": "ubiquiti_unifi_no_snmp",
    "tplink_omada_api": "tplink_omada_managed",
    "tplink_omada_pro_api": "tplink_omada_pro",
}
IDENTITY = {
    "meraki": ("Cisco Meraki", "Meraki MS", "cloud_managed"),
    "fortigate": ("Fortinet", "FortiSwitchOS", "controller_managed"),
    "unifi": ("Ubiquiti", "UniFi Switch", "controller_managed"),
    "omada": ("TP-Link", "Omada Managed", "controller_managed"),
    "omada_pro": ("TP-Link", "Omada Pro", "controller_managed"),
}
RUNTIME_VENDOR = {
    "meraki_dashboard": "meraki",
    "fortinet_fortilink_api": "fortigate",
    "unifi_api": "unifi",
    "unifi_no_snmp_api": "unifi",
    "tplink_omada_api": "omada",
    "tplink_omada_pro_api": "omada_pro",
}
REQUIRED_SCOPES = {
    "meraki": {
        "dashboard:general:config:read", "switch:config:read",
        "switch:telemetry:read",
    },
    "fortigate": {"switch-controller:read"},
    "unifi": {"site:read", "device:read"},
    "omada": {"site:read", "device:read"},
    "omada_pro": {"site:read", "device:read"},
}


def _runtime(device) -> str:
    return device.resolved_collector if device.collector == "auto" else device.collector


def _base_url(controller) -> str:
    if controller["vendor"] == "meraki":
        try:
            return CLOUD_ORIGINS[controller["cloud_region"] or "global"]
        except KeyError as error:
            raise ConnectionPolicyError("controller_cloud_region_invalid") from error
    address = controller["address"]
    if ":" in address:
        address = f"[{address}]"
    return f"https://{address}:{controller['port']}"


def _ssl_context(controller):
    context = ssl.create_default_context()
    if controller["ca_pem"]:
        try:
            context.load_verify_locations(cadata=controller["ca_pem"])
        except ssl.SSLError as error:
            raise ConnectionPolicyError("controller_ca_invalid") from error
    return context


def _paths(controller, binding):
    scope = quote(controller["external_scope_id"], safe="")
    site = quote(controller["external_site_id"], safe="")
    device = quote(binding["external_device_id"], safe="")
    vendor = controller["vendor"]
    if vendor == "meraki":
        return {
            "devices": f"/api/v1/organizations/{scope}/devices?networkIds[]={site}",
            "ports": f"/api/v1/devices/{device}/switch/ports",
            "status": f"/api/v1/devices/{device}/switch/ports/statuses?timespan=300",
        }
    if vendor == "unifi":
        prefix = f"/proxy/network/integration/v1/sites/{site}/devices"
        return {
            "devices": prefix,
            "details": f"{prefix}/{device}",
            "status": f"{prefix}/{device}/statistics/latest",
        }
    if vendor == "fortigate":
        return {"devices": f"/api/v2/monitor/switch-controller/managed-switch?switch-id={device}"}
    return {"devices": f"/openapi/v1/{scope}/sites/{site}/switches?deviceId={device}"}


def _next_url(base: str, initial_path: str, candidate: str) -> str:
    initial = urlsplit(base + initial_path)
    parsed = urlsplit(candidate if "://" in candidate else urljoin(urlunsplit(initial), candidate))
    if (parsed.scheme, parsed.netloc) != (initial.scheme, initial.netloc):
        raise ConnectionPolicyError("controller_pagination_origin_denied")
    if parsed.path != initial.path:
        raise ConnectionPolicyError("controller_pagination_path_denied")
    # Query values may advance cursors but cannot change the approved path.
    if len(parse_qsl(parsed.query, keep_blank_values=True)) > 32:
        raise ConnectionPolicyError("controller_pagination_query_limit")
    return urlunsplit(parsed)


def _link_next(value: str | None) -> str | None:
    if not value:
        return None
    for item in value.split(","):
        match = re.match(r'\s*<([^>]+)>\s*;\s*rel="?next"?', item, re.I)
        if match:
            return match.group(1)
    return None


class ControllerHTTPClient:
    def __init__(self, *, transport=None, sleeper: Callable = asyncio.sleep):
        self.transport = transport
        self.sleeper = sleeper

    async def _json(self, context, client, url, headers):
        retries = 0
        while True:
            context.checkpoint()
            try:
                request = client.build_request("GET", url, headers=headers)
                response = await context.wait(client.send(request, stream=True), timeout_seconds=15)
                try:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        raise ConnectionPolicyError("controller_redirect_denied")
                    if response.status_code == 401:
                        raise ConnectionPolicyError("controller_authentication_failed")
                    if response.status_code == 403:
                        raise ConnectionPolicyError("controller_scope_insufficient")
                    if response.status_code == 429:
                        try:
                            retry_after = int(response.headers.get("retry-after", "0"))
                        except ValueError:
                            retry_after = MAX_RETRY_AFTER + 1
                        if not 0 <= retry_after <= MAX_RETRY_AFTER:
                            raise ConnectionPolicyError("controller_retry_after_invalid")
                        if retries >= MAX_RATE_RETRIES:
                            raise ConnectionPolicyError("controller_rate_limited")
                        retries += 1
                        await context.wait(self.sleeper(retry_after), timeout_seconds=MAX_RETRY_AFTER + 1)
                        continue
                    if response.status_code < 200 or response.status_code >= 300:
                        raise ConnectionPolicyError("controller_http_failed")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise ConnectionPolicyError("controller_response_limit")
                    try:
                        value = json.loads(content)
                    except (json.JSONDecodeError, UnicodeDecodeError) as error:
                        raise ConnectionPolicyError("controller_response_invalid") from error
                    return value, response.headers
                finally:
                    await response.aclose()
            except ConnectionPolicyError:
                raise
            except (httpx.TimeoutException, asyncio.TimeoutError) as error:
                raise ConnectionPolicyError("controller_timeout") from error
            except (httpx.HTTPError, ssl.SSLError) as error:
                raise ConnectionPolicyError("controller_tls_or_connection_failed") from error

    async def pages(self, context, client, base, path, headers):
        url = base + path
        seen, values = set(), []
        for _ in range(MAX_PAGES):
            if url in seen:
                raise ConnectionPolicyError("controller_pagination_loop")
            seen.add(url)
            value, response_headers = await self._json(context, client, url, headers)
            values.append(value)
            candidate = _link_next(response_headers.get("link"))
            if isinstance(value, dict):
                candidate = candidate or value.get("next") or value.get("nextPage")
                if isinstance(candidate, dict):
                    candidate = candidate.get("href")
            if not candidate:
                return values
            if not isinstance(candidate, str) or len(candidate) > 2048:
                raise ConnectionPolicyError("controller_pagination_invalid")
            url = _next_url(base, path, candidate)
        raise ConnectionPolicyError("controller_pagination_limit")

    async def collect(self, context: TransportContext, controller, binding, secret, metadata):
        expires = metadata.get("expires_at")
        if expires:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                raise ConnectionPolicyError("controller_token_expired")
        if not REQUIRED_SCOPES[controller["vendor"]] <= set(metadata.get("scopes", ())):
            raise ConnectionPolicyError("controller_scope_insufficient")
        token = secret.get("token")
        if not isinstance(token, str) or not token:
            raise ConnectionPolicyError("controller_credentials_missing")
        headers = {"Accept": "application/json"}
        if metadata["auth_kind"] == "api_key":
            headers["X-API-Key"] = token
        elif metadata["auth_kind"] == "access_token":
            headers["Authorization"] = f"AccessToken={token}"
        else:
            headers["Authorization"] = f"Bearer {token}"
        base, paths = _base_url(controller), _paths(controller, binding)
        try:
            async with httpx.AsyncClient(
                verify=_ssl_context(controller), transport=self.transport,
                follow_redirects=False, timeout=httpx.Timeout(15), trust_env=False,
            ) as client:
                pages = await self.pages(context, client, base, paths["devices"], headers)
                rows = _rows(pages)
                record = _device_row(rows, binding, controller)
                if controller["vendor"] == "meraki":
                    port_pages = await self.pages(context, client, base, paths["ports"], headers)
                    status_pages = await self.pages(context, client, base, paths["status"], headers)
                    record = {**record, "ports": _merge_meraki_ports(_rows(port_pages), _rows(status_pages))}
                elif controller["vendor"] == "unifi":
                    detail_rows = _rows(await self.pages(
                        context, client, base, paths["details"], headers,
                    ))
                    detail = _device_row(detail_rows, binding, controller)
                    statistic_rows = _rows(await self.pages(
                        context, client, base, paths["status"], headers,
                    ))
                    if len(statistic_rows) != 1:
                        raise ConnectionPolicyError("controller_response_invalid")
                    record = {**record, **detail, "statistics": statistic_rows[0]}
                return record
        finally:
            # Do not retain token-bearing objects beyond this collection attempt.
            headers.clear()


def _rows(pages) -> list[dict]:
    result = []
    for value in pages:
        current = value
        if isinstance(current, dict):
            for key in ("data", "results", "result", "devices", "switches"):
                if key in current:
                    current = current[key]
                    break
        if isinstance(current, dict):
            for key in ("data", "items", "devices", "switches"):
                if key in current:
                    current = current[key]
                    break
        if isinstance(current, dict):
            current = [current]
        if not isinstance(current, list) or any(not isinstance(row, dict) for row in current):
            raise ConnectionPolicyError("controller_response_invalid")
        result.extend(current)
        if len(result) > MAX_ROWS:
            raise ConnectionPolicyError("controller_row_limit")
    return result


def _first(row, *keys):
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _device_row(rows, binding, controller):
    wanted = binding["external_device_id"]
    for row in rows:
        identity = str(_first(row, "serial", "id", "deviceId", "device_id", "mac") or "")
        if identity != wanted:
            continue
        site = _first(row, "networkId", "siteId", "site_id")
        if site is not None and str(site) != binding["external_site_id"]:
            raise ConnectionPolicyError("controller_device_site_mismatch")
        return row
    raise ConnectionPolicyError("controller_device_not_found")


def _merge_meraki_ports(config, status):
    by_id = {str(_first(row, "portId", "id")): dict(row) for row in config}
    for row in status:
        identifier = str(_first(row, "portId", "id"))
        by_id.setdefault(identifier, {}).update(row)
    return list(by_id.values())


def _bool(value):
    if isinstance(value, bool):
        return value
    token = str(value or "").lower()
    if token in {"up", "connected", "enabled", "active", "true", "1"}:
        return True
    if token in {"down", "disconnected", "disabled", "inactive", "false", "0"}:
        return False
    return None


def _number(value, *, scale=1):
    if value in {None, "", "unknown"} or isinstance(value, bool):
        return None
    try:
        result = float(value) * scale
    except (TypeError, ValueError, OverflowError):
        return None
    return result if 0 <= result <= 2**64 - 1 else None


def _capacity_bps(value):
    if isinstance(value, str):
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([GMTK]?)bps\s*", value, re.I)
        if not match:
            return None
        multiplier = {
            "": 1, "k": 1_000, "m": 1_000_000,
            "g": 1_000_000_000, "t": 1_000_000_000_000,
        }[match.group(2).lower()]
        return _number(match.group(1), scale=multiplier)
    return _number(value, scale=1_000_000)


def _port_entries(record):
    ports = _first(record, "ports", "switchPorts", "interfaces", "port_table") or []
    if isinstance(ports, dict):
        ports = ports.get("ports", [])
    if not isinstance(ports, list) or len(ports) > MAX_ROWS:
        raise ConnectionPolicyError("controller_port_limit")
    entries = []
    for index, port in enumerate(ports):
        if not isinstance(port, dict):
            raise ConnectionPolicyError("controller_response_invalid")
        identifier = _first(port, "name", "portId", "id", "port", "interface")
        if identifier is None and _first(port, "idx") is not None:
            identifier = f"Port {_first(port, 'idx')}"
        name = str(identifier or "")[:160]
        if not name:
            raise ConnectionPolicyError("controller_port_identity_missing")
        speed = _capacity_bps(_first(port, "speedMbps", "speed_mbps", "maxSpeedMbps", "speed"))
        admin = _bool(_first(port, "enabled", "adminUp", "admin_up", "adminStatus"))
        oper = _bool(_first(port, "status", "operUp", "oper_up", "linkStatus"))
        traffic = port.get("trafficInKbps") if isinstance(port.get("trafficInKbps"), dict) else {}
        rx_bps = _number(_first(traffic, "recv"), scale=1_000)
        tx_bps = _number(_first(traffic, "sent"), scale=1_000)
        connector = str(port.get("connector") or "").upper()
        connector_kind = {
            "RJ45": "rj45", "SFP": "sfp", "SFPPLUS": "sfp", "SFP28": "sfp",
            "QSFP": "qsfp", "QSFP28": "qsfp",
        }.get(connector, "unknown")
        sample = {
            "admin_up": admin, "oper_up": oper, "capacity_bps": speed,
            "rx_bps": rx_bps, "tx_bps": tx_bps,
            "rate_interval_seconds": 300 if rx_bps is not None or tx_bps is not None else None,
            "in_octets": _number(_first(port, "inOctets", "rxBytes", "rx_bytes")),
            "out_octets": _number(_first(port, "outOctets", "txBytes", "tx_bytes")),
            "errors": _number(_first(port, "errors", "rxErrors", "rx_errors")),
            "tx_errors": _number(_first(port, "txErrors", "tx_errors")),
            "discards": _number(_first(port, "discards", "rxDiscards", "rx_discards")),
            "tx_discards": _number(_first(port, "txDiscards", "tx_discards")),
            "access_vlan": int(_first(port, "vlan", "accessVlan", "pvid")) if str(_first(port, "vlan", "accessVlan", "pvid") or "").isdigit() else None,
            "pvid": int(_first(port, "vlan", "accessVlan", "pvid")) if str(_first(port, "vlan", "accessVlan", "pvid") or "").isdigit() else None,
            "vlan_mode": str(_first(port, "type", "mode", "vlanMode") or "unknown").lower()
                if str(_first(port, "type", "mode", "vlanMode") or "").lower() in {"access", "trunk"} else "unknown",
            "counter_bits": 64, "counter_epoch_known": False, "vrf_known": False,
        }
        entries.append({"name": name, "kind": "ethernet", "physical": True,
                        "connector": connector_kind, "index": index + 1, "sample": sample})
    if not entries:
        raise ConnectionPolicyError("controller_ports_missing")
    return entries


def _merge_inventory(device, runtime, entries, record, vendor):
    at = now()
    existing = {item.name.casefold(): item for item in device.interfaces}
    interfaces, samples, ports, bindings = [], [], [], []
    chassis_id = f"{device.id}:{runtime}:chassis"
    for ordinal, entry in enumerate(entries, 1):
        suffix = sha256(entry["name"].casefold().encode()).hexdigest()[:20]
        old = existing.get(entry["name"].casefold())
        interface_id = old.id if old else f"{device.id}:{runtime}:if:{suffix}"
        sample = InterfaceSample(interface_id=interface_id, source="api", **entry["sample"])
        def observed(value):
            return Observation(value=value, observed_at=at, source="api", stale_after_seconds=120,
                               quality="ok" if value is not None else "unknown")
        interfaces.append(Interface(
            id=interface_id, name=entry["name"], kind="ethernet", if_index=entry["index"],
            admin_up=observed(sample.admin_up), oper_up=observed(sample.oper_up),
            speed_mbps=observed(sample.capacity_bps / 1_000_000 if sample.capacity_bps else None),
        ))
        port_id = f"{device.id}:{runtime}:port:{suffix}"
        ports.append(PhysicalPort(id=port_id, component_id=chassis_id,
            label=entry["name"], connector=entry["connector"],
            group="Controller API", ordinal=ordinal))
        bindings.append(PortBinding(id=port_id + ":binding", physical_port_id=port_id,
                                    interface_id=interface_id, binding_quality="explicit"))
        samples.append(sample)
    model = str(_first(record, "model", "type", "product", "productModel") or device.model)[:160]
    serial = str(_first(record, "serial", "serialNumber") or device.serial)[:160]
    version = str(_first(record, "firmware", "firmwareVersion", "version", "softwareVersion") or device.os_version)[:160]
    updated = device.model_copy(update={
        "vendor": vendor, "model": model, "serial": serial, "os_version": version,
        "interfaces": interfaces, "physical_ports": ports, "bindings": bindings,
        "components": [PhysicalComponent(id=chassis_id, kind="chassis", label=model or "Controller switch")],
        "inventory_source": "api", "inventory_observed_at": at,
    })
    health = _first(record, "health", "systemStats", "statistics") or {}
    if not isinstance(health, dict):
        health = {}
    batch = Telemetry(observed_at=at, source="api", reachability="reachable", interfaces=samples,
        health=Health(
            cpu_percent=_number(_first(health, "cpuUtilizationPct", "cpuPercent", "cpu_percent", "cpu")),
            memory_percent=_number(_first(health, "memoryUtilizationPct", "memoryPercent", "memory_percent", "memory")),
            temperature_c=_number(_first(health, "temperatureC", "temperature_c", "temperature")),
            uptime_seconds=int(_number(_first(health, "uptimeSec", "uptimeSeconds", "uptime_seconds", "uptime")) or 0) or None,
        ))
    return updated, batch


def parse_controller_record(device, record, groups):
    runtime = _runtime(device)
    if runtime not in PROFILE_ID:
        raise ConnectionPolicyError("controller_profile_unsupported")
    profile_id = PROFILE_ID[runtime]
    vendor_key = RUNTIME_VENDOR[runtime]
    vendor_name, os_family, mode = IDENTITY[vendor_key]
    entries = _port_entries(record)
    updated, batch = _merge_inventory(device, runtime, entries, record, vendor_name)
    data = batch.model_dump(mode="json")
    result = ReadResult(updated, observed_profile_id=profile_id, identity_evidence={
        "vendor": vendor_name, "model": updated.model, "os_family": os_family,
        "os_version": updated.os_version, "management_mode": mode,
    })
    supported = SUPPORTED[runtime]
    for group in groups:
        fields = {field: "unsupported" for field in supported.get(group, ())}
        if group == "fast":
            payload = {"interfaces": data["interfaces"]}
            for field in fields:
                if any(row.get(field) is not None and row.get(field) != "unknown" for row in data["interfaces"]):
                    fields[field] = "ok"
        elif group == "health":
            payload = {"health": data["health"], "interfaces": []}
            for field in fields:
                if data["health"].get(field) is not None:
                    fields[field] = "ok"
        elif group == "network":
            payload = {"interfaces": [{key: row.get(key) for key in (
                "interface_id", "access_vlan", "pvid", "vlan_mode", "allowed_vlans"
            )} for row in data["interfaces"]], "neighbors": [], "endpoints": data["endpoints"]}
            if any(row.get("access_vlan") for row in data["interfaces"]) and "vlan" in fields:
                fields["vlan"] = "ok"
        else:
            payload = {"model": updated.model, "serial": updated.serial,
                       "os_version": updated.os_version,
                       "components": [item.model_dump(mode="json") for item in updated.components]}
            for field, key in (("model", "model"), ("serial", "serial"), ("os_version", "os_version")):
                if field in fields and payload[key]:
                    fields[field] = "ok"
            if "chassis" in fields:
                fields["chassis"] = "ok"
            result.inventory_complete = True
        result.payloads[group] = payload
        complete = all(value in {"ok", "unsupported"} for value in fields.values())
        quality = "unsupported" if not fields or all(
            value == "unsupported" for value in fields.values()
        ) else "ok" if complete else "partial"
        result.metadata[group] = metadata(
            group, runtime, source="api", quality=quality,
            complete=complete, fields=fields,
        )
    return result


class ControllerAPITransportAdapter:
    kind = "api"

    def __init__(self, *, transport=None, sleeper: Callable = asyncio.sleep):
        self.client = ControllerHTTPClient(transport=transport, sleeper=sleeper)

    async def collect(self, context: TransportContext, groups: set[str]) -> ReadResult:
        store, device = context.store, context.device
        with store.engine.connect() as conn:
            binding_row = conn.execute(sa.select(store.device_controller_bindings).where(
                store.device_controller_bindings.c.device_id == device.id)).mappings().first()
            controller_row = conn.execute(sa.select(store.api_controllers).where(
                store.api_controllers.c.id == binding_row["controller_id"])).mappings().first() if binding_row else None
        if not binding_row or not controller_row:
            raise ConnectionPolicyError("controller_binding_missing")
        controller = dict(controller_row)
        binding = dict(binding_row)
        if not controller["enabled"]:
            raise ConnectionPolicyError("controller_disabled")
        if controller["site"] != device.site or binding["external_site_id"] != controller["external_site_id"]:
            raise ConnectionPolicyError("controller_device_site_mismatch")
        secret, secret_metadata = context.vault.get_controller(controller["id"])
        try:
            context.checkpoint()
            record = await self.client.collect(context, controller, binding, secret, secret_metadata)
            context.checkpoint()
            return parse_controller_record(device, record, groups)
        finally:
            secret.clear()
