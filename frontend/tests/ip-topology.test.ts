import { describe, expect, it } from "vitest";
import type { Projection, TopologyNode } from "../lib/contracts";
import { layoutIPTopologyNodes, linkId, portTopologyIds, routeIPLink, topologySubset, type IPLink } from "../lib/ip-topology";

const nodes: TopologyNode[] = [
  { id: "n1", name: "Neighbor", kind: "neighbor", detail: "LLDP" },
  { id: "i1", name: "GigabitEthernet0/0/1", kind: "interface", interface_id: "if1", detail: "192.0.2.1/24" },
  { id: "s1", name: "192.0.2.0/24", kind: "subnet", detail: "VRF bilinmiyor" },
  { id: "i2", name: "GigabitEthernet0/0/2", kind: "interface", detail: "198.51.100.1/24" },
];
const links: IPLink[] = [
  { source: "i1", target: "s1", relation: "l3", evidence: "192.0.2.1/24" },
  { source: "i1", target: "n1", relation: "l2", evidence: "LLDP" },
  { source: "i2", target: "n1", relation: "physical", evidence: "explicit" },
];

describe("device IP topology geometry and evidence", () => {
  it.each([280, 320, 390, 519, 520, 900, 1536])("keeps fixed readable nodes within a %ipx canvas", (width) => {
    const original = structuredClone(nodes);
    const layout = layoutIPTopologyNodes(nodes, width);
    expect(layout.width).toBeLessThanOrEqual(width);
    expect(layout.nodeWidth).toBeGreaterThanOrEqual(96);
    expect(layout.nodeWidth).toBeLessThanOrEqual(176);
    for (const n of layout.nodes) {
      expect(n.x - layout.nodeWidth / 2).toBeGreaterThanOrEqual(0);
      expect(n.x + layout.nodeWidth / 2).toBeLessThanOrEqual(width);
    }
    expect(nodes).toEqual(original);
  });
  it("never expands sparse graphs to viewport size or overlaps nodes in dense graphs", () => {
    const sparse = layoutIPTopologyNodes(nodes.slice(0, 2), 1400);
    expect(sparse.width).toBe(484);
    const dense = layoutIPTopologyNodes(Array.from({ length: 100 }, (_, i) => ({ ...nodes[1], id: `i${i}` })), 390);
    for (let i = 1; i < dense.nodes.length; i++) expect(dense.nodes[i].y - dense.nodes[i - 1].y).toBeGreaterThan(dense.nodeHeight);
  });
  it("filters one hop in either direction, without inferring transitive relations", () => {
    expect(topologySubset(nodes, links, new Set(["i1"])).map((n) => n.id)).toEqual(["n1", "i1", "s1"]);
    expect(topologySubset(nodes, links, new Set(["s1"])).map((n) => n.id)).toEqual(["i1", "s1"]);
    expect(topologySubset(nodes, links, new Set())).toEqual([]);
  });
  it("routes from boundaries and retains distinct parallel evidence", () => {
    const layout = layoutIPTopologyNodes(nodes, 900);
    const a = layout.nodes.find((n) => n.id === "i1")!, b = layout.nodes.find((n) => n.id === "s1")!;
    const route = routeIPLink(a, b, layout.nodeWidth);
    expect(route.path).toContain(`M ${a.x + layout.nodeWidth / 2} ${a.y}`);
    expect(route.path).toContain(`H ${b.x - layout.nodeWidth / 2}`);
    expect(routeIPLink(a, b, layout.nodeWidth, 1).path).not.toBe(route.path);
    expect(linkId(links[0])).not.toBe(linkId({ ...links[0], relation: "physical" }));
  });
  it("uses only explicit port bindings even with no telemetry", () => {
    const row = { device: { physical_ports: [], bindings: [
      { physical_port_id: "p1", interface_id: "if1", binding_quality: "explicit" },
      { physical_port_id: "p2", interface_id: "if1", binding_quality: "inferred" },
    ] }, topology: { nodes }, telemetry: null } as unknown as Projection;
    expect([...portTopologyIds(row, "p1")]).toEqual(["i1"]);
    expect([...portTopologyIds(row, "p2")]).toEqual([]);
    expect([...portTopologyIds(row)]).toEqual([]);
  });
});
