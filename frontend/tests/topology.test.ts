import { describe, expect, it } from "vitest";
import { boardPayload, deleteZone, endpointPosition, endpointsForCanvas, layoutPositions, matchesDevice, moveZone, physicalLabels, positionFor, type NetworkDevice, type TopologyBoard } from "../lib/topology";

const board: TopologyBoard = { version: 3, zones: [{ id: "z", name: "Test zone", x: 0, y: 0, width: 600, height: 500, tone: "slate" }], placements: [{ device_id: "d", x: 300, y: 250, zone_id: "z" }], links: [] };
const device: NetworkDevice = { id: "d", name: "Test switch", management_address: "192.0.2.1", site: "Test", device_type: "switch", reachability: "unknown", data_state: "no_data", observed_at: null, source: null,
  ports: [{ id: "p", label: "Ethernet 1", connector: "rj45", parent_port_id: null }], interfaces: [{ id: "i", name: "eth1", kind: "ethernet", port_ids: ["p"] }, { id: "v", name: "Vlan10", kind: "svi", port_ids: [] }],
  endpoints: { status: "ok", entries: Array.from({ length: 15 }, (_, index) => ({ id: `e${index}`, interface_id: "i", mac: `02:00:00:00:00:${index.toString(16).padStart(2, "0")}`, addresses: [`192.0.2.${100 + index}`], vlan: 10, discovery: "fdb", state: "unknown", evidence: "test only" })) }, neighbors: [] };

describe("topology geometry and evidence", () => {
  it("preserves saved identity/position across a changed device order", () => {
    expect(positionFor(device, 12, board).x).toBe(300);
    expect(boardPayload({ ...board, updated_at: "time", omitted_references: 2 })).toEqual(board);
  });
  it("moves grouped devices with a zone and removes the zone without deleting devices", () => {
    const moved = moveZone(board, board.zones[0], 40, 60);
    expect(moved.placements[0]).toMatchObject({ x: 340, y: 310 });
    expect(deleteZone(moved, "z").placements[0]).toMatchObject({ x: 340, y: 310, zone_id: null });
    expect(board.placements[0].x).toBe(300);
  });
  it("keeps unbound SVI observations distinct from physical connectors", () => {
    expect(physicalLabels(device, "i")).toBe("Ethernet 1");
    expect(physicalLabels(device, "v")).toBe("Fiziksel port eşlemesi yok");
  });
  it("packs default devices away from saved device neighborhoods", () => {
    const pinned = { ...board, placements: [{ device_id: "d", x: 1010, y: 270, zone_id: "z" }] };
    const positions = layoutPositions([device, { ...device, id: "other" }, { ...device, id: "third" }], pinned, ["d", "other", "third"]);
    expect(positions.get("d")).toEqual(pinned.placements[0]);
    const values = [...positions.values()];
    for (const a of values) for (const b of values) {
      if (a.device_id !== b.device_id) expect(Math.abs(a.x - b.x) >= 650 || Math.abs(a.y - b.y) >= 600).toBe(true);
    }
  });
  it("limits the rendered neighborhood without losing a selected or searched endpoint", () => {
    expect(endpointsForCanvas(device, "")).toHaveLength(6);
    expect(endpointsForCanvas(device, "", "e14")[0].id).toBe("e14");
    expect(endpointsForCanvas(device, "192.0.2.114")[0].id).toBe("e14");
    expect(device.endpoints.entries).toHaveLength(15);
    expect(matchesDevice(device, "192.0.2.114")).toBe(true);
    expect(matchesDevice(device, "missing")).toBe(false);
  });
  it("returns and lays out every endpoint when detailed mode is enabled", () => {
    expect(endpointsForCanvas(device, "", undefined, true)).toEqual(device.endpoints.entries);
    const positions = device.endpoints.entries.map((_, index) => endpointPosition(board.placements[0], index, false, true));
    expect(new Set(positions.map(({ x, y }) => `${x}:${y}`)).size).toBe(device.endpoints.entries.length);
    expect(endpointPosition(board.placements[0], 0)).toEqual({ x: 300, y: 92 });
  });
});
