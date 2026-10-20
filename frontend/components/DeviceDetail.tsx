"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { api, ApiError, errorMessage } from "../lib/api";
import { recordActivity } from "../lib/activity";
import type { Job, PhysicalPort, Projection, SSHTicket } from "../lib/contracts";
import {
  displayProjection,
  formatRate,
  formatTime,
  healthLabels,
  physicalPorts,
  portDescription,
  reachLabels,
  stateLabels,
  typeLabels,
} from "../lib/metrics";
import { useSession } from "./ConsoleShell";
import { ConnectionSettings, InventoryImport } from "./DeviceForms";
import { DevicePanel } from "./DevicePanel";
import { DevicePanelInspector, PortPopover } from "./DevicePanelInspector";
import { IPTopology } from "./IPTopology";
import { Empty } from "./OperationSummary";
import { SSHWorkspace } from "./SSHWorkspace";
import { CollectionControls } from "./CollectionControls";

export default function DeviceDetail({ id }: { id: string }) {
  const session = useSession();
  const { data, error, isLoading, isValidating, mutate } = useSWR<Projection>(
    `/api/v1/devices/${id}/overview`,
    api,
    { refreshInterval: 15000 },
  );
  const received = data;
  const row = received ? displayProjection(received, !!error) : undefined;
  const [selectedId, setSelectedId] = useState<string>(),
    [settings, setSettings] = useState(false),
    [importing, setImporting] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [portAnchor, setPortAnchor] = useState<HTMLButtonElement>();
  const closePort = useCallback(() => {
    setSelectedId(undefined);
    setPortAnchor(undefined);
  }, [setSelectedId, setPortAnchor]);
  const selectPort = (port: PhysicalPort, anchor: HTMLButtonElement) => {
    setSelectedId(port.id);
    setPortAnchor(anchor);
    recordActivity({ action: "port.select", page: "device", device_id: id, port_id: port.id });
  };
  const openPanel = () => {
    setPortAnchor(undefined);
    setPanelOpen(true);
  };
  const [sshOpen, setSSHOpen] = useState(false),
    [ticket, setTicket] = useState<SSHTicket>(),
    [actionError, setActionError] = useState<string>(),
    [job, setJob] = useState<string>(),
    [busy, setBusy] = useState(false);
  const opening = useRef(false),
    generation = useRef(0);
  const { data: jobState } = useSWR<Job>(
    job ? `/api/v1/jobs/${job}` : null,
    api,
    {
      refreshInterval: (value) =>
        value && ["queued", "running"].includes(value.status) ? 1500 : 0,
    },
  );
  useEffect(() => {
    if (jobState?.status && ["succeeded", "partial"].includes(jobState.status)) void mutate();
  }, [jobState?.status, mutate]);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  async function openSSH() {
    if (opening.current || sshOpen) return;
    opening.current = true;
    setSSHOpen(true);
    setActionError(undefined);
    const current = ++generation.current;
    try {
      const created = await api<SSHTicket>(
        `/api/v1/devices/${id}/ssh-sessions`,
        { method: "POST" },
      );
      if (current !== generation.current) {
        await api(`/api/v1/ssh-sessions/${created.id}`, { method: "DELETE" });
        return;
      }
      setTicket(created);
    } catch (e) {
      if (current === generation.current) setActionError(errorMessage(e));
    } finally {
      opening.current = false;
    }
  }
  function closeSSH() {
    generation.current++;
    opening.current = false;
    if (ticket)
      void api(`/api/v1/ssh-sessions/${ticket.id}`, { method: "DELETE" }).catch(
        () => {},
      );
    setTicket(undefined);
    setSSHOpen(false);
  }
  async function runJob(kind: "polls" | "connection-tests") {
    setBusy(true);
    setActionError(undefined);
    try {
      const result = await api<Job>(`/api/v1/devices/${id}/${kind}`, {
        method: "POST",
      });
      setJob(result.id);
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  if (isLoading) return <Empty text="Cihaz bilgileri yükleniyor…" />;
  if (!row)
    return (
      <>
        <Link href="/">Ağ cihazlarına dön</Link>
        <Empty
          text={
            error
              ? errorMessage(error)
              : "Cihaz bulunamadı veya bu cihaza erişim yetkiniz yok."
          }
        />
      </>
    );
  const selected = physicalPorts(row).find((p) => p.id === selectedId),
    device = row.device;
  return (
    <>
      <nav className="breadcrumb" aria-label="Konum">
        <Link href="/">Ağ cihazları</Link>
        <span>/</span>
        <span>{device.name}</span>
      </nav>
      <div className="page-heading device-heading">
        <div>
          <h1>{device.name}</h1>
          <div className="device-subtitle">
            <span className="mono">{device.management_address}</span>
            <span className={`status ${row.reachability}`}>
              {reachLabels[row.reachability]}
            </span>
            <span>{stateLabels[row.data_state]}</span>
          </div>
          <p>
            Son başarılı gözlem: {formatTime(row.last_success_at)} · Ekran:{" "}
            {formatTime(data?.telemetry?.received_at)}
          </p>
        </div>
        <div className="toolbar-actions">
          <button onClick={() => mutate()} disabled={isValidating}>
            Yenile
          </button>
          {session.permissions.includes("terminal.open") && (
            <button className="primary" onClick={openSSH} disabled={sshOpen}>
              SSH
            </button>
          )}
        </div>
      </div>
      <div className="management-toolbar">
        <span>
          {typeLabels[device.device_type]} · {device.site}
        </span>
        <div className="toolbar-actions">
          {session.permissions.includes("job.create") && (
            <>
              <button
                disabled={
                  busy ||
                  jobState?.status === "running" ||
                  jobState?.status === "queued"
                }
                onClick={() => runJob("connection-tests")}
              >
                Bağlantıyı test et
              </button>
              {device.collector !== "external" && (
                <button
                  disabled={
                    busy ||
                    jobState?.status === "running" ||
                    jobState?.status === "queued"
                  }
                  onClick={() => runJob("polls")}
                >
                  Veri topla
                </button>
              )}
            </>
          )}
          {session.permissions.includes("credential.manage") && (
            <button onClick={() => setSettings(true)}>
              Bağlantı bilgileri
            </button>
          )}
          {session.permissions.includes("inventory.manage") && (
            <button onClick={() => setImporting(true)}>Envanter aktar</button>
          )}
        </div>
      </div>
      {error && (
        <p className="notice error" role="alert">
          {errorMessage(error)} Son görünüm gösteriliyor; güncellik
          doğrulanamıyor.
        </p>
      )}
      {actionError && (
        <p className="notice error" role="alert">
          {actionError}
        </p>
      )}
      {jobState && (
        <p
          className={`notice ${jobState.status === "failed" ? "error" : ""}`}
          role="status"
        >
          İş:{" "}
          {(
            {
              queued: "Sırada",
              running: "Çalışıyor",
              succeeded: "Tamamlandı",
              partial: "Kısmi · eksik grupları inceleyin",
              blocked: "Engellendi",
              cancelled: "İptal edildi",
              failed: "Başarısız",
            } as Record<string, string>
          )[jobState.status] ?? jobState.status}
          {jobState.error_code
            ? ` · ${errorMessage(new ApiError(jobState.error_code, 409))}`
            : ""}{" "}
          · <Link href="/jobs">İş geçmişi</Link>
        </p>
      )}
      {row.data_state !== "current" && (
        <p className="notice warning">
          {stateLabels[row.data_state]}. Son bilinen bilgiler zaman damgasıyla
          gösterilir; güncel sağlık veya kapasite olarak değerlendirilmez.
        </p>
      )}
      <CollectionControls device={device} />
      <div className={`device-workspace ${sshOpen ? "with-terminal" : ""}`}>
        <section className="panel front-panel">
          <div className="panel-heading">
            <h2>Cihaz ön paneli</h2>
            <div className="front-panel-actions">
              <span>{portDescription(row)}</span>
              <button onClick={openPanel} aria-haspopup="dialog">Tam ekran <span aria-hidden="true">⛶</span></button>
            </div>
          </div>
          <DevicePanel
            row={row}
            selectedId={selected?.id}
            onSelect={selectPort}
            onExpand={openPanel}
          />
          <p className="source-note">
            Envanter: {formatTime(device.inventory_observed_at)} ·{" "}
            {device.inventory_source ?? "Kaynak yok"}
            <br />
            Port gözlemi: {formatTime(row.telemetry?.observed_at)} · Portu
            seçerek detayları inceleyin.
          </p>
        </section>
        {sshOpen &&
          (ticket ? (
            <SSHWorkspace
              key={ticket.id}
              ticket={ticket}
              name={device.name}
              onClose={closeSSH}
            />
          ) : (
            <section className="panel ssh-pending">
              <div className="panel-heading">
                <h2>SSH</h2>
                <button onClick={closeSSH}>Kapat</button>
              </div>
              <Empty text={actionError ?? "Oturum hazırlanıyor…"} />
            </section>
          ))}
      </div>
      {!panelOpen && selected && portAnchor && (
        <PortPopover row={row} port={selected} anchor={portAnchor} onClose={closePort} />
      )}
      {panelOpen && (
        <DevicePanelInspector
          row={row}
          selected={selected}
          anchor={portAnchor}
          onSelect={selectPort}
          onClosePort={closePort}
          onClose={() => { setPanelOpen(false); setPortAnchor(undefined); }}
        />
      )}
      <div className="detail-lower">
        <IPTopology row={row} port={selected} />
        <TechnicalInfo row={row} />
      </div>
      {settings && (
        <ConnectionSettings
          device={device}
          onClose={() => setSettings(false)}
          onSaved={() => {
            void mutate();
          }}
        />
      )}
      {importing && (
        <InventoryImport
          device={device}
          onClose={() => setImporting(false)}
          onSaved={() => {
            void mutate();
          }}
        />
      )}
    </>
  );
}

function TechnicalInfo({ row }: { row: Projection }) {
  const d = row.device,
    h = row.telemetry?.health;
  const number = (value: number | null | undefined, unit: string) =>
    value == null
      ? "Veri yok"
      : `${value.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} ${unit}`;
  return (
    <section className="panel technical-panel">
      <div className="panel-heading">
        <h2>Teknik bilgiler ve sağlık</h2>
        <span className={`status ${row.health_status}`}>
          {healthLabels[row.health_status]}
        </span>
      </div>
      <div className="detail-body">
        <dl className="technical-grid">
          <div>
            <dt>Üretici / model</dt>
            <dd>
              {[d.vendor, d.model].filter(Boolean).join(" / ") ||
                "Belirtilmedi"}
            </dd>
          </div>
          <div>
            <dt>Hostname / tür</dt>
            <dd>
              {d.name} / {typeLabels[d.device_type]}
            </dd>
          </div>
          <div>
            <dt>Yönetim IP / SSH portu</dt>
            <dd className="mono">
              {d.management_address} / {d.ssh_port}
            </dd>
          </div>
          <div>
            <dt>Firmware / işletim sistemi</dt>
            <dd>{d.os_version || "Veri yok"}</dd>
          </div>
          {d.serial && (
            <div>
              <dt>Seri numarası</dt>
              <dd className="mono">{d.serial}</dd>
            </div>
          )}
          <div>
            <dt>Fiziksel portlar</dt>
            <dd>{portDescription(row)}</dd>
          </div>
          <div>
            <dt>Aktif / toplam port</dt>
            <dd>
              {row.ports.total
                ? `${row.ports.counts.unknown === row.ports.total ? "Bilinmiyor" : row.ports.counts.up} / ${row.ports.total} · ${row.ports.counts.unknown} bilinmiyor`
                : "Envanter yok"}
            </dd>
          </div>
          <div>
            <dt>Gözlenen RX / TX</dt>
            <dd>
              {formatRate(row.ports.rx_bps)} / {formatRate(row.ports.tx_bps)}
            </dd>
          </div>
          <div>
            <dt>Uptime</dt>
            <dd>
              {h?.uptime_seconds == null
                ? "Veri yok"
                : `${Math.floor(h.uptime_seconds / 86400)} gün ${Math.floor(h.uptime_seconds / 3600) % 24} sa ${Math.floor(h.uptime_seconds / 60) % 60} dk`}
            </dd>
          </div>
          <div>
            <dt>CPU / RAM</dt>
            <dd>
              {number(h?.cpu_percent, "%")} / {number(h?.memory_percent, "%")}
            </dd>
          </div>
          <div>
            <dt>Sıcaklık</dt>
            <dd>{number(h?.temperature_c, "°C")}</dd>
          </div>
          {h?.fan && (
            <div>
              <dt>Fan</dt>
              <dd>{h.fan}</dd>
            </div>
          )}
          {h?.power_supply && (
            <div>
              <dt>Güç kaynağı</dt>
              <dd>{h.power_supply}</dd>
            </div>
          )}
          {h?.poe_watts != null && (
            <div>
              <dt>PoE tüketimi</dt>
              <dd>{number(h.poe_watts, "W")}</dd>
            </div>
          )}
          <div>
            <dt>Kimlik bilgisi</dt>
            <dd>
              {d.credential_configured ? "Tanımlı · şifreli" : "Tanımlı değil"}
            </dd>
          </div>
          <div>
            <dt>Host anahtarı</dt>
            <dd>
              {d.host_key_fingerprint
                ? "Doğrulanmış anahtar kayıtlı"
                : "Güven kaydı gerekli"}
            </dd>
          </div>
        </dl>
        <div className="health-note">
          <h3>Sağlık değerlendirmesi</h3>
          <p>
            {h?.evaluation ??
              (h?.status === "unsupported"
                ? "Toplayıcı bu sağlık metriğini desteklemiyor."
                : "Sağlık değerlendirmesi alınmadı. Erişilebilirlik sağlıklı olmayı garanti etmez.")}
          </p>
          {h?.alerts.length ? (
            <ul>
              {h.alerts.map((alert, i) => (
                <li key={i}>{alert}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              {h?.status === "ok" && row.data_state === "current"
                ? "Kaynak aktif uyarı bildirmedi."
                : "Aktif uyarı durumu doğrulanmadı."}
            </p>
          )}
        </div>
        <p className="source-note">
          {row.data_state !== "current"
            ? "Son bilinen sağlık değerleri · "
            : ""}
          {formatTime(row.telemetry?.observed_at)} ·{" "}
          {row.telemetry?.source ?? "Veri kaynağı yok"}
          <br />
          {row.ports.traffic_scope}
        </p>
      </div>
    </section>
  );
}
