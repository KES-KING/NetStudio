import type { Projection, Reachability } from "./contracts";

export type Endpoint = {
  id: string; interface_id: string; mac: string; addresses: string[];
  vlan: number | null; discovery: "fdb" | "arp" | "ndp";
  state: "reachable" | "stale" | "static" | "unknown"; evidence: string;
  vrf?: string | null; vrf_known?: boolean;
  resolution?: {
    status: "observed" | "resolved" | "unresolved" | "stale" | "ambiguous";
    reason: string | null; observed_at: string | null;
    sources: { device_id: string; device_name: string; interface_id: string; discovery: string; observed_at: string; evidence: string }[];
  };
};
export type EndpointCollection = { status: "ok" | "partial" | "unknown" | "unsupported" | "error"; entries: Endpoint[] };
export type NetworkDevice = {
  id: string; name: string; management_address: string; site: string; device_type: string;
  reachability: Reachability; data_state: Projection["data_state"]; observed_at: string | null; source: string | null;
  ports: { id: string; label: string; connector: string; parent_port_id: string | null }[];
  interfaces: { id: string; name: string; kind: string; port_ids: string[] }[];
  endpoints: EndpointCollection;
  neighbors: { id: string; interface_id: string; label: string; relation: "physical" | "l2"; evidence: string; addresses?: string[]; observed_at?: string | null }[];
};
export type ObservedLink = {
  id: string; source_device_id: string; source_interface_id: string;
  target_device_id: string; target_interface_id: string | null;
  relation: "physical" | "l2"; evidence: string; observed_at: string;
  data_state: Projection["data_state"]; source: string;
};
export type NetworkGraph = { devices: NetworkDevice[]; links: ObservedLink[]; generated_at: string };
export type Zone = { id: string; name: string; x: number; y: number; width: number; height: number; tone: "slate" | "blue" | "sand" };
export type Placement = { device_id: string; x: number; y: number; zone_id: string | null };
export type ManualLink = { id: string; source_device_id: string; source_port_id: string; target_device_id: string; target_port_id: string };
export type TopologyBoard = {
  version: number; zones: Zone[]; placements: Placement[]; links: ManualLink[];
  updated_at?: string | null; omitted_references?: number;
};
export type Selection = { kind: "device"; id: string } | { kind: "endpoint"; id: string; deviceId: string }
  | { kind: "neighbor"; id: string; deviceId: string } | { kind: "zone"; id: string }
  | { kind: "manual" | "observed"; id: string } | null;
export const dataLabels = { current: "Güncel gözlem", no_data: "Veri yok", stale: "Son veri güncel değil", error: "Veri alma hatası", unreachable: "Cihaz erişilemiyor" };
export const endpointLabels = { ok: "Tablo okundu", partial: "Kısmi tablo", unknown: "Henüz toplanmadı", unsupported: "Desteklenmiyor", error: "Tablo okunamadı" };
export const neighborStateLabels = { reachable: "Komşuluk erişilebilir", stale: "Komşuluk yeniden doğrulanmalı", static: "Statik kayıt", unknown: "Komşuluk durumu bilinmiyor" };
export function resolutionLabel(endpoint: Endpoint) {
  const status = endpoint.resolution?.status;
  return status ? {
    observed: "IP doğrudan gözlendi", resolved: "IP eşleştirildi", unresolved: "IP bulunamadı · kapsamı doğrulanmış ARP/NDP kaydı yok",
    stale: "Son bilinen gözlem · güncelliği doğrulanmıyor", ambiguous: "IP belirsiz · çelişkili adres veya VRF kayıtları",
  }[status] : endpoint.addresses.length ? "IP gözlendi" : "IP bilinmiyor";
}
export const reachLabels = { reachable: "Erişilebilir", unreachable: "Erişilemiyor", unknown: "Durum bilinmiyor" };
export const relationLabels = { physical: "Fiziksel kanıt", l2: "L2 komşuluk", manual: "Elle çizilen", endpoint: "MAC / IP gözlemi" };
export const GRAPH_DEVICE_LIMIT = 24;
export const GRAPH_ENDPOINT_LIMIT = 6;

export function positionFor(device: NetworkDevice, index: number, board: TopologyBoard): Placement {
  return board.placements.find((p) => p.device_id === device.id) ?? {
    device_id: device.id, x: 330 + (index % 3) * 680, y: 270 + Math.floor(index / 3) * 560, zone_id: null,
  };
}
export function layoutPositions(devices: NetworkDevice[], board: TopologyBoard, order: string[]) {
  // Keep intentional placements fixed. Pack automatic neighborhoods around them,
  // reserving endpoint space so an unplaced device cannot hide a zoned device.
  const ids = new Set(devices.map((d) => d.id));
  const result = new Map(board.placements.filter((p) => ids.has(p.device_id)).map((p) => [p.device_id, p]));
  const columns = Math.max(3, Math.ceil(Math.sqrt(devices.length)));
  const sorted = [...devices].sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
  for (const device of sorted) {
    if (result.has(device.id)) continue;
    let slot = Math.max(0, order.indexOf(device.id));
    let candidate: Placement;
    do {
      candidate = { device_id: device.id, x: 330 + (slot % columns) * 680, y: 270 + Math.floor(slot / columns) * 680, zone_id: null };
      slot++;
    } while ([...result.values()].some((p) => Math.abs(p.x - candidate.x) < 650 && Math.abs(p.y - candidate.y) < 600));
    result.set(device.id, candidate);
  }
  return result;
}
export function endpointPosition(position: Placement, index: number, compact = false, detailed = false) {
  const offsets = compact ? [[0, -158], [-84, 165], [84, 165], [-84, 300], [84, 300], [0, 435]] : [[0, -158], [-145, 165], [145, 165], [-220, -110], [220, -110], [0, 300]];
  if (detailed) {
    const stepX = compact ? 180 : 210, stepY = 120;
    let remaining = index;
    for (let ring = 1; ; ring++) {
      const halfWidth = stepX * ring, halfHeight = 145 * ring;
      const slots: [number, number][] = [];
      for (let x = -halfWidth; x <= halfWidth; x += stepX) slots.push([x, -halfHeight]);
      for (let y = -halfHeight + stepY; y < halfHeight; y += stepY) slots.push([halfWidth, y]);
      for (let x = halfWidth; x >= -halfWidth; x -= stepX) slots.push([x, halfHeight]);
      for (let y = halfHeight - stepY; y > -halfHeight; y -= stepY) slots.push([-halfWidth, y]);
      if (remaining < slots.length) {
        const [dx, dy] = slots[remaining];
        return { x: position.x + dx, y: position.y + dy };
      }
      remaining -= slots.length;
    }
  }
  const [dx, dy] = offsets[index % offsets.length];
  return { x: position.x + dx, y: position.y + dy };
}
export function interfaceLabel(device: NetworkDevice, id: string | null) {
  return device.interfaces.find((i) => i.id === id)?.name ?? "Arayüz bilinmiyor";
}
export function portLabel(device: NetworkDevice, id: string) {
  return device.ports.find((p) => p.id === id)?.label ?? "Port artık envanterde yok";
}
export function physicalLabels(device: NetworkDevice, interfaceId: string) {
  const iface = device.interfaces.find((i) => i.id === interfaceId);
  return iface?.port_ids.map((id) => portLabel(device, id)).join(", ") || "Fiziksel port eşlemesi yok";
}
export function movePlacement(board: TopologyBoard, placement: Placement): TopologyBoard {
  return { ...board, placements: [...board.placements.filter((p) => p.device_id !== placement.device_id), placement] };
}
export function moveZone(board: TopologyBoard, zone: Zone, x: number, y: number): TopologyBoard {
  const dx = x - zone.x, dy = y - zone.y;
  return { ...board, zones: board.zones.map((z) => z.id === zone.id ? { ...z, x, y } : z),
    placements: board.placements.map((p) => p.zone_id === zone.id ? { ...p, x: p.x + dx, y: p.y + dy } : p) };
}
export function deleteZone(board: TopologyBoard, id: string): TopologyBoard {
  return { ...board, zones: board.zones.filter((z) => z.id !== id), placements: board.placements.map((p) => p.zone_id === id ? { ...p, zone_id: null } : p) };
}
export function boardPayload(board: TopologyBoard) {
  return { version: board.version, zones: board.zones, placements: board.placements, links: board.links };
}
export function elbowPath(a: { x: number; y: number }, b: { x: number; y: number }) {
  // Boundary anchors are supplied by the renderer. Deterministic orthogonal paths.
  const middle = Math.round((a.y + b.y) / 2);
  return `M ${a.x} ${a.y} V ${middle} H ${b.x} V ${b.y}`;
}
export function matchesDevice(device: NetworkDevice, query: string) {
  const q = query.trim().toLocaleLowerCase("tr");
  return !q || [device.name, device.management_address, device.site,
    ...device.endpoints.entries.flatMap((e) => [e.mac, ...e.addresses])].some((v) => v.toLocaleLowerCase("tr").includes(q));
}
export function endpointsForCanvas(device: NetworkDevice, query: string, selectedId?: string, detailed = false) {
  const q = query.trim().toLowerCase();
  const list = device.endpoints.entries;
  if (detailed) return list;
  const prioritized = list.filter((e) => e.id === selectedId || (q && [e.mac, ...e.addresses].some((v) => v.toLowerCase().includes(q))));
  return [...prioritized, ...list.filter((e) => !prioritized.includes(e))].slice(0, GRAPH_ENDPOINT_LIMIT);
}
