import { describe, expect, it } from "vitest";
import { resolutionLabel, type Endpoint } from "../lib/topology";
import { nodeKindLabels, relationLabels, portTopologyIds, topologySubset } from "../lib/ip-topology";
import type { Projection } from "../lib/contracts";

const endpoint: Endpoint = { id: "ep", interface_id: "if1", mac: "02:00:00:00:00:01", addresses: [],
  vlan: 10, discovery: "fdb", state: "unknown", evidence: "fixture" };
describe("shared MAC/IP presentation", () => {
  it.each([
    ["resolved", "IP eşleştirildi"], ["unresolved", "IP bulunamadı"],
    ["ambiguous", "IP belirsiz"], ["stale", "Son bilinen"], ["observed", "doğrudan gözlendi"],
  ] as const)("distinguishes %s from a verified current address", (status, text) => {
    expect(resolutionLabel({ ...endpoint, resolution: { status, reason: null, observed_at: null, sources: [] } })).toContain(text);
  });
  it("keeps endpoint observations separate from physical and L2 edges in port scope", () => {
    const nodes = [{ id: "interface:if1", interface_id: "if1", name: "eth1", kind: "interface", detail: "" },
      { id: "endpoint:ep", interface_id: "if1", endpoint_id: "ep", name: "192.0.2.101", kind: "endpoint", detail: endpoint.mac }];
    const links = [{ source: nodes[0].id, target: nodes[1].id, relation: "endpoint" as const, evidence: "ARP + FDB" }];
    const row = { device: { physical_ports: [], bindings: [{ physical_port_id: "p1", interface_id: "if1", binding_quality: "explicit" }] },
      topology: { nodes, links } } as unknown as Projection;
    expect(topologySubset(nodes, links, portTopologyIds(row, "p1"))).toHaveLength(2);
    expect(nodeKindLabels.endpoint).toBe("MAC / IP gözlemi");
    expect(relationLabels.endpoint).not.toContain("Fiziksel");
  });
});
