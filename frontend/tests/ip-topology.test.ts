import { describe, expect, it } from "vitest";
import type { TopologyNode } from "../lib/contracts";
import {
  IP_TOPOLOGY_NODE_SIZE,
  IP_TOPOLOGY_COMPACT_NODE_SIZE,
  IP_TOPOLOGY_ZOOM,
  ipTopologyOption,
  layoutIPTopologyNodes,
} from "../lib/ip-topology";

const nodes: TopologyNode[] = [
  { id: "n1", name: "Neighbor", kind: "neighbor", detail: "LLDP" },
  { id: "i1", name: "GigabitEthernet0/0/1", kind: "interface", detail: "192.0.2.1/24" },
  { id: "s1", name: "192.0.2.0/24", kind: "subnet", detail: "VRF bilinmiyor" },
  { id: "i2", name: "GigabitEthernet0/0/2", kind: "interface", detail: "198.51.100.1/24" },
];

describe("device IP topology layout", () => {
  it("uses stable lanes and compact vertical spacing without mutating API data", () => {
    const before = structuredClone(nodes);
    const positioned = layoutIPTopologyNodes(nodes);
    expect(nodes).toEqual(before);
    expect(positioned.map((node) => node.id)).toEqual(["i1", "i2", "s1", "n1"]);
    expect(positioned.filter((node) => node.kind === "interface").map((node) => node.x)).toEqual([0, 0]);
    expect(positioned.find((node) => node.id === "s1")?.x).toBe(230);
    expect(positioned.find((node) => node.id === "n1")?.x).toBe(460);
    expect(positioned.filter((node) => node.kind === "interface").map((node) => node.y)).toEqual([-44, 44]);
  });

  it("keeps node geometry fixed during roam and disables emphasis enlargement", () => {
    const option = ipTopologyOption({
      deviceId: "device-1",
      nodes,
      links: [{ source: "i1", target: "s1", relation: "l3", evidence: "192.0.2.1/24" }],
      zoom: 1,
      selectedId: "i1",
      related: new Set(["i1"]),
    });
    const series = (option.series as Record<string, unknown>[])[0];
    expect(series.symbolSize).toEqual(IP_TOPOLOGY_NODE_SIZE);
    expect(series.nodeScaleRatio).toBe(0);
    expect(series.emphasis).toMatchObject({ scale: false });
    expect(series.scaleLimit).toEqual({ min: IP_TOPOLOGY_ZOOM.min, max: IP_TOPOLOGY_ZOOM.max });
    expect(series.data).toHaveLength(nodes.length);

    const zoomed = ipTopologyOption({
      deviceId: "device-1",
      nodes,
      links: [],
      zoom: 1.5,
      selectedId: "",
      related: new Set(),
    });
    expect(((zoomed.series as Record<string, unknown>[])[0].symbolSize as number[])).toEqual(
      IP_TOPOLOGY_NODE_SIZE.map((value) => value / 1.5),
    );
  });

  it("collapses subnet and neighbor targets into a second lane in narrow panels", () => {
    const positioned = layoutIPTopologyNodes(nodes, true);
    expect(positioned.filter((node) => node.kind === "interface").map((node) => node.x)).toEqual([0, 0]);
    expect(positioned.filter((node) => node.kind !== "interface").map((node) => node.x)).toEqual([180, 180]);
    const option = ipTopologyOption({
      deviceId: "device-1",
      nodes,
      links: [{ source: "i1", target: "s1", relation: "l3", evidence: "192.0.2.1/24" }],
      zoom: 1,
      selectedId: "",
      related: new Set(),
      compact: true,
    });
    const series = (option.series as Record<string, unknown>[])[0];
    expect(series.symbolSize).toEqual(IP_TOPOLOGY_COMPACT_NODE_SIZE);
    expect((series.links as { label: { show: boolean } }[])[0].label.show).toBe(false);
  });
});
