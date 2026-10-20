"use client";
import { useState } from "react";
import type { EndpointCollection } from "../lib/topology";
import { endpointLabels } from "../lib/topology";
import { EndpointDetails } from "./EndpointDetails";

export function PortEndpoints({ collection, interfaceIds }: { collection?: EndpointCollection; interfaceIds: string[] }) {
  const [query, setQuery] = useState(""), [page, setPage] = useState(0);
  const entries = (collection?.entries ?? []).filter((e) => interfaceIds.includes(e.interface_id)
    && [e.mac, ...e.addresses].some((value) => value.toLowerCase().includes(query.trim().toLowerCase())));
  const last = Math.max(0, Math.ceil(entries.length / 6) - 1), current = Math.min(page, last);
  return <section className="port-endpoints" aria-label="Port MAC ve IP gözlemleri">
    <h3>MAC / IP gözlemleri</h3>
    <label>Portta MAC veya IP ara<input type="search" value={query} maxLength={160} onChange={(e) => { setQuery(e.target.value); setPage(0); }} /></label>
    {!entries.length ? <p>{query ? "Eşleşen kayıt yok." : collection?.status === "ok" ? "Bu portta uç kaydı gözlenmedi." : endpointLabels[collection?.status ?? "unknown"]}</p> : <>
      {entries.slice(current * 6, current * 6 + 6).map((endpoint) => <EndpointDetails key={endpoint.id} endpoint={endpoint} />)}
      {last > 0 && <div className="small-actions"><button disabled={!current} onClick={() => setPage(current - 1)}>Önceki uçlar</button><span>{current + 1} / {last + 1}</span><button disabled={current === last} onClick={() => setPage(current + 1)}>Sonraki uçlar</button></div>}
    </>}
    <p className="source-note">MAC tek başına IP içermez. ARP/NDP kaydı yoksa ağ geçidinden gözlem gerekir. Bu kayıtlar doğrudan kablo kanıtı değildir.</p>
  </section>;
}
