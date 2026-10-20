"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { recordActivity } from "../lib/activity";
import type { PhysicalPort, Projection } from "../lib/contracts";
import { IP_NODE_LIMIT, linkId, nodeKindLabels, portTopologyIds, relationLabels, topologySubset } from "../lib/ip-topology";
import { formatTime, stateLabels } from "../lib/metrics";
import { IPTopologyCanvas } from "./IPTopologyCanvas";
import { Empty } from "./OperationSummary";

export function IPTopology({ row, port }: { row: Projection; port?: PhysicalPort }) {
  const [selectedId, setSelectedId] = useState("");
  const [edgeId, setEdgeId] = useState("");
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("all");
  const [focus, setFocus] = useState({ id: "", sequence: 0 });
  const related = useMemo(() => portTopologyIds(row, port?.id), [row, port?.id]);
  const scoped = useMemo(() => topologySubset(row.topology.nodes, row.topology.links, scope === "port" && port ? related : undefined), [row.topology, scope, port, related]);
  const matches = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("tr-TR");
    return term ? topologySubset(scoped, row.topology.links, new Set(scoped.filter((n) =>
      `${n.name} ${n.detail} ${n.vrf ?? ""} ${n.vlan ?? ""}`.toLocaleLowerCase("tr-TR").includes(term)).map((n) => n.id))) : scoped;
  }, [query, scoped, row.topology.links]);
  // A selected result beyond the rendering budget remains accessible through the list.
  const nodes = useMemo(() => {
    if (matches.length <= IP_NODE_LIMIT) return matches;
    const selected = matches.find((n) => n.id === selectedId);
    const chosen = selected ? [selected, ...topologySubset(matches, row.topology.links, new Set([selectedId])).filter((n) => n.id !== selectedId)] : [];
    const ids = new Set(chosen.map((n) => n.id));
    return [...chosen, ...matches.filter((n) => !ids.has(n.id))].slice(0, IP_NODE_LIMIT);
  }, [matches, selectedId, row.topology.links]);
  const links = useMemo(() => {
    const ids = new Set(nodes.map((n) => n.id));
    return [...new Map(row.topology.links.filter((l) => ids.has(l.source) && ids.has(l.target)).map((l) => [linkId(l), l])).values()];
  }, [nodes, row.topology.links]);
  const selected = nodes.find((n) => n.id === selectedId);
  const edge = links.find((l) => linkId(l) === edgeId);
  function selectNode(id: string, center = false) {
    setSelectedId(id); setEdgeId("");
    if (center && id) setFocus((f) => ({ id, sequence: f.sequence + 1 }));
    if (id) recordActivity({ action: "topology.select", page: "device", device_id: row.device.id, node_id: id });
  }
  const name = (id: string) => nodes.find((n) => n.id === id)?.name ?? id;
  return <section className="topology-panel panel device-ip-panel" aria-label="Cihaz IP topolojisi">
    <div className="panel-heading">
      <div><h2>IP topolojisi</h2><p>{row.topology.nodes.length} düğüm · {row.topology.links.length} ilişki · {stateLabels[row.data_state]}</p></div>
      <Link href="/topology" className="button-link">Ağ topolojisini aç</Link>
    </div>
    {!!row.topology.nodes.length && <div className="topology-controls">
      <label>Topolojide ara<input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Arayüz, IP, VRF veya VLAN" /></label>
      <label>Düğüm seç<select value={selected?.id ?? ""} onChange={(e) => selectNode(e.target.value, true)}>
        <option value="">Bir düğüm seçin</option>
        {matches.map((n) => <option key={n.id} value={n.id}>{n.name} · {n.detail}</option>)}
      </select></label>
      {port && <label>Kapsam<select value={scope} onChange={(e) => { setScope(e.target.value); selectNode(""); }}>
        <option value="all">Tüm ilişkiler</option><option value="port">Seçili port · {port.label}</option>
      </select></label>}
    </div>}
    {nodes.length ? <div className="device-ip-workspace">
      <div className="device-ip-drawing">
        <IPTopologyCanvas key={`${scope === "port" ? port?.id : "all"}:${query}`} nodes={nodes} links={links} selectedId={selected?.id ?? ""} selectedEdge={edge ? edgeId : ""}
          related={related} focus={focus} onNode={selectNode} onEdge={(id) => { setEdgeId(id); setSelectedId(""); }}
          onClear={() => { setSelectedId(""); setEdgeId(""); }} />
        <div className="device-topology-legend" aria-label="Topoloji ilişki türleri">
          <span className="l3">L3 / IP</span><span className="l2">L2 komşuluk</span><span className="physical">Fiziksel bağlantı</span>
        </div>
        <p className="source-note">{nodes.length} / {matches.length} düğüm gösteriliyor{nodes.length < matches.length ? " · Diğer düğümler için arayın veya listeden seçin." : "."} Sürükleyerek veya odaklanıp ok tuşlarıyla kaydırın.</p>
      </div>
      <aside className="device-ip-inspector" aria-label="Topoloji seçim ayrıntıları">
        <h3>Seçim ayrıntıları</h3>
        {edge ? <>
          <strong>{relationLabels[edge.relation]}</strong>
          <p>{name(edge.source)} ↔ {name(edge.target)}</p>
          <dl className="device-facts"><div><dt>Bağlantı kanıtı</dt><dd>{edge.evidence || "Kanıt açıklaması yok"}</dd></div></dl>
          <button onClick={() => selectNode(edge.source, true)}>Kaynak düğüme odaklan</button>
          <button onClick={() => selectNode(edge.target, true)}>Hedef düğüme odaklan</button>
        </> : selected ? <>
          <strong>{selected.name}</strong>
          <dl className="device-facts">
            <div><dt>Tür</dt><dd>{nodeKindLabels[selected.kind] ?? selected.kind}</dd></div>
            <div><dt>Adres / açıklama</dt><dd className="mono">{selected.detail || "Veri yok"}</dd></div>
            <div><dt>VRF</dt><dd>{selected.vrf || "Bildirilmedi"}</dd></div>
            <div><dt>VLAN</dt><dd>{selected.vlan ?? "Bildirilmedi"}</dd></div>
          </dl>
          <h4>İlişkiler</h4>
          <ul className="device-ip-relations">{links.filter((l) => l.source === selected.id || l.target === selected.id).map((l) =>
            <li key={linkId(l)}><button onClick={() => setEdgeId(linkId(l))}>{relationLabels[l.relation]} · {name(l.source === selected.id ? l.target : l.source)}</button></li>)}</ul>
        </> : <><strong>İlişkileri inceleyin</strong><p>Bir düğüm veya bağlantı çizgisi seçin. Adres, VLAN, VRF ve bağlantı kanıtı burada gösterilir.</p>
          <dl className="device-facts">{["interface", "subnet", "neighbor"].map((kind) => <div key={kind}><dt>{nodeKindLabels[kind]}</dt><dd>{scoped.filter((n) => n.kind === kind).length}</dd></div>)}</dl></>}
        <p className="source-note">Gözlem: {formatTime(row.topology.observed_at)}<br />{row.topology.source ?? "Kaynak yok"}</p>
      </aside>
    </div> : <Empty text={query ? "Aramanızla eşleşen düğüm yok. Aramayı temizleyerek tekrar deneyin." : "Bu kapsamda doğrulanmış IP veya komşuluk ilişkisi yok."} />}
    <p className="source-note">L3: atanmış IP / alt ağ · L2 ve fiziksel: açık kanıtlı komşu kaydı. Yönetim IP’sinden bağlantı üretilmez. {row.data_state !== "current" && "Gösterilen ilişkiler son bilinen gözlemdir; güncellik doğrulanmıyor."}</p>
  </section>;
}
