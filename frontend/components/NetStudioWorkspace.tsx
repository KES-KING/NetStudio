"use client";

import { useEffect, useMemo, useState } from "react";
import { boundInterface, portStatus, type PhysicalPort } from "../lib/domain";
import { demoDevice } from "../lib/fixture";

type IconName = "grid" | "topology" | "backup" | "jobs" | "search" | "bell" | "plus" | "refresh" | "zoomIn" | "zoomOut" | "fit" | "close" | "switch" | "external";

function Icon({ name, size = 15 }: { name: IconName; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  const paths: Record<IconName, React.ReactNode> = {
    grid: <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>,
    topology: <><circle cx="6" cy="6" r="2.3" /><circle cx="18" cy="7" r="2.3" /><circle cx="12" cy="18" r="2.3" /><path d="m8 7 7.7-.2M7.4 8l3.1 7.5m5.8-6.4-3 6.8" /></>,
    backup: <><path d="M6 5h12v14H6z" /><path d="M9 5V3h6v2M9 10h6M9 14h4" /></>,
    jobs: <><path d="M5 7h14M7 3v4m10-4v4M6 11h12M6 15h7M6 19h5" /><rect x="4" y="4" width="16" height="16" rx="2" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.2" /><path d="m16 16 4.4 4.4" /></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    refresh: <><path d="M20 11a8 8 0 0 0-14.7-4L3 10m0-5v5h5M4 13a8 8 0 0 0 14.7 4L21 14m0 5v-5h-5" /></>,
    zoomIn: <><circle cx="10.8" cy="10.8" r="6.2" /><path d="M10.8 7.7v6.2m-3.1-3.1h6.2M16 16l4.4 4.4" /></>,
    zoomOut: <><circle cx="10.8" cy="10.8" r="6.2" /><path d="M7.7 10.8h6.2M16 16l4.4 4.4" /></>,
    fit: <><path d="M8 4H4v4M16 4h4v4M8 20H4v-4M20 16v4h-4" /><rect x="8" y="8" width="8" height="8" rx="1" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    switch: <><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M6 10h2m3 0h2m3 0h2M6 14h2m3 0h2m3 0h2" /></>,
    external: <><path d="M14 5h5v5M19 5l-8 8" /><path d="M18 13v5H5V5h5" /></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function formatObserved(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}

function PortModal({ port, onClose }: { port: PhysicalPort; onClose: () => void }) {
  const iface = boundInterface(port, demoDevice);
  const status = portStatus(port, demoDevice);
  const admin = iface?.admin_up;
  const oper = iface?.oper_up;
  return (
    <div className="port-modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="port-modal" role="dialog" aria-modal="true" aria-labelledby="port-modal-title">
        <div className="port-modal-header">
          <div>
            <div id="port-modal-title" className="port-modal-title">{port.label}</div>
            <div className="port-modal-sub">{iface?.name ?? "Eşleşmemiş fiziksel port"} · {port.id}</div>
          </div>
          <button className="close-button" onClick={onClose} aria-label="Port detayını kapat"><Icon name="close" size={14} /></button>
        </div>
        <div className="port-modal-body">
          <div className="detail-grid">
            <div className="detail-cell"><div className="detail-label">Admin durumu</div><div className={`detail-value ${admin?.value ? "good" : "down"}`}>{admin?.value ? "UP" : "DOWN"}</div></div>
            <div className="detail-cell"><div className="detail-label">Oper durumu</div><div className={`detail-value ${status === "up" ? "good" : status === "stale" ? "warn" : "down"}`}>{status === "stale" ? "STALE" : oper?.value ? "UP" : "DOWN"}</div></div>
            <div className="detail-cell"><div className="detail-label">Hız</div><div className="detail-value">{iface?.speed_mbps.value ? `${iface.speed_mbps.value / 1000} Gbps` : "—"}</div></div>
            <div className="detail-cell"><div className="detail-label">Access VLAN</div><div className="detail-value">{iface?.access_vlan?.value ?? "—"}</div></div>
          </div>
          <div className="observed"><span className="freshness" /> Son gözlem {formatObserved(oper?.observed_at)} · kaynak: {oper?.source ?? "unknown"} · kalite: {oper?.quality ?? "unknown"}</div>
          <div className="port-modal-note">Bu cihaz bir salt okunur demo fixture&apos;ıdır. Doğrulanmış capability, yedek ve değişmez plan olmadan hiçbir yazma işlemi sunulmaz.</div>
          <div className="modal-actions"><button className="button" onClick={onClose}>Kapat</button><button className="button primary" disabled aria-disabled="true">Değişiklik planı</button></div>
        </div>
      </section>
    </div>
  );
}

function SwitchFrontPanel({ onSelect, selectedId }: { onSelect: (port: PhysicalPort) => void; selectedId?: string }) {
  const accessPorts = demoDevice.physical_ports.filter((port) => port.group === "access");
  const uplinkPorts = demoDevice.physical_ports.filter((port) => port.group === "uplink");
  const renderPort = (port: PhysicalPort, x: number, y: number, width: number, height: number) => {
    const status = portStatus(port, demoDevice);
    return (
      <g key={port.id} className={`svg-port ${status} ${port.connector === "sfp" ? "sfp" : ""} ${selectedId === port.id ? "selected" : ""}`} role="button" tabIndex={0} aria-label={`${port.label}, ${status}`} onClick={() => onSelect(port)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelect(port); }}>
        <rect x={x} y={y} width={width} height={height} rx="3" />
        <text x={x + width / 2} y={y + height / 2}>{port.label.replace("Gi0/", "").replace("Te0/", "U")}</text>
      </g>
    );
  };
  return (
    <div className="front-panel">
      <div className="front-panel-head"><div className="front-panel-title">Fiziksel ön panel</div><div className="front-panel-mode">SCHEMATIC · 28 PORT</div></div>
      <div className="switch-svg-wrap">
        <svg className="switch-svg" viewBox="0 0 760 176" role="img" aria-label="28 fiziksel portlu şematik switch ön paneli">
          <rect className="switch-body" x="5" y="5" width="750" height="166" rx="7" />
          <text className="switch-label" x="24" y="28">SW-DEMO-01 / FRONT</text>
          <text className="switch-label" x="24" y="56">ACCESS</text>
          {accessPorts.map((port, index) => { const row = index % 2; const col = Math.floor(index / 2); return renderPort(port, 74 + col * 25, 42 + row * 49, 20, 34); })}
          <text className="switch-label" x="630" y="56">UPLINK</text>
          {uplinkPorts.map((port, index) => { const row = index % 2; const col = Math.floor(index / 2); return renderPort(port, 634 + col * 46, 42 + row * 49, 36, 34); })}
        </svg>
      </div>
      <div className="front-panel-note">Model şablonu doğrulanmadı; görünüm şematiktir. Fiziksel portlar envanterdeki açık binding ile eşlenir.</div>
    </div>
  );
}

export function NetStudioWorkspace() {
  const [selectedPort, setSelectedPort] = useState<PhysicalPort | undefined>(undefined);
  const [activeNav, setActiveNav] = useState("Topoloji");
  const [search, setSearch] = useState("");
  const [jobMessage, setJobMessage] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const filteredDevice = useMemo(() => demoDevice.name.toLowerCase().includes(search.toLowerCase()), [search]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") setSelectedPort(undefined); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function queueConnectionTest() {
    setJobMessage("Bağlantı testi kuyruğa alınıyor…");
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/devices/${demoDevice.id}/connection-tests`, { method: "POST", headers: { "X-Stocc-User": "demo-operator" } });
      if (!response.ok) throw new Error("API unavailable");
      const job = await response.json() as { status: string; result?: { message?: string } };
      setJobMessage(`${job.status === "succeeded" ? "İş tamamlandı" : "İş alındı"}: ${job.result?.message ?? "fixture sonucu hazır"}`);
    } catch {
      setJobMessage("API çalışmıyor; bağlantı testi gönderilmedi. Demo verisi değişmedi.");
    }
  }

  async function queuePoll() {
    setPolling(true);
    setJobMessage("Salt okunur gözlem işi kuyruğa alınıyor…");
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/devices/${demoDevice.id}/polls`, { method: "POST", headers: { "X-Stocc-User": "demo-operator" } });
      if (!response.ok) throw new Error("API unavailable");
      const job = await response.json() as { status: string; result?: { snapshot?: { observations?: unknown[] } } };
      const count = job.result?.snapshot?.observations?.length ?? 0;
      setJobMessage(`${job.status === "succeeded" ? "Gözlem yenilendi" : "Gözlem işi alındı"}: ${count} ethernet interface · kaynak: fixture`);
    } catch {
      setJobMessage("API çalışmıyor; gözlem işi gönderilmedi. Son başarılı fixture snapshot korunuyor.");
    } finally {
      setPolling(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><div className="brand-mark"><Icon name="switch" size={16} /></div><div><div className="brand-name">Stocc NetStudio</div><div className="brand-meta">NETWORK OPERATIONS</div></div></div>
        <div className="topbar-center"><label className="search"><Icon name="search" size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Cihaz, port veya site ara" aria-label="Cihaz, port veya site ara" /></label><div className="connection-status"><span className="status-dot" /> Collector hazır</div></div>
        <div className="topbar-actions"><button className="topbar-icon" aria-label="Bildirimler"><Icon name="bell" size={16} /></button><div className="operator"><div className="avatar">AD</div><div className="operator-copy"><div className="operator-name">Ayşe Demir</div><div className="operator-role">Network admin</div></div></div></div>
      </header>
      <div className="workspace">
        <aside className="sidebar">
          <div className="side-label">Çalışma alanı</div>
          <nav className="nav" aria-label="Ana navigasyon">
            {[{ label: "Genel Bakış", icon: "grid" as IconName }, { label: "Envanter", icon: "switch" as IconName, count: "01" }, { label: "Topoloji", icon: "topology" as IconName }, { label: "Yedekler", icon: "backup" as IconName }, { label: "İşler", icon: "jobs" as IconName, count: "—" }].map((item) => <button key={item.label} className={`nav-button ${activeNav === item.label ? "active" : ""}`} onClick={() => setActiveNav(item.label)}><Icon name={item.icon} size={15} /><span>{item.label}</span>{item.count && <small className="nav-count">{item.count}</small>}</button>)}
          </nav>
          <div className="inventory"><div className="inventory-header"><div className="inventory-title">Cihaz envanteri</div><button className="inventory-add" aria-label="Cihaz ekle" disabled><Icon name="plus" size={14} /></button></div><div className="inventory-list">{filteredDevice ? <button className="device-row selected"><span className="device-status" /><span className="device-copy"><span className="device-name">{demoDevice.name}</span><span className="device-sub">{demoDevice.site}</span></span><Icon name="external" size={12} /></button> : <div className="device-sub" style={{ padding: "10px 12px" }}>Eşleşen cihaz yok</div>}</div></div>
          <div className="side-footer"><div className="demo-tag"><span className="status-dot" style={{ background: "var(--amber)" }} /> Salt okunur demo</div><div>Fixture verisi · gerçek cihaz bağlantısı kapalı</div></div>
        </aside>
        <section className="main" aria-label="Topoloji ve ön panel">
          <div className="main-heading"><div><div className="eyebrow">{activeNav}</div><h1 className="heading">Ağ görünümü</h1><div className="heading-copy">Gözlem tabanlı topoloji · {demoDevice.site}</div></div><div className="heading-actions"><button className="button" onClick={queuePoll} disabled={polling}><Icon name="refresh" size={13} /> {polling ? "Okunuyor…" : "Veriyi yenile"}</button><button className="button" onClick={queueConnectionTest}><Icon name="external" size={13} /> Bağlantı testi</button><button className="button primary" disabled title="Demo fixture salt okunur"><Icon name="plus" size={13} /> Cihaz ekle</button></div></div>
          <div className="revision"><span className="status-dot" /><strong>Snapshot #1042</strong><span className="revision-line" /> son tam okuma 14:32:08 <span className="revision-line" /> kaynak: fixture</div>
          {jobMessage && <div className="revision" role="status"><span className="status-dot" style={{ background: "var(--amber)" }} /><strong>{jobMessage}</strong></div>}
          <div className="canvas" aria-label="Temsili topoloji görünümü"><div className="canvas-grid" /><div className="topology-caption">TOPOLOGY / OBSERVED LINKS</div><div className="canvas-tools"><button className="canvas-tool" aria-label="Yakınlaştır"><Icon name="zoomIn" size={13} /></button><button className="canvas-tool" aria-label="Uzaklaştır"><Icon name="zoomOut" size={13} /></button><button className="canvas-tool" aria-label="Görünümü sığdır"><Icon name="fit" size={13} /></button></div><div className="topology-link link-core-a" /><div className="topology-link link-core-b" /><div className="topology-link link-core-fw" /><div className="topology-node node-core selected"><div className="node-title"><span className="node-icon"><Icon name="switch" size={12} /></span>SW-DEMO-01</div><div className="node-sub">Gi0/1 · 192.0.2.10</div><div className="node-status"><span className="status-dot" /> managed / read-only</div></div><div className="topology-node node-a"><div className="node-title"><span className="node-icon"><Icon name="switch" size={12} /></span>SW-ACCESS-A</div><div className="node-sub">one-sided evidence</div><div className="node-status" style={{ color: "var(--amber)" }}><span className="status-dot" style={{ background: "var(--amber)" }} /> stale</div></div><div className="topology-node node-b"><div className="node-title"><span className="node-icon"><Icon name="switch" size={12} /></span>SW-ACCESS-B</div><div className="node-sub">one-sided evidence</div><div className="node-status" style={{ color: "var(--amber)" }}><span className="status-dot" style={{ background: "var(--amber)" }} /> stale</div></div><div className="canvas-legend"><span className="legend-item"><span className="legend-line" /> gözlemlendi</span><span className="legend-item"><span className="legend-line dashed" /> eskimiş</span></div></div>
          <SwitchFrontPanel onSelect={setSelectedPort} selectedId={selectedPort?.id} />
        </section>
        <aside className="panel"><div className="panel-content"><div className="panel-heading"><div><div className="panel-kicker">Seçili cihaz</div><div className="panel-title">{demoDevice.name}</div><div className="panel-sub">{demoDevice.model} · {demoDevice.management_address}</div></div><button className="close-button" aria-label="Seçimi temizle"><Icon name="close" size={14} /></button></div><div className="read-only"><span>●</span> Salt okunur · demo fixture</div><div className="detail-section"><div className="detail-heading">Cihaz kimliği</div><div className="detail-grid"><div className="detail-cell"><div className="detail-label">Üretici</div><div className="detail-value">{demoDevice.vendor}</div></div><div className="detail-cell"><div className="detail-label">Seri</div><div className="detail-value">{demoDevice.serial}</div></div><div className="detail-cell"><div className="detail-label">İşletim sistemi</div><div className="detail-value">{demoDevice.os_version}</div></div><div className="detail-cell"><div className="detail-label">Port / interface</div><div className="detail-value">28 / {demoDevice.interfaces.length}</div></div></div><div className="observed"><span className="freshness" /> Envanter okuması taze · 14:32:08 · fixture</div></div><div className="detail-section"><div className="detail-heading">Yeteneğe göre erişim</div><div className="detail-grid"><div className="detail-cell"><div className="detail-label">Interfaces read</div><div className="detail-value good">SUPPORTED</div></div><div className="detail-cell"><div className="detail-label">Config write</div><div className="detail-value warn">DISABLED</div></div></div></div></div></aside>
      </div>
      {selectedPort && <PortModal port={selectedPort} onClose={() => setSelectedPort(undefined)} />}
    </main>
  );
}
