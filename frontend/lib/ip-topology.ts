import type { Projection, TopologyNode } from "./contracts";

export type IPLink = Projection["topology"]["links"][number];
export type IPPosition = TopologyNode & { x: number; y: number };
export const IP_TOPOLOGY_ZOOM = { min: .7, max: 1.8, step: .15 };
export const IP_NODE_LIMIT = 80;
export const relationLabels = { l3: "L3 / IP", l2: "L2 komşuluk", physical: "Fiziksel bağlantı" };
export const nodeKindLabels: Record<string, string> = { interface: "Arayüz", subnet: "Alt ağ", neighbor: "Komşu" };
export const linkId = (link: IPLink) => JSON.stringify([link.source, link.target, link.relation, link.evidence]);

/** A one-hop view, not a transitive connectivity inference. */
export function topologySubset(nodes: TopologyNode[], links: IPLink[], seeds?: Set<string>) {
  if (!seeds) return nodes;
  const ids = new Set(seeds);
  for (const link of links) {
    if (seeds.has(link.source)) ids.add(link.target);
    if (seeds.has(link.target)) ids.add(link.source);
  }
  return nodes.filter((node) => ids.has(node.id));
}

/** Explicit pixel geometry: sparse graphs must never stretch to fill the viewport. */
export function layoutIPTopologyNodes(nodes: TopologyNode[], width: number) {
  const nodeWidth = Math.max(96, Math.min(176, (width - 76) / 2));
  const gap = width < 520 ? 44 : 100;
  const left = nodes.filter((n) => n.kind === "interface");
  const right = nodes.filter((n) => n.kind !== "interface");
  const rows = Math.max(left.length, right.length);
  const position = (lane: TopologyNode[], x: number) => lane.map((n, i) => ({
    ...n, x, y: 42 + (i + (rows - lane.length) / 2) * 76,
  }));
  return {
    nodes: [...position(left, 16 + nodeWidth / 2), ...position(right, 16 + nodeWidth * 1.5 + gap)],
    nodeWidth, nodeHeight: 60, width: 32 + nodeWidth * 2 + gap, height: Math.max(84, rows * 76 + 8),
  };
}

/** Anchor to boundaries; same-lane records route outside nodes, never through their bodies. */
export function routeIPLink(a: IPPosition, b: IPPosition, width: number, lane = 0) {
  const offset = Math.max(-18, Math.min(18, lane * 7));
  if (a.id === b.id) {
    const x = a.x + width / 2;
    return { path: `M ${x} ${a.y - 12} H ${x + 12} V ${a.y + 12} H ${x}`, x: x + 12, y: a.y };
  }
  if (a.x === b.x) {
    const x = a.x - width / 2, outside = Math.max(4, x - 8);
    return { path: `M ${x} ${a.y + offset} H ${outside} V ${b.y + offset} H ${x}`, x: outside, y: (a.y + b.y) / 2 };
  }
  const direction = b.x > a.x ? 1 : -1;
  const ax = a.x + direction * width / 2, bx = b.x - direction * width / 2;
  const mid = (ax + bx) / 2 + offset;
  return { path: `M ${ax} ${a.y + offset} H ${mid} V ${b.y + offset} H ${bx}`, x: mid, y: (a.y + b.y) / 2 + offset };
}

/** Physical-to-logical selection uses inventory bindings even without a traffic sample. */
export function portTopologyIds(row: Projection, portId?: string) {
  if (!portId) return new Set<string>();
  const ports = new Set([portId, ...row.device.physical_ports.filter((p) => p.parent_port_id === portId).map((p) => p.id)]);
  const interfaces = new Set(row.device.bindings.filter((b) => b.binding_quality === "explicit" && ports.has(b.physical_port_id)).map((b) => b.interface_id));
  return new Set(row.topology.nodes.filter((n) => n.interface_id && interfaces.has(n.interface_id)).map((n) => n.id));
}
