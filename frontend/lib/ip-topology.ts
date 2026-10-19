import type { EChartsCoreOption } from "echarts/core";
import type { Projection, TopologyNode } from "./contracts";
import { theme } from "./theme";

const kindOrder = ["interface", "subnet", "neighbor"] as const;
const relationLabels = {
  l3: "L3 / IP",
  l2: "L2 komşuluk",
  physical: "Fiziksel bağlantı",
} as const;

export const IP_TOPOLOGY_NODE_SIZE = [116, 40] as const;
export const IP_TOPOLOGY_COMPACT_NODE_SIZE = [96, 38] as const;
export const IP_TOPOLOGY_ZOOM = { min: 0.7, max: 1.8, step: 0.15 } as const;

export function layoutIPTopologyNodes(nodes: TopologyNode[], compact = false) {
  if (compact) {
    const interfaces = nodes.filter((node) => node.kind === "interface");
    const targets = nodes.filter((node) => node.kind !== "interface");
    return [interfaces, targets].flatMap((group, column) =>
      group.map((node, index) => ({
        ...node,
        x: column * 180,
        y: (index - (group.length - 1) / 2) * 88,
      })),
    );
  }
  const groups = kindOrder
    .map((kind) => nodes.filter((node) => node.kind === kind))
    .filter((group) => group.length);
  return groups.flatMap((group, column) =>
    group.map((node, index) => ({
      ...node,
      x: column * 230,
      y: (index - (group.length - 1) / 2) * 88,
    })),
  );
}

export function ipTopologyOption({
  deviceId,
  nodes,
  links,
  zoom,
  selectedId,
  related,
  compact = false,
}: {
  deviceId: string;
  nodes: TopologyNode[];
  links: Projection["topology"]["links"];
  zoom: number;
  selectedId: string;
  related: ReadonlySet<string>;
  compact?: boolean;
}): EChartsCoreOption {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const baseNodeSize = compact ? IP_TOPOLOGY_COMPACT_NODE_SIZE : IP_TOPOLOGY_NODE_SIZE;
  const nodeSize = baseNodeSize.map((value) => value / zoom);
  const labelSize = (compact ? 9 : 10) / zoom;
  return {
    tooltip: {
      renderMode: "richText",
      formatter: (event: { data?: { name?: string; detail?: string; evidence?: string } }) => {
        const data = event.data;
        return [data?.name, data?.detail ?? data?.evidence].filter(Boolean).join("\n");
      },
    },
    series: [
      {
        id: `${deviceId}:ip-topology`,
        type: "graph",
        layout: "none",
        // Pointer/touch drag pans. Zoom stays controlled so labels and nodes
        // retain a predictable physical size instead of growing past the panel.
        roam: "move",
        zoom,
        scaleLimit: { min: IP_TOPOLOGY_ZOOM.min, max: IP_TOPOLOGY_ZOOM.max },
        // Keep nodes the same readable size while users pan/zoom the graph.
        nodeScaleRatio: 0,
        symbol: "rect",
        symbolSize: nodeSize,
        left: compact ? 52 : 70,
        right: compact ? 52 : 70,
        top: compact ? 38 : 46,
        bottom: compact ? 38 : 46,
        data: layoutIPTopologyNodes(nodes, compact).map((node) => ({
          ...node,
          itemStyle: {
            color:
              selectedId === node.id
                ? theme.accent
                : related.has(node.id)
                  ? theme.selected
                  : theme.surface,
            borderColor: related.has(node.id) ? theme.accent : theme["node-border"],
            borderWidth: (related.has(node.id) || selectedId === node.id ? 2 : 1) / zoom,
          },
          label: {
            show: true,
            color: selectedId === node.id ? theme.surface : theme.text,
            fontSize: labelSize,
            width: (compact ? 82 : 102) / zoom,
            overflow: "truncate",
          },
        })),
        links: links
          .filter((link) => nodeIds.has(link.source) && nodeIds.has(link.target))
          .map((link) => ({
            ...link,
            name: relationLabels[link.relation],
            label: {
              show: !compact,
              formatter: relationLabels[link.relation],
              fontSize: 9 / zoom,
              color: theme.muted,
              backgroundColor: theme.surface,
              padding: [2 / zoom, 3 / zoom],
            },
            lineStyle: {
              color: related.has(link.source) ? theme.accent : theme.down,
              width: (related.has(link.source) ? 2 : 1.25) / zoom,
              type: link.relation === "physical" ? "solid" : "dashed",
            },
          })),
        emphasis: { focus: "adjacency", scale: false },
        lineStyle: { curveness: 0.04 },
      },
    ],
  };
}
