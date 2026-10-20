"use client";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { formatTime } from "../../lib/metrics";
import { EndpointDetails } from "../EndpointDetails";
import { dataLabels, deleteZone, endpointLabels, interfaceLabel, movePlacement, moveZone, neighborStateLabels, physicalLabels, portLabel, reachLabels,
  type NetworkDevice, type NetworkGraph, type Placement, type Selection, type TopologyBoard, type Zone } from "../../lib/topology";

function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return <dl className="topology-facts">{rows.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value ?? "Bilinmiyor"}</dd></div>)}</dl>;
}
type Props = { selection: Selection; graph: NetworkGraph; board: TopologyBoard; positions: Map<string, Placement>; select: (v: Selection) => void; change: (v: TopologyBoard) => void };

export default function TopologyInspector({ selection, graph, board, positions, select, change }: Props) {
  const deviceId = selection?.kind === "device" ? selection.id : selection?.kind === "endpoint" || selection?.kind === "neighbor" ? selection.deviceId : null;
  const device = graph.devices.find((d) => d.id === deviceId);
  const zone = selection?.kind === "zone" ? board.zones.find((z) => z.id === selection.id) : null;
  const manual = selection?.kind === "manual" ? board.links.find((l) => l.id === selection.id) : null;
  const observed = selection?.kind === "observed" ? graph.links.find((l) => l.id === selection.id) : null;
  let content: ReactNode = <div className="topology-inspector-empty"><h3>Ağı keşfedin</h3><p>Bir cihaz, uç düğüm, bağlantı veya zone seçin.</p><p>Cihazları sürükleyin veya odaklanıp ok tuşlarıyla taşıyın. Mobilde sürüklemek için taşıma modunu açın.</p><p>Zone’lar ve elle çizilen bağlantılar yalnızca sizin çalışma alanınıza aittir; cihazlara komut gönderilmez.</p></div>;
  if (zone) content = <ZoneEditor key={zone.id} zone={zone} board={board} change={change} clear={() => select(null)} />;
  else if (manual || observed) {
    const link = manual ?? observed!;
    const source = graph.devices.find((d) => d.id === link.source_device_id), target = graph.devices.find((d) => d.id === link.target_device_id);
    content = source && target ? <><h3>{manual ? "Elle çizilen bağlantı" : observed!.relation === "l2" ? "L2 komşuluk" : "Fiziksel bağlantı kanıtı"}</h3>
      <Facts rows={[["Kaynak cihaz", source.name], ["Kaynak port / arayüz", manual ? portLabel(source, manual.source_port_id) : interfaceLabel(source, observed!.source_interface_id)],
        ["Hedef cihaz", target.name], ["Hedef port / arayüz", manual ? portLabel(target, manual.target_port_id) : interfaceLabel(target, observed!.target_interface_id)],
        ...(observed ? [["Kanıt", observed.evidence], ["Kaynak", observed.source], ["Son gözlem", formatTime(observed.observed_at)], ["Güncellik", dataLabels[observed.data_state]]] as [string, ReactNode][] : [])]} />
      {manual && <><p className="notice">Kullanıcı çizimi; çalışan kablo veya link-up doğrulaması değildir.</p><button className="danger" onClick={() => { change({ ...board, links: board.links.filter((l) => l.id !== manual.id) }); select(null); }}>Bağlantıyı kaldır</button></>}
    </> : <p>Bağlantının bir ucu artık erişilebilir değil. Gözlemleri yenileyin.</p>;
  } else if (device && selection) {
    const endpoint = selection.kind === "endpoint" ? device.endpoints.entries.find((e) => e.id === selection.id) : null;
    const neighbor = selection.kind === "neighbor" ? device.neighbors.find((n) => n.id === selection.id) : null;
    content = <>
      <h3>{endpoint ? "Uç gözlemi" : neighbor ? neighbor.label : device.name}</h3>
      <p className={`topology-data-state ${device.data_state}`}>{dataLabels[device.data_state]} · {formatTime(device.observed_at)}</p>
      {endpoint ? <>
        <EndpointDetails endpoint={endpoint} />
        <Facts rows={[["Gözleyen cihaz", device.name], ["Arayüz", interfaceLabel(device, endpoint.interface_id)],
          ["Fiziksel port", physicalLabels(device, endpoint.interface_id)], ["VLAN", endpoint.vlan], ["Keşif", endpoint.discovery.toUpperCase()],
          ["Komşuluk durumu", neighborStateLabels[endpoint.state]], ["Toplama kaynağı", device.source], ["Kanıt", endpoint.evidence]]} />
        <p className="source-note">Bu kayıt arayüzden gözlenmiştir. Arada switch, telefon veya başka bir köprü olabilir. Sembol, bilgisayar türünü doğrulamaz.</p>
        <button onClick={() => select({ kind: "device", id: device.id })}>Cihaza dön</button>
      </> : neighbor ? <><Facts rows={[["Yönetim IP", neighbor.addresses?.join(", ") || "Bildirilmedi"], ["Adres gözlemi", formatTime(neighbor.observed_at)], ["Arayüz", interfaceLabel(device, neighbor.interface_id)], ["İlişki", neighbor.relation === "l2" ? "L2 komşuluk" : "Fiziksel kanıt"], ["Kanıt", neighbor.evidence]]} /><p className="source-note">Uzak envanter kimliği verilmediği için başka bir cihazla otomatik birleştirilmedi.</p></> : <>
        <Facts rows={[["Yönetim IP", device.management_address], ["Site", device.site], ["Tür", device.device_type], ["Erişilebilirlik", reachLabels[device.reachability]],
          ["MAC / IP tablosu", endpointLabels[device.endpoints.status]], ["Kayıt sayısı", ["ok", "partial"].includes(device.endpoints.status) ? device.endpoints.entries.length : null], ["Kaynak", device.source]]} />
        <DevicePlacement key={`${device.id}:${board.version}`} device={device} placement={positions.get(device.id)!} board={board} change={change} />
        <EndpointList key={device.id} device={device} select={select} />
        {!!device.neighbors.length && <details><summary>Uzak kimliği eşlenmemiş komşular ({device.neighbors.length})</summary>
          {device.neighbors.map((n) => <button key={n.id} onClick={() => select({ kind: "neighbor", id: n.id, deviceId: device.id })}>{n.label} · {interfaceLabel(device, n.interface_id)}</button>)}</details>}
      </>}
      <Link className="button-link" href={`/devices/${encodeURIComponent(device.id)}`}>Cihaz detayları</Link>
    </>;
  } else if (selection) content = <p role="status">Seçilen kayıt artık bu gözlemde veya yetki kapsamında yok. Başka bir düğüm seçin.</p>;
  return <aside className="topology-inspector" aria-label="Topoloji seçim ayrıntıları">
    <details open><summary>Seçim ayrıntıları</summary><div className="topology-inspector-body">{content}</div></details>
  </aside>;
}

function DevicePlacement({ device, placement, board, change }: { device: NetworkDevice; placement: Placement; board: TopologyBoard; change: (v: TopologyBoard) => void }) {
  return <section className="topology-placement"><label>Zone ataması<select aria-label="Cihazın zone’u" value={placement.zone_id ?? ""} onChange={(e) => {
    const zone = board.zones.find((z) => z.id === e.target.value);
    if (!zone) { change(movePlacement(board, { ...placement, zone_id: null })); return; }
    const occupied = board.placements.filter((p) => p.zone_id === zone.id && p.device_id !== device.id).length;
    const columns = Math.max(1, Math.floor(zone.width / 560)), row = Math.floor(occupied / columns);
    const nextHeight = Math.max(zone.height, (row + 1) * 520 + 50);
    if (nextHeight > 6000) return;
    const resized = { ...board, zones: board.zones.map((z) => z.id === zone.id ? { ...z, height: nextHeight } : z) };
    change(movePlacement(resized, { device_id: device.id, zone_id: zone.id, x: zone.x + 280 + (occupied % columns) * 560, y: zone.y + 240 + row * 520 }));
  }}><option value="">Zone dışında</option>{board.zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select></label>
    <p className="source-note">Konum: {Math.round(placement.x)}, {Math.round(placement.y)}. Sürükleme veya ok tuşlarıyla düzenlenebilir.</p>
  </section>;
}

function EndpointList({ device, select }: { device: NetworkDevice; select: (v: Selection) => void }) {
  const [query, setQuery] = useState(""), [page, setPage] = useState(0);
  const entries = device.endpoints.entries.filter((e) => [e.mac, ...e.addresses, interfaceLabel(device, e.interface_id)].some((v) => v.toLowerCase().includes(query.toLowerCase())));
  const lastPage = Math.max(0, Math.ceil(entries.length / 12) - 1), currentPage = Math.min(page, lastPage);
  return <section className="endpoint-list"><h4>Portlardaki uç gözlemleri</h4>
    <label>MAC, IP veya arayüz ara<input value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} maxLength={160} /></label>
    {!entries.length ? <p>{device.endpoints.status === "ok" ? "Bu kapsamda uç kaydı yok." : endpointLabels[device.endpoints.status]}</p> : <>
      <div className="endpoint-results">{entries.slice(currentPage * 12, currentPage * 12 + 12).map((e) => <button key={e.id} onClick={() => select({ kind: "endpoint", id: e.id, deviceId: device.id })}>
        <strong className="mono">{e.addresses[0] ?? "IP bilinmiyor"}</strong><span className="mono">{e.mac}</span><small>{interfaceLabel(device, e.interface_id)} · {e.discovery.toUpperCase()}</small>
      </button>)}</div>
      <div className="small-actions"><button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Önceki</button><span>{currentPage + 1}/{lastPage + 1}</span><button disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Sonraki</button></div>
    </>}
  </section>;
}

function ZoneEditor({ zone, board, change, clear }: { zone: Zone; board: TopologyBoard; change: (v: TopologyBoard) => void; clear: () => void }) {
  const [confirm, setConfirm] = useState(false);
  return <><h3>Zone düzenle</h3><form className="topology-form" key={`${zone.x}:${zone.y}:${zone.width}:${zone.height}:${zone.name}`} onSubmit={(e) => {
    e.preventDefault(); const form = new FormData(e.currentTarget);
    const moved = moveZone(board, zone, Number(form.get("x")), Number(form.get("y")));
    change({ ...moved, zones: moved.zones.map((z) => z.id === zone.id ? { ...z, name: String(form.get("name")).trim(), width: Number(form.get("width")), height: Number(form.get("height")), tone: form.get("tone") as Zone["tone"] } : z) });
  }}>
    <label>Zone adı<input name="name" defaultValue={zone.name} required maxLength={80} pattern=".*\S.*" /></label>
    <label>Yüzey tonu<select name="tone" defaultValue={zone.tone}><option value="slate">Gri</option><option value="blue">Mavi gri</option><option value="sand">Kum</option></select></label>
    <div className="topology-form-pair">{([['x', 'X konumu', 0, 20000], ['y', 'Y konumu', 0, 20000], ['width', 'Genişlik', 400, 6000], ['height', 'Yükseklik', 280, 6000]] as const).map(([key, label, min, max]) => <label key={key}>{label}<input type="number" name={key} min={min} max={max} required defaultValue={Math.round(zone[key])} /></label>)}</div>
    <button type="submit">Zone’u uygula</button>
  </form><p className="source-note">Zone taşınırken içindeki cihazlar birlikte taşınır. Yeniden boyutlandırma cihaz konumlarını değiştirmez.</p>
    <button className="danger" onClick={() => setConfirm(!confirm)}>Zone’u kaldır</button>
    {confirm && <div className="notice"><p>Yalnızca zone kaldırılacak; cihazlar ve bağlantılar korunacak.</p><button onClick={() => { change(deleteZone(board, zone.id)); clear(); }}>Kaldırmayı onayla</button></div>}
  </>;
}
