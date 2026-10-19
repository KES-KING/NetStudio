"use client";
import { theme } from "../lib/theme";
import { useMemo, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import type { PhysicalPort, Projection } from "../lib/contracts";
import { formatTime, sampleForPort } from "../lib/metrics";
import { Chart, Empty } from "./OperationSummary";

const relations = {
  l3: "L3 / IP",
  l2: "L2 komşuluk",
  physical: "Fiziksel bağlantı",
};
export function IPTopology({
  row,
  port,
}: {
  row: Projection;
  port?: PhysicalPort;
}) {
  const [selectedId, setSelectedId] = useState(""),
    [zoom, setZoom] = useState(1),
    [revision, setRevision] = useState(0);
  const [scope, setScope] = useState("all");
  const related = useMemo(
    () =>
      new Set(
        port
          ? sampleForPort(row, port).map((s) => `interface:${s.interface_id}`)
          : [],
      ),
    [row, port],
  );
  const nodes = useMemo(() => {
    if (scope !== "port" || !port) return row.topology.nodes;
    const ids = new Set(related);
    row.topology.links.forEach((link) => {
      if (related.has(link.source)) ids.add(link.target);
    });
    return row.topology.nodes.filter((node) => ids.has(node.id));
  }, [scope, port, related, row.topology]);
  const selected = nodes.find((n) => n.id === selectedId);
  const option = useMemo<EChartsCoreOption>(() => {
    const groups = ["interface", "subnet", "neighbor"].map((kind) =>
      nodes.filter((n) => n.kind === kind),
    );
    const nodeIds = new Set(nodes.map((n) => n.id));
    return {
      tooltip: { renderMode: "richText", formatter: "{b}" },
      series: [
        {
          id: `${row.device.id}:ip-topology`,
          type: "graph",
          layout: "none",
          roam: true,
          zoom,
          scaleLimit: { min: 0.4, max: 3 },
          symbol: "rect",
          symbolSize: [122, 36],
          left: 80,
          right: 80,
          top: 38,
          bottom: 38,
          data: groups.flatMap((group, col) =>
            group.map((n, index) => ({
              id: n.id,
              name: n.name,
              x: col * 260,
              y: (index - (group.length - 1) / 2) * 140,
              itemStyle: {
                color:
                  selectedId === n.id
                    ? theme["accent"]
                    : related.has(n.id)
                      ? theme["selected"]
                      : theme["secondary"],
                borderColor: related.has(n.id)
                  ? theme["accent"]
                  : theme["node-border"],
                borderWidth: related.has(n.id) ? 2 : 1,
              },
              label: {
                show: true,
                color: selectedId === n.id ? theme["surface"] : theme["text"],
                fontSize: 10,
                width: 116,
                overflow: "truncate",
              },
            })),
          ),
          links: row.topology.links
            .filter((l) => nodeIds.has(l.source) && nodeIds.has(l.target))
            .map((l) => ({
              ...l,
              label: {
                show: true,
                formatter: relations[l.relation],
                fontSize: 9,
                color: theme["muted"],
              },
              lineStyle: {
                color: related.has(l.source) ? theme["accent"] : theme["down"],
                width: 1.5,
                type: l.relation === "physical" ? "solid" : "dashed",
              },
            })),
          emphasis: { focus: "adjacency" },
          lineStyle: { curveness: 0.05 },
        },
      ],
    };
  }, [nodes, row, zoom, selectedId, related]);
  return (
    <section className="topology-panel panel">
      <div className="panel-heading">
        <h2>IP topolojisi</h2>
        <div className="small-actions">
          <button
            onClick={() => setZoom(Math.min(3, zoom + 0.25))}
            aria-label="Topolojiyi yakınlaştır"
          >
            +
          </button>
          <button
            onClick={() => setZoom(Math.max(0.4, zoom - 0.25))}
            aria-label="Topolojiyi uzaklaştır"
          >
            −
          </button>
          <button
            onClick={() => {
              setZoom(1);
              setRevision((v) => v + 1);
            }}
          >
            Sıfırla
          </button>
        </div>
      </div>
      {!!row.topology.nodes.length && (
        <div className="topology-controls">
          <label>
            Düğüm seç
            <select
              value={selected?.id ?? ""}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              <option value="">Bir düğüm seçin</option>
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name} · {n.detail}
                </option>
              ))}
            </select>
          </label>
          {port && (
            <label>
              Kapsam
              <select value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="all">Tüm ilişkiler</option>
                <option value="port">Seçili port</option>
              </select>
            </label>
          )}
        </div>
      )}
      {nodes.length ? (
        <div
          className="topology-scroll"
          tabIndex={0}
          aria-label="Kaydırılabilir topoloji görünümü"
        >
          <Chart
            key={`${row.device.id}-${revision}`}
            className="topology-chart"
            option={option}
            label="Doğrulanmış IP alt ağları ve türü belirtilmiş komşu ilişkileri. Düğüm seçimi için açılır listeyi de kullanabilirsiniz."
            onSelect={setSelectedId}
          />
        </div>
      ) : (
        <Empty text="Bu kapsamda doğrulanmış IP veya komşuluk ilişkisi yok." />
      )}
      {selected && (
        <div className="topology-selection">
          <strong>{selected.name}</strong>
          <p className="mono">{selected.detail}</p>
          {selected.vrf && <p>VRF: {selected.vrf}</p>}
          {selected.vlan != null && <p>VLAN: {selected.vlan}</p>}
        </div>
      )}
      <p className="source-note">
        L3: atanmış IP / alt ağ · L2 ve fiziksel: açık kanıtlı komşu kaydı.
        Yönetim IP’sinden bağlantı üretilmez.
        <br />
        Gözlem: {formatTime(row.topology.observed_at)} ·{" "}
        {row.topology.source ?? "Kaynak yok"}
      </p>
    </section>
  );
}
