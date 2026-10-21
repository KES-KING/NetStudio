"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { api, errorMessage } from "../../lib/api";
import { recordActivity } from "../../lib/activity";
import { formatTime } from "../../lib/metrics";
import { boardPayload, GRAPH_DEVICE_LIMIT, layoutPositions, matchesDevice, type NetworkGraph, type Selection, type TopologyBoard } from "../../lib/topology";
import { useSession } from "../ConsoleShell";
import { Dialog } from "../DeviceForms";
import TopologyCanvas from "./TopologyCanvas";
import TopologyInspector from "./TopologyInspector";
import { AddConnection, AddZone } from "./TopologyForms";

const graphPath = "/api/v1/topology", boardPath = "/api/v1/topology/board";

export default function TopologyWorkspace() {
  const session = useSession();
  const graph = useSWR<NetworkGraph>(graphPath, api, { refreshInterval: 15000 });
  const board = useSWR<TopologyBoard>(boardPath, api, { revalidateOnFocus: false, revalidateOnReconnect: false });
  if (!graph.data || !board.data) return <section><h1>Topoloji</h1>{graph.error || board.error ? <><p className="notice error" role="alert">{errorMessage(graph.error ?? board.error)}</p><button onClick={() => { void graph.mutate(); void board.mutate(); }}>Yeniden dene</button></> : <p role="status">Cihazlar ve kişisel yerleşim yükleniyor…</p>}</section>;
  return <Workspace key={session.user_id} graph={graph.data} initialBoard={board.data} graphError={graph.error} refresh={() => graph.mutate()} persisted={(value) => { void board.mutate(value, { revalidate: false }); }} />;
}

function Workspace({ graph, initialBoard, graphError, refresh, persisted }: { graph: NetworkGraph; initialBoard: TopologyBoard; graphError: unknown; refresh: () => Promise<unknown>; persisted: (board: TopologyBoard) => void }) {
  const params = useSearchParams();
  const [board, setBoard] = useState(initialBoard), [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false);
  const [selection, setSelection] = useState<Selection>(() => params.get("device") ? params.get("endpoint") ? { kind: "endpoint", id: params.get("endpoint")!, deviceId: params.get("device")! } : { kind: "device", id: params.get("device")! } : null);
  const [focus, setFocus] = useState<{ id: string; sequence: number } | null>({ id: params.get("device") ?? graph.devices[0]?.id ?? "", sequence: 0 });
  const [query, setQuery] = useState(""), [site, setSite] = useState(""), [zoneId, setZoneId] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [detailed, setDetailed] = useState(false);
  const [dialog, setDialog] = useState<"zone" | "connection" | "reload" | null>(null);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [baseIds] = useState(() => graph.devices.map((d) => d.id));
  const positions = useMemo(() => {
    const order = [...baseIds, ...graph.devices.filter((d) => !baseIds.includes(d.id)).map((d) => d.id)];
    return layoutPositions(graph.devices, board, order);
  }, [graph.devices, baseIds, board]);
  const filtered = graph.devices.filter((d) => matchesDevice(d, query) && (!site || d.site === site) && (!zoneId || positions.get(d.id)?.zone_id === zoneId));
  const visible = filtered.slice(0, GRAPH_DEVICE_LIMIT);
  const sites = [...new Set(graph.devices.map((d) => d.site))].sort();

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    const navigate = (e: MouseEvent) => {
      const anchor = e.target instanceof Element ? e.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (anchor && !anchor.hash && anchor.target !== "_blank" && anchor.origin === window.location.origin && anchor.pathname !== window.location.pathname && !window.confirm("Kaydedilmemiş topoloji değişiklikleri var. Sayfadan ayrılsın mı?")) {
        e.preventDefault(); e.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", beforeUnload); document.addEventListener("click", navigate, true);
    return () => { window.removeEventListener("beforeunload", beforeUnload); document.removeEventListener("click", navigate, true); };
  }, [dirty]);
  const change = useCallback((value: TopologyBoard) => {
    if (busy) return;
    setBoard(value); setDirty(true); setNotice("");
  }, [busy]);
  function select(value: Selection) {
    setSelection(value);
    const deviceId = value?.kind === "device" ? value.id : value?.kind === "endpoint" || value?.kind === "neighbor" ? value.deviceId : "";
    const url = new URL(window.location.href);
    if (deviceId) url.searchParams.set("device", deviceId); else url.searchParams.delete("device");
    if (value?.kind === "endpoint") url.searchParams.set("endpoint", value.id); else url.searchParams.delete("endpoint");
    window.history.replaceState(null, "", url.pathname + url.search);
    if (deviceId) recordActivity({ action: "topology.select", page: "topology", device_id: deviceId, node_id: value!.id });
  }
  async function save() {
    setBusy(true); setError(""); setNotice("");
    try { const saved = await api<TopologyBoard>(boardPath, { method: "PUT", body: JSON.stringify(boardPayload(board)) }); setBoard(saved); persisted(saved); setDirty(false); setNotice("Yerleşim kaydedildi."); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function reload() {
    setBusy(true); setError("");
    try { const saved = await api<TopologyBoard>(boardPath); setBoard(saved); persisted(saved); setDirty(false); setNotice("Sunucudaki yerleşim yüklendi."); setDialog(null); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <section className="topology-workspace">
    <div className="page-heading"><div><p className="eyebrow">AĞ ÇALIŞMA ALANI</p><h1>Topoloji</h1><p>Kişisel yerleşim · Yetkili cihazlar</p></div>
      <div className="toolbar-actions"><button disabled={busy || board.zones.length >= 40} onClick={() => setDialog("zone")}>Zone ekle</button><button disabled={busy || board.links.length >= 500} onClick={() => setDialog("connection")}>Bağlantı ekle</button><button className="primary" disabled={!dirty || busy} onClick={save}>{busy ? "İşleniyor…" : "Kaydet"}</button><button onClick={() => void refresh()}>Yenile</button></div>
    </div>
    {error && <p className="notice error" role="alert">{error}</p>}
    {!!graphError && <p className="notice error" role="alert">{errorMessage(graphError)} Son alınan gözlemler gösteriliyor; güncellikleri doğrulanamıyor.</p>}
    {notice && <p className="notice" role="status">{notice}</p>}
    <div className="topology-status"><span>{filtered.length} / {graph.devices.length} cihaz · {board.zones.length} zone · {board.links.length} kullanıcı bağlantısı</span>
      <span role="status">{dirty ? "Kaydedilmemiş değişiklikler" : `Kayıt: ${formatTime(board.updated_at ?? null)}`} · <button className="text-action" disabled={busy} onClick={() => setDialog("reload")}>Yerleşimi yeniden yükle</button></span>
    </div>
    {!!initialBoard.omitted_references && <p className="notice">Artık erişilemeyen cihaz / port başvuruları gizlendi. Kaydettiğinizde geçersiz başvurular temizlenir.</p>}
    <div className={`topology-commandbar ${filtersOpen ? "filters-open" : ""}`}><label>Cihaz, MAC veya IP ara<input value={query} onChange={(e) => setQuery(e.target.value)} maxLength={160} placeholder="Ad, yönetim IP, uç IP veya MAC" /></label>
      <label>Site<select value={site} onChange={(e) => setSite(e.target.value)}><option value="">Tüm yetkili siteler</option>{sites.map((s) => <option key={s}>{s}</option>)}</select></label>
      <label>Zone<select value={zoneId} onChange={(e) => setZoneId(e.target.value)}><option value="">Tüm zone’lar</option>{board.zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select></label>
      <label>Cihaza odaklan<select value={selection?.kind === "device" ? selection.id : selection?.kind === "endpoint" || selection?.kind === "neighbor" ? selection.deviceId : ""} onChange={(e) => {
        if (!e.target.value) { select(null); return; }
        if (!visible.some((d) => d.id === e.target.value)) { setQuery(graph.devices.find((d) => d.id === e.target.value)?.management_address ?? ""); setSite(""); setZoneId(""); }
        select({ kind: "device", id: e.target.value }); setFocus((v) => ({ id: e.target.value, sequence: (v?.sequence ?? 0) + 1 }));
      }}><option value="">Cihaz seçin</option>{graph.devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      <button className="topology-filter-toggle" aria-expanded={filtersOpen} onClick={() => setFiltersOpen(!filtersOpen)}>Site / zone filtreleri{site || zoneId ? " · etkin" : ""}</button>
    </div>
    {(site || zoneId) && <p className="topology-active-filters">Kapsam: {site || "Tüm siteler"} · {board.zones.find((z) => z.id === zoneId)?.name ?? "Tüm zone’lar"} <button onClick={() => { setSite(""); setZoneId(""); }}>Filtreleri temizle</button></p>}
    {filtered.length > GRAPH_DEVICE_LIMIT && <p className="notice">Okunabilirlik için ilk {GRAPH_DEVICE_LIMIT} cihaz çiziliyor. Diğer cihazlara arama veya odak seçimiyle ulaşabilirsiniz; toplamlar tüm kapsamı içerir.</p>}
    <div className={`topology-stage ${busy ? "is-saving" : ""}`} aria-busy={busy}>
      <TopologyCanvas graph={graph} devices={visible} board={board} positions={positions} selection={selection} select={select} change={change} query={query} focus={focus} detailed={detailed} setDetailed={setDetailed} />
      <TopologyInspector selection={selection} graph={graph} board={board} positions={positions} select={select} change={change} />
    </div>
    <p className="source-note">Görünüm yenilendi: {formatTime(graph.generated_at)} · 15 sn sorgulama. Her cihazın gözlem zamanı ayrıdır. Yenile, toplanmış verileri getirir; ağ taraması başlatmaz. Varsayılan görünümde cihaz başına en fazla 6 uç çizilir; Detaylandır açıkken tüm uçlar gösterilir.</p>
    <details className="topology-accessible-list"><summary>Bağlantıları liste olarak göster ({board.links.length + graph.links.length})</summary>
      <ul>{board.links.map((l) => <li key={`m:${l.id}`}><button onClick={() => select({ kind: "manual", id: l.id })}>{graph.devices.find((d) => d.id === l.source_device_id)?.name ?? "Erişilemeyen cihaz"} ↔ {graph.devices.find((d) => d.id === l.target_device_id)?.name ?? "Erişilemeyen cihaz"} · Elle çizilen</button></li>)}
        {graph.links.map((l) => <li key={`o:${l.id}`}><button onClick={() => select({ kind: "observed", id: l.id })}>{graph.devices.find((d) => d.id === l.source_device_id)?.name} ↔ {graph.devices.find((d) => d.id === l.target_device_id)?.name} · {l.relation === "l2" ? "L2 komşuluk" : "Fiziksel kanıt"}</button></li>)}</ul>
    </details>
    {dialog === "zone" && <AddZone board={board} onClose={() => setDialog(null)} onAdd={(zone) => { change({ ...board, zones: [...board.zones, zone] }); select({ kind: "zone", id: zone.id }); setDialog(null); }} />}
    {dialog === "connection" && <AddConnection board={board} graph={graph} onClose={() => setDialog(null)} onAdd={(link) => { change({ ...board, links: [...board.links, link] }); select({ kind: "manual", id: link.id }); setDialog(null); }} />}
    {dialog === "reload" && <Dialog title="Sunucudaki yerleşimi yükle" onClose={() => setDialog(null)}><p>Kaydedilmemiş yerleşim değişiklikleri bırakılacak. Cihaz verileri değişmeyecek.</p><button disabled={busy} onClick={reload}>Yüklemeyi onayla</button></Dialog>}
  </section>;
}
