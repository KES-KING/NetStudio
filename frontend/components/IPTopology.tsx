"use client";
import { recordActivity } from "../lib/activity";
import { useEffect, useMemo, useRef, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import type { PhysicalPort, Projection } from "../lib/contracts";
import { ipTopologyOption, IP_TOPOLOGY_ZOOM } from "../lib/ip-topology";
import { formatTime, sampleForPort } from "../lib/metrics";
import { Chart, Empty } from "./OperationSummary";

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
  const stage = useRef<HTMLDivElement>(null);
  const [stageWidth, setStageWidth] = useState(0);
  function selectNode(id: string) {
    setSelectedId(id);
    if (id) recordActivity({ action: "topology.select", page: "device", device_id: row.device.id, node_id: id });
  }
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
  const activeSelectedId = selected?.id ?? "";
  const compact = stageWidth > 0 && stageWidth < 520;
  useEffect(() => {
    const element = stage.current;
    if (!element) return;
    const update = () => {
      const width = Math.round(element.getBoundingClientRect().width);
      setStageWidth((current) => current === width ? current : width);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [nodes.length]);
  const option = useMemo<EChartsCoreOption>(() => {
    return ipTopologyOption({
      deviceId: row.device.id,
      nodes,
      links: row.topology.links,
      zoom,
      selectedId: activeSelectedId,
      related,
      compact,
    });
  }, [activeSelectedId, compact, nodes, related, row.device.id, row.topology.links, zoom]);
  return (
    <section className="topology-panel panel">
      <div className="panel-heading">
        <h2>IP topolojisi</h2>
        <span>Arayüz · alt ağ · komşu</span>
      </div>
      {!!row.topology.nodes.length && (
        <div className="topology-controls">
          <label>
            Düğüm seç
            <select
              value={activeSelectedId}
              onChange={(e) => selectNode(e.target.value)}
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
        <div className="device-topology-stage" ref={stage} data-layout={compact ? "compact" : "wide"}>
          <div className="device-topology-camera" aria-label="Topoloji görünüm kontrolleri">
            <button
              onClick={() => setZoom(Math.min(IP_TOPOLOGY_ZOOM.max, zoom + IP_TOPOLOGY_ZOOM.step))}
              aria-label="Topolojiyi yakınlaştır"
            >
              +
            </button>
            <button
              onClick={() => setZoom(Math.max(IP_TOPOLOGY_ZOOM.min, zoom - IP_TOPOLOGY_ZOOM.step))}
              aria-label="Topolojiyi uzaklaştır"
            >
              −
            </button>
            <button
              onClick={() => {
                setZoom(1);
                setRevision((value) => value + 1);
              }}
            >
              Ortala ve sıfırla
            </button>
            <span className="device-topology-zoom" aria-label="Yakınlaştırma oranı">
              {Math.round(zoom * 100)}%
            </span>
          </div>
          <div className="topology-scroll">
            <Chart
              key={`${row.device.id}-${revision}`}
              className="topology-chart"
              option={option}
              label="Doğrulanmış IP alt ağları ve türü belirtilmiş komşu ilişkileri. Düğümler sabit ölçülüdür; görünümü kaydırabilir veya yakınlaştırabilirsiniz. Düğüm seçimi için açılır listeyi de kullanabilirsiniz."
              onSelect={selectNode}
            />
          </div>
          <div className="device-topology-legend" aria-label="Topoloji ilişki türleri">
            <span className="l3">L3 / IP</span>
            <span className="l2">L2 komşuluk</span>
            <span className="physical">Fiziksel bağlantı</span>
          </div>
        </div>
      ) : (
        <Empty text="Bu kapsamda doğrulanmış IP veya komşuluk ilişkisi yok." />
      )}
      {selected ? (
        <div className="topology-selection">
          <strong>{selected.name}</strong>
          <p className="mono">{selected.detail}</p>
          {selected.vrf && <p>VRF: {selected.vrf}</p>}
          {selected.vlan != null && <p>VLAN: {selected.vlan}</p>}
        </div>
      ) : null}
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
