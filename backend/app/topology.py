"""User-owned diagram layouts and a site-authorized, evidence-preserving graph.

Manual edges are annotations only. Neither IP adjacency nor MAC learning creates
a device-to-device physical link. Polling never writes or re-arranges a board.
"""
from typing import Literal

from fastapi import Request
from pydantic import Field, field_validator, model_validator
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from .auth import fail
from .contracts import StrictModel
from .database import now
from .security import Permission, has_permission
from .telemetry import projection
from .endpoint_resolution import latest_payloads, resolve_endpoints


class Zone(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    x: float = Field(ge=0, le=20000)
    y: float = Field(ge=0, le=20000)
    width: float = Field(ge=400, le=6000)
    height: float = Field(ge=280, le=6000)
    tone: Literal["slate", "blue", "sand"] = "slate"

    @field_validator("name")
    @classmethod
    def name_text(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("invalid_zone_name")
        return value


class Placement(StrictModel):
    device_id: str = Field(min_length=1, max_length=64)
    x: float = Field(ge=0, le=26000)
    y: float = Field(ge=0, le=26000)
    zone_id: str | None = Field(default=None, max_length=80)


class ManualLink(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    source_device_id: str = Field(min_length=1, max_length=64)
    source_port_id: str = Field(min_length=1, max_length=160)
    target_device_id: str = Field(min_length=1, max_length=64)
    target_port_id: str = Field(min_length=1, max_length=160)


class Board(StrictModel):
    version: int = Field(default=0, ge=0, le=2**31 - 2)
    zones: list[Zone] = Field(default_factory=list, max_length=40)
    placements: list[Placement] = Field(default_factory=list, max_length=500)
    links: list[ManualLink] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def references(self):
        zone_ids = {z.id for z in self.zones}
        if len(zone_ids) != len(self.zones) or len({p.device_id for p in self.placements}) != len(self.placements) or len({l.id for l in self.links}) != len(self.links):
            raise ValueError("duplicate_topology_id")
        if any(p.zone_id and p.zone_id not in zone_ids for p in self.placements):
            raise ValueError("unknown_zone")
        pairs = set()
        for link in self.links:
            pair = tuple(sorted(((link.source_device_id, link.source_port_id), (link.target_device_id, link.target_port_id))))
            if link.source_device_id == link.target_device_id or pair in pairs:
                raise ValueError("invalid_topology_link")
            pairs.add(pair)
        return self


def authorized_devices(store, user):
    return {d.id: d for d in store.list_devices() if has_permission(user, Permission.INVENTORY_READ, d.site)}


def valid_link(link, devices):
    for side in ("source", "target"):
        device = devices.get(link[f"{side}_device_id"])
        if not device or not any(p.id == link[f"{side}_port_id"] and p.connector != "console" for p in device.physical_ports):
            return False
    return True


def visible_board(row, devices):
    value = row["payload"] if row else Board().model_dump()
    placements = [p for p in value["placements"] if p["device_id"] in devices]
    links = [l for l in value["links"] if valid_link(l, devices)]
    return {**value, "placements": placements, "links": links, "version": row["version"] if row else 0,
        "updated_at": row["updated_at"].isoformat() if row else None,
        "omitted_references": len(value["placements"]) + len(value["links"]) - len(placements) - len(links)}


def network_graph(store, devices):
    latest = latest_payloads(store, devices)
    resolved = resolve_endpoints(devices, latest)
    rows, links = [], []
    for device in sorted(devices.values(), key=lambda d: (d.name.casefold(), d.id)):
        data = latest.get(device.id)
        view = projection(device, data, endpoints=resolved[device.id])
        interface_ids = {i.id for i in device.interfaces}
        endpoint_collection = resolved[device.id]
        ports = [{"id": p.id, "label": p.label, "connector": p.connector, "parent_port_id": p.parent_port_id} for p in device.physical_ports if p.connector != "console"]
        interfaces = []
        for interface in device.interfaces:
            # Conflicting / inferred bindings never claim a physical connector.
            bindings = [b.physical_port_id for b in device.bindings if b.interface_id == interface.id and b.binding_quality == "explicit"]
            interfaces.append({"id": interface.id, "name": interface.name, "kind": interface.kind, "port_ids": sorted(set(bindings))})
        unknown_neighbors = []
        for neighbor in (data or {}).get("neighbors", []):
            if neighbor["interface_id"] not in interface_ids:
                continue
            remote_id = neighbor.get("remote_device_id")
            if remote_id:
                if remote_id not in devices or remote_id == device.id:
                    continue  # Do not leak out-of-scope IDs, names or remote ports.
                remote_if = neighbor.get("remote_interface_id")
                if remote_if not in {i.id for i in devices[remote_id].interfaces}:
                    remote_if = None
                links.append({"id": f"{device.id}:{neighbor['id']}", "source_device_id": device.id,
                    "source_interface_id": neighbor["interface_id"], "target_device_id": remote_id,
                    "target_interface_id": remote_if, "relation": neighbor["relation"], "evidence": neighbor["evidence"],
                    "observed_at": data["observed_at"], "data_state": view["data_state"], "source": data["source"]})
            else:
                unknown_neighbors.append({**{k: neighbor[k] for k in ("id", "interface_id", "label", "relation", "evidence")},
                    "addresses": neighbor.get("addresses", []),
                    "observed_at": neighbor.get("observed_at") or data.get("groups", {}).get("network", {}).get("observed_at") or data["observed_at"]})
        rows.append({"id": device.id, "name": device.name, "management_address": device.management_address,
            "site": device.site, "device_type": device.device_type, "ports": ports, "interfaces": interfaces,
            "reachability": view["reachability"], "data_state": view["data_state"],
            "observed_at": data["observed_at"] if data else None, "source": data["source"] if data else None,
            "endpoints": endpoint_collection,
            "neighbors": unknown_neighbors})
    return {"devices": rows, "links": links, "generated_at": now().isoformat()}


def install_topology_routes(app, context):
    @app.get("/api/v1/topology")
    def graph(request: Request):
        auth = context(request)
        return network_graph(app.state.store, authorized_devices(app.state.store, auth.user))

    @app.get("/api/v1/topology/board")
    def board(request: Request):
        auth = context(request)
        store = app.state.store
        with store.engine.connect() as conn:
            row = conn.execute(sa.select(store.topology_boards).where(store.topology_boards.c.user_id == auth.user.user_id)).mappings().first()
        return visible_board(row, authorized_devices(store, auth.user))

    @app.put("/api/v1/topology/board")
    def save_board(value: Board, request: Request):
        auth = context(request, True)
        store, at = app.state.store, now()
        payload = value.model_dump(mode="json", exclude={"version"})
        try:
            with store.engine.begin() as conn:
                # Serialize with account deletion / permission changes, not other users' boards.
                conn.execute(sa.select(store.users.c.id).where(store.users.c.id == auth.user.user_id).with_for_update()).scalar_one()
                auth = context(request, True)
                devices = authorized_devices(store, auth.user)
                if any(p.device_id not in devices for p in value.placements) or any(not valid_link(l, devices) for l in payload["links"]):
                    fail("topology_reference_unavailable", 422)
                values = {"payload": payload, "version": value.version + 1, "updated_at": at}
                if value.version == 0:
                    conn.execute(store.topology_boards.insert().values(user_id=auth.user.user_id, **values))
                else:
                    result = conn.execute(store.topology_boards.update().where(store.topology_boards.c.user_id == auth.user.user_id,
                        store.topology_boards.c.version == value.version).values(**values))
                    if result.rowcount != 1:
                        fail("topology_version_conflict", 409)
                store.record(auth.user.user_id, "topology.saved", "succeeded", conn=conn, status_code=200,
                    target_type="topology", target_id=auth.user.user_id,
                    details={"version": value.version + 1, "zone_count": len(value.zones), "device_count": len(value.placements),
                        "link_count": len(value.links), "input": payload})
        except IntegrityError:
            fail("topology_version_conflict", 409)
        return {**payload, "version": value.version + 1, "updated_at": at.isoformat(), "omitted_references": 0}
