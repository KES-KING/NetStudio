"use client";
import { useEffect, useId, useMemo, useRef, useState, type PointerEvent } from "react";
import type { TopologyNode } from "../lib/contracts";
import { IP_TOPOLOGY_ZOOM, layoutIPTopologyNodes, linkId, nodeKindLabels, relationLabels, routeIPLink, type IPLink } from "../lib/ip-topology";

type Props = {
  nodes: TopologyNode[]; links: IPLink[]; selectedId: string; selectedEdge: string;
  related: Set<string>; focus: { id: string; sequence: number };
  onNode: (id: string) => void; onEdge: (id: string) => void; onClear: () => void;
};
const short = (text: string, limit: number) => text.length > limit ? `${text.slice(0, limit - 1)}…` : text;

export function IPTopologyCanvas({ nodes, links, selectedId, selectedEdge, related, focus, onNode, onEdge, onClear }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const pattern = useId();
  const [width, setWidth] = useState(320);
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const [moveMode, setMoveMode] = useState(false);
  const drag = useRef<{ x: number; y: number; dx: number; dy: number } | null>(null);
  const frame = useRef<number | null>(null);
  const [preview, setPreview] = useState({ x: 0, y: 0 });
  const layout = useMemo(() => layoutIPTopologyNodes(nodes, width), [nodes, width]);
  const positions = useMemo(() => new Map(layout.nodes.map((n) => [n.id, n])), [layout]);
  const height = 340;
  const base = { x: Math.max(0, (width - layout.width) / 2), y: Math.max(0, (height - layout.height) / 2) };
  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(element);
    return () => { observer.disconnect(); if (frame.current != null) cancelAnimationFrame(frame.current); };
  }, []);
  const lastFocus = useRef(focus.sequence);
  useEffect(() => {
    if (lastFocus.current === focus.sequence) return;
    const target = positions.get(focus.id);
    if (!target) return;
    const handle = requestAnimationFrame(() => {
      lastFocus.current = focus.sequence;
      // Small graphs stay wholly visible; focusing a node must not clip its peers.
      setView(layout.width <= width && layout.height <= height
        ? { x: 0, y: 0, scale: 1 }
        : { x: width / 2 - target.x - base.x, y: height / 2 - target.y - base.y, scale: 1 });
    });
    return () => cancelAnimationFrame(handle);
  }, [focus, positions, width, base.x, base.y, layout.width, layout.height]);
  function zoom(delta: number) {
    setView((v) => {
      const scale = Math.max(IP_TOPOLOGY_ZOOM.min, Math.min(IP_TOPOLOGY_ZOOM.max, v.scale + delta));
      const ratio = scale / v.scale;
      return { scale, x: (width / 2 - base.x) * (1 - ratio) + v.x * ratio, y: (height / 2 - base.y) * (1 - ratio) + v.y * ratio };
    });
  }
  function start(e: PointerEvent<SVGSVGElement>) {
    if (e.button !== 0 || !e.isPrimary || (e.target as Element).closest("[data-selectable]") || (e.pointerType === "touch" && !moveMode)) return;
    drag.current = { x: e.clientX, y: e.clientY, dx: 0, dy: 0 };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent<SVGSVGElement>) {
    if (!drag.current) return;
    drag.current.dx = e.clientX - drag.current.x; drag.current.dy = e.clientY - drag.current.y;
    if (frame.current == null) frame.current = requestAnimationFrame(() => {
      setPreview({ x: drag.current?.dx ?? 0, y: drag.current?.dy ?? 0 }); frame.current = null;
    });
  }
  function end(e: PointerEvent<SVGSVGElement>, cancel = false) {
    const current = drag.current; drag.current = null;
    if (frame.current != null) { cancelAnimationFrame(frame.current); frame.current = null; }
    setPreview({ x: 0, y: 0 });
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    if (!current || cancel) return;
    if (Math.abs(current.dx) + Math.abs(current.dy) < 5) onClear();
    else setView((v) => ({ ...v, x: v.x + current.dx, y: v.y + current.dy }));
  }
  const pairs = new Map<string, string[]>();
  for (const l of links) {
    const key = JSON.stringify([l.source, l.target].sort());
    pairs.set(key, [...(pairs.get(key) ?? []), linkId(l)]);
  }
  return <div className="device-topology-stage" data-layout={width < 520 ? "compact" : "wide"}>
    <div className="device-topology-camera" aria-label="Topoloji görünüm kontrolleri">
      <button onClick={() => zoom(.15)} aria-label="Topolojiyi yakınlaştır" disabled={view.scale >= IP_TOPOLOGY_ZOOM.max}>+</button>
      <button onClick={() => zoom(-.15)} aria-label="Topolojiyi uzaklaştır" disabled={view.scale <= IP_TOPOLOGY_ZOOM.min}>−</button>
      <button onClick={() => setView({ x: 0, y: 0, scale: 1 })}>Ortala ve sıfırla</button>
      <button aria-pressed={moveMode} onClick={() => setMoveMode(!moveMode)}>Taşıma modu</button>
      <output className="device-topology-zoom" aria-label="Yakınlaştırma oranı">{Math.round(view.scale * 100)}%</output>
    </div>
    <div className="topology-chart">
      <svg ref={svg} className={`device-ip-canvas ${moveMode ? "move-mode" : ""}`} role="group" tabIndex={0}
        aria-label="Cihazın arayüz, alt ağ ve komşuluk ilişkileri" onPointerDown={start} onPointerMove={move} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e, true)}
        onKeyDown={(e) => {
          if (e.key === "Escape") { onClear(); drag.current = null; setPreview({ x: 0, y: 0 }); return; }
          const step = { ArrowLeft: [30, 0], ArrowRight: [-30, 0], ArrowUp: [0, 30], ArrowDown: [0, -30] }[e.key];
          if (step) { e.preventDefault(); setView((v) => ({ ...v, x: v.x + step[0], y: v.y + step[1] })); }
        }}>
        <defs><pattern id={pattern} width="12" height="12" patternUnits="userSpaceOnUse"><path d="M -3 3 L 3 -3 M 0 12 L 12 0 M 9 15 L 15 9" /></pattern></defs>
        <rect width="100%" height="100%" fill={`url(#${pattern})`} />
        <g data-camera transform={`translate(${base.x + view.x + preview.x} ${base.y + view.y + preview.y}) scale(${view.scale})`}>
          {links.map((l) => {
            const a = positions.get(l.source), b = positions.get(l.target);
            if (!a || !b) return null;
            const id = linkId(l), group = pairs.get(JSON.stringify([l.source, l.target].sort()))!;
            const route = routeIPLink(a, b, layout.nodeWidth, group.indexOf(id) - (group.length - 1) / 2);
            return <g key={id} data-selectable className={`device-ip-edge ${l.relation} ${selectedEdge === id ? "selected" : ""}`} role="button" tabIndex={0}
              aria-label={`${a.name} ↔ ${b.name} · ${relationLabels[l.relation]} · bağlantı ayrıntıları`}
              onClick={() => onEdge(id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onEdge(id); } }}>
              <title>{l.evidence}</title><path className="edge-hit" d={route.path} /><path className="edge-line" d={route.path} />
              <text x={route.x} y={route.y - 6} textAnchor="middle">{l.relation === "physical" ? "Fiz." : l.relation.toUpperCase()}</text>
            </g>;
          })}
          {layout.nodes.map((n) => <g key={n.id} data-selectable data-node-id={n.id}
            transform={`translate(${n.x} ${n.y})`} className={`device-ip-node ${selectedId === n.id ? "selected" : ""} ${related.has(n.id) ? "related" : ""}`}
            tabIndex={0} role="button" aria-label={`${n.name} · ${nodeKindLabels[n.kind] ?? n.kind} · ${n.detail}`} aria-pressed={selectedId === n.id}
            onClick={() => onNode(n.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onNode(n.id); } }}>
            <title>{n.name} · {n.detail}</title>
            <rect className="node-hit" x={-layout.nodeWidth / 2} y={-30} width={layout.nodeWidth} height={60} />
            <text className="node-kind" y={-15} textAnchor="middle">{nodeKindLabels[n.kind] ?? n.kind}</text>
            <text className="node-title" y={2} textAnchor="middle">{short(n.name, Math.floor((layout.nodeWidth - 14) / 6.6))}</text>
            <text className="node-detail" y={19} textAnchor="middle">{short(n.detail || "Veri yok", Math.floor((layout.nodeWidth - 14) / 6))}</text>
          </g>)}
        </g>
      </svg>
    </div>
  </div>;
}
