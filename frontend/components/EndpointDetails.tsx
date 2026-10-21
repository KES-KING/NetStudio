import type { Endpoint } from "../lib/topology";
import { resolutionLabel } from "../lib/topology";
import { formatTime } from "../lib/metrics";

/** Shared evidence presentation for port, device graph and network graph. */
export function EndpointDetails({ endpoint }: { endpoint: Endpoint }) {
  return <div className="endpoint-details">
    <dl className="device-facts">
      <div><dt>IP adresleri</dt><dd className="mono">{endpoint.addresses.join(", ") || "Bulunamadı"}</dd></div>
      <div><dt>MAC adresi</dt><dd className="mono">{endpoint.mac}</dd></div>
      <div><dt>IP eşleştirme</dt><dd>{resolutionLabel(endpoint)}</dd></div>
      <div><dt>VLAN / VRF</dt><dd>{endpoint.vlan ?? "Bilinmiyor"} / {endpoint.vrf_known ? endpoint.vrf || "Varsayılan" : "Bildirilmedi"}</dd></div>
      <div><dt>Adres gözlemi</dt><dd>{formatTime(endpoint.resolution?.observed_at)}</dd></div>
    </dl>
    <details><summary>Adres kanıtı</summary>
      <p className="source-note">{endpoint.evidence}</p>
      {endpoint.resolution?.sources.map((source, index) => <p className="source-note" key={`${source.device_id}:${source.interface_id}:${index}`}>
        {source.device_name} · {source.discovery === "active_arp" ? "YAZILIM ARP" : source.discovery.toUpperCase()} · {formatTime(source.observed_at)}<br />{source.evidence}
      </p>)}
    </details>
  </div>;
}
