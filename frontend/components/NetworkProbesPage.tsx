"use client";
import { useMemo, useState, type FormEvent } from "react";
import useSWR from "swr";
import { api, errorMessage } from "../lib/api";
import type { NetworkProbeAgent, NetworkProbeProposal, NetworkProbeState } from "../lib/contracts";
import { formatTime } from "../lib/metrics";

const endpoint = "/api/v1/network-probes";

export default function NetworkProbesPage() {
  const { data, error, mutate } = useSWR<NetworkProbeState>(endpoint, api, { refreshInterval: 10000 });
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState(""), [notice, setNotice] = useState("");
  async function action(path: string, init: RequestInit, message: string) {
    setBusy(true); setFailure(""); setNotice("");
    try { await api(path, init); await mutate(); setNotice(message); }
    catch (value) { setFailure(errorMessage(value)); }
    finally { setBusy(false); }
  }
  if (error) return <p role="alert" className="notice error">{errorMessage(error)}</p>;
  if (!data) return <p role="status">Ağ keşfi yapılandırması yükleniyor…</p>;
  const agentNames = new Map(data.agents.map((agent) => [agent.id, agent.name]));
  const sites = [...new Set(data.proposals.map((proposal) => proposal.site))].sort((left, right) => left.localeCompare(right, "tr"));
  const runByScope = new Map<string, NetworkProbeState["runs"][number]>();
  for (const run of data.runs) if (!runByScope.has(run.scope_id)) runByScope.set(run.scope_id, run);
  return <>
    <section className="panel"><div className="panel-heading"><div><h2>VLAN ARP probe ajanları</h2><p>Ham ağ erişimi API’den ayrıdır; yerel ajan otomatik kaydolur, token veya CLI gerektirmez.</p></div></div>
      <div className="probe-body"><div className="probe-grid">{!data.agents.length ? <p>Yerel ajan başlatılıyor; kısa süre sonra bu listeye eklenecek.</p> : data.agents.map((agent) => <article key={agent.id}>
        <div><strong>{agent.name}</strong><span className={`status ${agent.online ? "ok" : "unknown"}`}>{agent.online ? "Bağlı" : "Bağlı değil"}</span></div>
        <p>{agent.site || "Site ataması bekliyor"} · Son heartbeat: {formatTime(agent.last_seen_at)}</p>
        <p>{agent.interfaces.length ? agent.interfaces.map((item) => `${item.name}: ${item.addresses.join(", ") || "IPv4 yok"}`).join(" · ") : "Henüz arayüz bildirilmedi"}</p>
        {!agent.site && <AgentAssignment agent={agent} sites={sites} busy={busy} onAssigned={async () => { await mutate(); setNotice("Probe ajanı siteye atandı."); }} onFailure={setFailure} />}
        {agent.enabled && <button disabled={busy} onClick={() => { if (window.confirm(`${agent.name} ajanını iptal etmek istediğinize emin misiniz?`)) void action(`${endpoint}/agents/${agent.id}`, { method: "DELETE" }, "Probe ajanı iptal edildi."); }}>Ajanı iptal et</button>}
      </article>)}</div></div>
    </section>

    <section className="panel"><div className="panel-heading"><div><h2>Switch SVI önerileri</h2><p>Hedef ağ switch’in SVI CIDR’ından gelir; SVI adresi kaynak olarak kullanılmaz.</p></div><span>En fazla /{data.defaults.max_range_prefix} · {data.defaults.max_targets} hedef · {data.defaults.max_rate_pps} ARP/sn</span></div>
      <div className="probe-body probe-proposals">{!data.proposals.length ? <p>Güncel ve VLAN kimliği doğrulanmış IPv4 SVI gözlemi bulunamadı.</p> : data.proposals.map((proposal) =>
        <ProposalForm key={proposal.id} proposal={proposal} agents={data.agents} busy={busy} onFailure={setFailure}
          onCreated={async () => { await mutate(); setNotice("ARP tarama kapsamı onaylandı."); }} />)}</div>
    </section>

    <section className="panel"><div className="panel-heading"><div><h2>Onaylı tarama kapsamları</h2><p>Başarılı aktif tarama önceliklidir; ajan çevrimdışı veya sonuç eskiyse switch ARP verisi yedek olur.</p></div></div>
      <div className="probe-body"><div className="probe-scope-list">{!data.scopes.length ? <p>Henüz onaylı kapsam yok.</p> : data.scopes.map((scope) => { const run = runByScope.get(scope.id); return <article key={scope.id}>
        <div className="probe-scope-heading"><div><strong>{scope.site} · VLAN {scope.vlan} · {scope.vrf || "Varsayılan VRF"}</strong><p>{scope.target_cidrs.join(", ")} · {scope.interface_name} / {scope.source_ip} · {agentNames.get(scope.agent_id) || "Ajan bulunamadı"}</p></div><span className={`status ${scope.status === "active" ? "ok" : "unknown"}`}>{scope.status === "active" ? "Etkin" : scope.status === "needs_review" ? "Yeniden onay gerekli" : "Kapalı"}</span></div>
        <dl className="device-facts probe-facts"><div><dt>Son başarılı tarama</dt><dd>{formatTime(scope.last_success_at)}</dd></div><div><dt>Sonraki tarama</dt><dd>{scope.enabled ? formatTime(scope.next_due_at) : "—"}</dd></div>
          <div><dt>Son sonuç</dt><dd>{run ? `${run.matched_count} eşleşme / ${run.reply_count} yanıt` : "Henüz çalışmadı"}</dd></div><div><dt>Bilinmeyen yanıt</dt><dd>{run?.unknown_count ?? "—"}</dd></div></dl>
        {scope.last_error && <p className="notice error">{scope.last_error}</p>}
        <div className="toolbar-actions probe-actions"><button disabled={busy || !scope.enabled || scope.status !== "active"} onClick={() => void action(`${endpoint}/scopes/${scope.id}/runs`, { method: "POST" }, "Manuel ARP taraması kuyruğa alındı.")}>Şimdi tara</button>
          <button disabled={busy || scope.status === "needs_review"} onClick={() => void action(`${endpoint}/scopes/${scope.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !scope.enabled }) }, scope.enabled ? "Tarama kapsamı kapatıldı." : "Tarama kapsamı etkinleştirildi.")}>{scope.enabled ? "Kapat" : "Etkinleştir"}</button>
          <button disabled={busy} onClick={() => { if (window.confirm("Bu kapsam ve aktif eşleşmeleri silinsin mi?")) void action(`${endpoint}/scopes/${scope.id}`, { method: "DELETE" }, "Tarama kapsamı silindi."); }}>Sil</button></div>
      </article>; })}</div></div>
    </section>
    {notice && <p className="notice" role="status">{notice}</p>}{failure && <p className="notice error" role="alert">{failure}</p>}
  </>;
}

function AgentAssignment({ agent, sites, busy, onAssigned, onFailure }: { agent: NetworkProbeAgent; sites: string[]; busy: boolean;
  onAssigned: () => Promise<void>; onFailure: (message: string) => void }) {
  const [site, setSite] = useState(sites[0] || ""), [assigning, setAssigning] = useState(false);
  async function assign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setAssigning(true); onFailure("");
    try { await api(`${endpoint}/agents/${agent.id}`, { method: "PATCH", body: JSON.stringify({ site }) }); await onAssigned(); }
    catch (value) { onFailure(errorMessage(value)); } finally { setAssigning(false); }
  }
  return <form className="probe-agent-assignment" onSubmit={assign}><label>Site<select value={site} required onChange={(event) => setSite(event.target.value)}>
    <option value="">Site seçin</option>{sites.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
    <button className="primary" disabled={busy || assigning || !site}>Bu siteye ata</button>
  </form>;
}

function ProposalForm({ proposal, agents, busy, onCreated, onFailure }: { proposal: NetworkProbeProposal; agents: NetworkProbeAgent[];
  busy: boolean; onCreated: () => Promise<void>; onFailure: (message: string) => void }) {
  const available = useMemo(() => agents.filter((agent) => agent.site === proposal.site && agent.online && agent.enabled), [agents, proposal.site]);
  const [agentId, setAgentId] = useState(available[0]?.id || "");
  const agent = available.find((item) => item.id === agentId) || available[0];
  const [interfaceName, setInterfaceName] = useState(agent?.interfaces[0]?.name || "");
  const selectedInterface = agent?.interfaces.find((item) => item.name === interfaceName) || agent?.interfaces[0];
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); onFailure(""); const values = new FormData(event.currentTarget);
    try {
      await api(`${endpoint}/scopes`, { method: "POST", body: JSON.stringify({ proposal_id: proposal.id, agent_id: agent?.id,
        interface_name: selectedInterface?.name, source_ip: values.get("source_ip"),
        target_cidrs: String(values.get("target_cidrs") || "").split(",").map((item) => item.trim()).filter(Boolean),
        interval_seconds: Number(values.get("interval_seconds")), vrf: values.get("vrf") || null,
        confirm_unknown_vrf: values.get("confirm_unknown_vrf") === "on",
        active_broadcast_acknowledged: values.get("acknowledged") === "on" }) });
      await onCreated();
    } catch (value) { onFailure(errorMessage(value)); }
  }
  return <article className={proposal.conflict ? "has-conflict" : ""}><div className="probe-proposal-heading"><div><strong>{proposal.site} · VLAN {proposal.vlan} · {proposal.vrf_known ? proposal.vrf || "Varsayılan VRF" : "VRF doğrulanmadı"}</strong><p>{proposal.network} · {proposal.evidence.map((item) => `${item.device_name} / ${item.address}`).join(" · ")}</p></div>{proposal.conflict && <span className="status error">Çakışma</span>}</div>
    {!proposal.conflict && <form className="probe-scope-form" onSubmit={submit}>
      <label>Probe ajanı<select value={agent?.id || ""} required onChange={(event) => { setAgentId(event.target.value); const next = available.find((item) => item.id === event.target.value); setInterfaceName(next?.interfaces[0]?.name || ""); }}><option value="">Ajan seçin</option>{available.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>VLAN arayüzü<select value={selectedInterface?.name || ""} required onChange={(event) => setInterfaceName(event.target.value)}><option value="">Arayüz seçin</option>{agent?.interfaces.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
      <label>Kaynak IPv4<select name="source_ip" required><option value="">Adres seçin</option>{selectedInterface?.addresses.map((value) => <option key={value} value={value.split("/")[0]}>{value}</option>)}</select></label>
      <label>Onaylı hedef CIDR<input name="target_cidrs" defaultValue={proposal.requires_narrowing ? "" : proposal.network} required placeholder={`${proposal.network} içinde /22 veya daha dar`} /></label>
      <label>Aralık (saniye)<input name="interval_seconds" type="number" min={900} max={86400} defaultValue={900} required /></label>
      {!proposal.vrf_known && <><label>Doğrulanan VRF<input name="vrf" maxLength={160} placeholder="Boş = varsayılan VRF" /></label><label className="checkbox"><input name="confirm_unknown_vrf" type="checkbox" required />VRF kapsamını doğruladım</label></>}
      <label className="checkbox probe-ack"><input name="acknowledged" type="checkbox" required />Bu kapsamda aktif ARP broadcast sorguları gönderileceğini onaylıyorum.</label>
      <button className="primary" disabled={busy || !agent || !selectedInterface}>Kapsamı onayla</button>
    </form>}
  </article>;
}
