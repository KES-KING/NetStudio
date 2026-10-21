"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import {
  elbowPath, endpointLabels, endpointPosition, endpointsForCanvas, interfaceLabel, movePlacement, moveZone, portLabel, reachLabels,
  type NetworkDevice, type NetworkGraph, type Placement, type Selection, type TopologyBoard,
} from "../../lib/topology";

export function NetworkSymbol({ computer = false }: { computer?: boolean }) {
  return computer ? <g fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="-19" y="-16" width="38" height="26" /><path d="M -7 17 H 7 M 0 10 V 17" />
  </g> : <g fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="-43" y="-14" width="86" height="28" /><path d="M -30 -4 H 25 l -5 -5 M 30 4 H -25 l 5 5" />
  </g>;
}

type Props = {
  graph: NetworkGraph; devices: NetworkDevice[]; board: TopologyBoard; positions: Map<string, Placement>;
  selection: Selection; select: (value: Selection) => void; change: (value: TopologyBoard) => void;
  query: string; focus: { id: string; sequence: number } | null;
  detailed: boolean; setDetailed: (value: boolean) => void;
};
type Drag = { kind: "device" | "zone" | "pan"; id: string; startX: number; startY: number; dx: number; dy: number };
const short = (text: string, size = 25) => text.length > size ? `${text.slice(0, size - 1)}…` : text;

export default function TopologyCanvas({ graph, devices, board, positions, selection, select, change, query, focus, detailed, setDetailed }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const frame = useRef<number | null>(null);
  const drag = useRef<Drag | null>(null);
  const [preview, setPreview] = useState<Drag | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const [mode, setMode] = useState<"select" | "move">("select");
  const [viewport, setViewport] = useState({ width: 800, height: 650 });
  useEffect(() => {
    const node = svg.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setViewport({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(node);
    return () => { observer.disconnect(); if (frame.current != null) cancelAnimationFrame(frame.current); };
  }, []);
  const lastFocus = useRef(-1);
  useEffect(() => {
    if (!focus || focus.sequence === lastFocus.current) return;
    const p = positions.get(focus.id);
    if (!p) return;
    // Camera synchronization is independent from persisted node coordinates.
    const handle = requestAnimationFrame(() => { lastFocus.current = focus.sequence; setView({ x: viewport.width / 2 - p.x, y: viewport.height / 2 - p.y, scale: 1 }); });
    return () => cancelAnimationFrame(handle);
  }, [focus, positions, viewport]);

  function point(id: string): Placement {
    const p = positions.get(id)!;
    const moving = preview?.kind === "device" && preview.id === id || preview?.kind === "zone" && p.zone_id === preview.id;
    return moving && preview ? { ...p, x: p.x + preview.dx / view.scale, y: p.y + preview.dy / view.scale } : p;
  }
  function zoom(delta: number) {
    setView((v) => {
      const scale = Math.min(1.8, Math.max(0.4, v.scale + delta)), ratio = scale / v.scale;
      return { scale, x: viewport.width / 2 - (viewport.width / 2 - v.x) * ratio, y: viewport.height / 2 - (viewport.height / 2 - v.y) * ratio };
    });
  }
  function center() {
    const target = selection?.kind === "device" ? selection.id : selection?.kind === "endpoint" || selection?.kind === "neighbor" ? selection.deviceId : devices[0]?.id;
    const p = target ? positions.get(target) : null;
    setView(p ? { x: viewport.width / 2 - p.x, y: viewport.height / 2 - p.y, scale: 1 } : { x: 0, y: 0, scale: 1 });
  }
  function start(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0 || !event.isPrimary) return;
    const target = (event.target as Element).closest<SVGGElement>("[data-drag-kind]");
    if (target) select({ kind: target.dataset.dragKind as "device" | "zone", id: target.dataset.id! });
    if (event.pointerType === "touch" && mode === "select") return;
    if ((event.target as Element).closest("[data-select-only]")) return;
    drag.current = { kind: (target?.dataset.dragKind as "device" | "zone") ?? "pan", id: target?.dataset.id ?? "", startX: event.clientX, startY: event.clientY, dx: 0, dy: 0 };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    if (!drag.current) return;
    drag.current = { ...drag.current, dx: event.clientX - drag.current.startX, dy: event.clientY - drag.current.startY };
    if (frame.current == null) frame.current = requestAnimationFrame(() => { setPreview(drag.current ? { ...drag.current } : null); frame.current = null; });
  }
  function place(id: string, x: number, y: number) {
    x = Math.max(100, Math.min(25900, Math.round(x / 10) * 10));
    y = Math.max(100, Math.min(25900, Math.round(y / 10) * 10));
    const zone = [...board.zones].reverse().find((z) => x >= z.x + 90 && x <= z.x + z.width - 90 && y >= z.y + 90 && y <= z.y + z.height - 90);
    change(movePlacement(board, { device_id: id, x, y, zone_id: zone?.id ?? null }));
  }
  function end(event: PointerEvent<SVGSVGElement>, cancel = false) {
    const current = drag.current;
    drag.current = null;
    if (frame.current != null) { cancelAnimationFrame(frame.current); frame.current = null; }
    setPreview(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (!current || cancel) return;
    const dx = event.clientX - current.startX, dy = event.clientY - current.startY;
    if (Math.abs(dx) + Math.abs(dy) < 5) { if (current.kind === "pan") select(null); return; }
    if (current.kind === "pan") setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
    else if (current.kind === "device") { const p = positions.get(current.id)!; place(current.id, p.x + dx / view.scale, p.y + dy / view.scale); }
    else {
      const z = board.zones.find((z) => z.id === current.id)!;
      change(moveZone(board, z, Math.max(0, Math.min(20000, Math.round((z.x + dx / view.scale) / 10) * 10)), Math.max(0, Math.min(20000, Math.round((z.y + dy / view.scale) / 10) * 10))));
    }
  }
  function keyboard(event: KeyboardEvent<SVGGElement>, kind: "device" | "zone", id: string) {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select({ kind, id }); return; }
    const steps: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
    const step = steps[event.key];
    if (!step) return;
    event.preventDefault(); event.stopPropagation();
    if (kind === "device") { const p = positions.get(id)!; place(id, p.x + step[0], p.y + step[1]); }
    else { const z = board.zones.find((z) => z.id === id)!; change(moveZone(board, z, Math.max(0, Math.min(20000, z.x + step[0])), Math.max(0, Math.min(20000, z.y + step[1])))); }
  }
  const ids = new Set(devices.map((d) => d.id));
  const deviceMap = new Map(devices.map((d) => [d.id, d]));
  const compact = viewport.width < 500;
  const edgeGroups = new Map<string, string[]>();
  for (const link of [...board.links.map((l) => ({ ...l, key: `manual:${l.id}` })), ...graph.links.map((l) => ({ ...l, key: `observed:${l.id}` }))]) {
    const pair = JSON.stringify([link.source_device_id, link.target_device_id].sort());
    edgeGroups.set(pair, [...(edgeGroups.get(pair) ?? []), link.key]);
  }
  const panX = preview?.kind === "pan" ? preview.dx : 0, panY = preview?.kind === "pan" ? preview.dy : 0;

  function connection(id: string, sourceId: string, targetId: string, label: string, kind: "manual" | "observed", relation: string, stale = false) {
    const a = point(sourceId), b = point(targetId), left = b.x >= a.x;
    const group = edgeGroups.get(JSON.stringify([sourceId, targetId].sort())) ?? [];
    const lane = (group.indexOf(`${kind}:${id}`) - (group.length - 1) / 2) * 20;
    const ax = a.x + (left ? 94 : -94), bx = b.x + (left ? -94 : 94), mid = (ax + bx) / 2;
    const path = `M ${ax} ${a.y + lane} H ${mid} V ${b.y + lane} H ${bx}`;
    const selected = selection?.kind === kind && selection.id === id;
    return <g key={`${kind}:${id}`} className={`topology-edge ${relation} ${stale ? "stale" : ""} ${selected ? "selected" : ""}`}
      data-select-only="true" role="button" tabIndex={0} aria-label={`${label} — bağlantı ayrıntıları`}
      onClick={() => select({ kind, id })} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select({ kind, id }); } }}>
      <title>{label}</title><path className="edge-hit" d={path} /><path className="edge-line" d={path} />
      <text x={mid} y={(a.y + b.y) / 2 + lane - 6} textAnchor="middle">{short(label, 35)}</text>
    </g>;
  }

  return <div className="topology-canvas-wrap">
    <div className="topology-camera">
      <button aria-label="Topolojiyi yakınlaştır" onClick={() => zoom(.15)}>+</button>
      <button aria-label="Topolojiyi uzaklaştır" onClick={() => zoom(-.15)}>−</button>
      <button onClick={center}>Ortala</button>
      <button aria-pressed={mode === "move"} onClick={() => setMode(mode === "select" ? "move" : "select")}>Taşıma modu</button>
      <button className="topology-detail-switch" role="switch" aria-checked={detailed} aria-label="Detaylandır" onClick={() => setDetailed(!detailed)}>
        <span>Detaylandır</span><span className="switch-state" aria-hidden="true">{detailed ? "Açık" : "Kapalı"}</span>
      </button>
      <output aria-label="Yakınlaştırma oranı">{Math.round(view.scale * 100)}%</output>
    </div>
    <svg ref={svg} className={`network-canvas ${mode === "move" ? "move-mode" : ""}`} role="group" aria-label="Etkileşimli topoloji çalışma alanı"
      tabIndex={0} onPointerDown={start} onPointerMove={move} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e, true)}
      onKeyDown={(e) => { if (e.key === "Escape") { drag.current = null; setPreview(null); select(null); } }}>
      <defs><pattern id="topology-hatch" width="12" height="12" patternUnits="userSpaceOnUse"><path d="M -3 3 L 3 -3 M 0 12 L 12 0 M 9 15 L 15 9" /></pattern></defs>
      <rect width="100%" height="100%" fill="url(#topology-hatch)" />
      <g transform={`translate(${view.x + panX} ${view.y + panY}) scale(${view.scale})`}>
        {board.zones.map((z) => {
          const moving = preview?.kind === "zone" && preview.id === z.id;
          const dx = moving ? preview.dx / view.scale : 0, dy = moving ? preview.dy / view.scale : 0;
          return <g key={z.id} transform={`translate(${z.x + dx} ${z.y + dy})`} className={`network-zone ${z.tone} ${selection?.kind === "zone" && selection.id === z.id ? "selected" : ""}`}>
            <rect width={z.width} height={z.height} className="zone-fill" pointerEvents="none" />
            <g data-drag-kind="zone" data-id={z.id} role="button" tabIndex={0} aria-label={`Zone: ${z.name}. Taşımak için ok tuşları.`} onKeyDown={(e) => keyboard(e, "zone", z.id)}>
              <rect width={z.width} height={36} className="zone-heading" /><text x={Math.max(14, Math.min(z.width - 150, -(view.x + panX) / view.scale - z.x - dx + 14))} y={24}>{z.name}</text>
              <text x={z.width - 14} y={24} textAnchor="end" className="zone-count">{board.placements.filter((p) => p.zone_id === z.id && ids.has(p.device_id)).length} atanmış cihaz</text>
            </g>
          </g>;
        })}
        {board.links.filter((l) => ids.has(l.source_device_id) && ids.has(l.target_device_id)).map((l) => connection(l.id, l.source_device_id, l.target_device_id,
          `${portLabel(deviceMap.get(l.source_device_id)!, l.source_port_id)} ↔ ${portLabel(deviceMap.get(l.target_device_id)!, l.target_port_id)} · Elle çizilen`, "manual", "manual"))}
        {graph.links.filter((l) => ids.has(l.source_device_id) && ids.has(l.target_device_id)).map((l) => connection(l.id, l.source_device_id, l.target_device_id,
          `${interfaceLabel(deviceMap.get(l.source_device_id)!, l.source_interface_id)} ↔ ${interfaceLabel(deviceMap.get(l.target_device_id)!, l.target_interface_id)}`, "observed", l.relation, l.data_state !== "current"))}
        {devices.map((device) => {
          const p = point(device.id), active = selection?.kind === "device" && selection.id === device.id;
          const endpoints = endpointsForCanvas(device, query, selection?.kind === "endpoint" && selection.deviceId === device.id ? selection.id : undefined, detailed);
          return <g key={device.id}>
            {endpoints.map((e, index) => {
              const { x, y } = endpointPosition(p, index, compact, detailed);
              const selected = selection?.kind === "endpoint" && selection.deviceId === device.id && selection.id === e.id;
              return <g key={e.id}>
                <g className={`topology-edge endpoint ${device.data_state !== "current" || e.state === "stale" || e.resolution?.status === "stale" ? "stale" : ""}`}>
                  <path className="edge-line" d={elbowPath({ x: p.x, y: p.y + (y < p.y ? -17 : 84) }, { x, y: y < p.y ? y + 65 : y - 22 })} />
                  <text x={(p.x + x) / 2 + 7} y={(p.y + y) / 2 + (y < p.y ? 10 : 40)}>{short(interfaceLabel(device, e.interface_id), 20)}</text>
                </g>
                <g data-select-only="true" transform={`translate(${x} ${y})`} className={`network-endpoint ${selected ? "selected" : ""}`}
                  tabIndex={0} role="button" aria-label={`${e.addresses.join(", ") || "IP bilinmiyor"} · ${e.mac} · ${interfaceLabel(device, e.interface_id)}`}
                  onClick={() => select({ kind: "endpoint", id: e.id, deviceId: device.id })}
                  onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select({ kind: "endpoint", id: e.id, deviceId: device.id }); } }}>
                  <title>{e.mac} · {e.addresses.join(", ") || "IP bilinmiyor"} · {e.discovery.toUpperCase()}</title>
                  <rect x={compact ? -76 : -95} y={-23} width={compact ? 152 : 190} height={101} className="node-hit" />
                  <NetworkSymbol computer /><text y={36} textAnchor="middle">{short(e.addresses[0] ?? "IP bilinmiyor", compact ? 20 : 27)}</text>
                  <text y={53} textAnchor="middle" className="node-mono">{e.mac}</text>
                  <text y={70} textAnchor="middle" className="node-meta">{e.resolution?.status === "stale" ? "Eski gözlem" : e.resolution?.status === "ambiguous" ? "IP belirsiz" : e.discovery.toUpperCase()} · {e.vlan ? `VLAN ${e.vlan}` : "VLAN bilinmiyor"}</text>
                </g>
              </g>;
            })}
            <g transform={`translate(${p.x} ${p.y})`} className={`network-device ${active ? "selected" : ""}`} data-drag-kind="device" data-id={device.id}
              tabIndex={0} role="button" aria-label={`${device.name} · ${device.management_address}. Taşımak için ok tuşları.`} onKeyDown={(e) => keyboard(e, "device", device.id)}>
              <title>{device.name} · {device.site} · {reachLabels[device.reachability]}</title>
              <rect x={-100} y={-24} width={200} height={126} className="node-hit" />
              <NetworkSymbol /><text y={35} textAnchor="middle" className="node-title">{short(device.name, 24)}</text>
              <text y={54} textAnchor="middle" className="node-mono">{device.management_address}</text>
              <text y={73} textAnchor="middle" className={`node-meta ${device.reachability}`}>{reachLabels[device.reachability]}</text>
              <text y={91} textAnchor="middle" className="node-meta">{["ok", "partial"].includes(device.endpoints.status) ? `${device.endpoints.entries.length} uç gözlemi${device.endpoints.entries.length > endpoints.length ? ` · ${endpoints.length} çiziliyor` : detailed && device.endpoints.entries.length > 0 ? " · tamamı çiziliyor" : ""}` : endpointLabels[device.endpoints.status]}</text>
            </g>
          </g>;
        })}
      </g>
    </svg>
    {!devices.length && <p className="topology-canvas-empty">Bu kapsamda cihaz yok. Envantere cihaz ekleyin veya filtreyi temizleyin.</p>}
    <div className="topology-legend"><span className="physical">Fiziksel kanıt</span><span className="l2">L2 komşuluk</span><span className="manual">Elle çizilen</span><span className="endpoint">MAC / IP gözlemi</span></div>
    <p className="source-note">MAC öğrenimi doğrudan kablo bağlantısı kanıtı değildir. Bilgisayar sembolü uç kaydını temsil eder; cihaz türü doğrulanmış değildir. Soluk çizgi: eski / geçersiz güncellik.</p>
  </div>;
}
