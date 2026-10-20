"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { api, ApiError, errorMessage } from "../lib/api";
import { recordActivity } from "../lib/activity";
import type { Job, PhysicalPort, Projection, SSHTicket } from "../lib/contracts";
import {
  displayProjection,
  formatTime,
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
import { DeviceFacts, DeviceInterfaces, DeviceSummary } from "./DeviceFacts";

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
      <DeviceSummary row={row} />
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
      <div className="device-detail-sections">
        <IPTopology row={row} port={selected} />
        <DeviceFacts row={row} />
        <DeviceInterfaces row={row} />
        <CollectionControls device={device} />
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
