"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { api, errorMessage } from "../lib/api";
import { recordActivity } from "../lib/activity";
import type { Overview, Projection } from "../lib/contracts";
import {
  displayProjection,
  filterDevices,
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
import { AddDevice } from "./DeviceForms";
import { DevicePanel, PortDetails } from "./DevicePanel";
import { Empty, OperationSummary } from "./OperationSummary";

export default function Dashboard() {
  const router = useRouter(),
    search = useSearchParams(),
    session = useSession();
  const query = search.get("q") ?? "",
    type = search.get("type") ?? "",
    status = search.get("status") ?? "";
  const requested = Number(search.get("minutes") ?? 60),
    minutes = [15, 60, 360, 1440].includes(requested) ? requested : 60;
  const page = Math.max(1, Number(search.get("page")) || 1);
  useEffect(() => {
    const timer = window.setTimeout(() => recordActivity({ action: "inventory.filter", page: "dashboard",
      q: query.slice(0, 160), type, status, minutes }), 1000);
    return () => window.clearTimeout(timer);
  }, [query, type, status, minutes]);
  const { data, error, isLoading, isValidating, mutate } = useSWR<Overview>(
    "/api/v1/overview/summary",
    api,
    { refreshInterval: 15000, keepPreviousData: true },
  );
  const { data: traffic } = useSWR<Record<string, Projection["traffic"]>>(
    `/api/v1/overview/traffic?minutes=${minutes}`, api, { refreshInterval: 60000, keepPreviousData: true },
  );
  const rows = useMemo(
    () =>
      filterDevices(
        (data?.devices ?? []).map((row) => displayProjection({ ...row, traffic: traffic?.[row.device.id] ?? [] }, !!error)),
        query,
        type,
        status,
      ),
    [data, traffic, error, query, type, status],
  );
  const [adding, setAdding] = useState(false);
  const pageCount = Math.max(1, Math.ceil(rows.length / 20)),
    activePage = Math.min(page, pageCount);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(search);
    value ? next.set(key, value) : next.delete(key);
    if (key !== "page") next.delete("page");
    router.replace(`/?${next}`, { scroll: false });
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">OPERASYON MERKEZİ</p>
          <h1>Ağ cihazları</h1>
          <p>Cihaz erişilebilirliği, arayüz trafiği ve port envanteri.</p>
        </div>
        <div className="toolbar-actions">
          <button onClick={() => mutate()} disabled={isValidating}>
            Yenile
          </button>
          {session.permissions.includes("inventory.manage") && (
            <button className="primary" onClick={() => setAdding(true)}>
              Cihaz Ekle
            </button>
          )}
        </div>
      </div>
      <div className="filter-bar">
        <label className="search-field">
          Cihaz ara
          <input
            type="search"
            maxLength={160}
            value={query}
            onChange={(e) => filter("q", e.target.value)}
            placeholder="Cihaz adı veya IP adresi"
          />
        </label>
        <label>
          Cihaz türü
          <select value={type} onChange={(e) => filter("type", e.target.value)}>
            <option value="">Tüm türler</option>
            {Object.entries(typeLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Erişilebilirlik
          <select
            value={status}
            onChange={(e) => filter("status", e.target.value)}
          >
            <option value="">Tüm durumlar</option>
            {Object.entries(reachLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Zaman aralığı
          <select
            value={minutes}
            onChange={(e) => filter("minutes", e.target.value)}
          >
            <option value={15}>Son 15 dakika</option>
            <option value={60}>Son 1 saat</option>
            <option value={360}>Son 6 saat</option>
            <option value={1440}>Son 24 saat</option>
          </select>
        </label>
      </div>
      <p className="refresh-info" role="status">
        {isValidating
          ? "Güncelleniyor…"
          : `Görünüm yenilendi: ${formatTime(data?.generated_at)}`}{" "}
        · 15 sn sorgulama · Grafik ve liste: aynı filtredeki {rows.length} cihaz
      </p>
      {error && (
        <p className="notice error" role="alert">
          {errorMessage(error)}
          {data &&
            " Son alınan görünüm gösteriliyor; güncellik doğrulanamıyor."}
        </p>
      )}
      {isLoading && !data ? (
        <Empty text="Envanter ve gözlemler yükleniyor…" />
      ) : data ? (
        <>
          <OperationSummary rows={rows} minutes={minutes} />
          <section className="inventory-list" aria-label="Cihaz envanteri">
            <div className="section-heading">
              <h2>
                Cihaz envanteri{" "}
                <span className="count-label">{rows.length}</span>
              </h2>
              <span>
                {rows.length
                  ? `${(activePage - 1) * 20 + 1}–${Math.min(activePage * 20, rows.length)}`
                  : "0"}{" "}
                / {rows.length} cihaz
              </span>
            </div>
            {rows.length ? (
              rows
                .slice((activePage - 1) * 20, activePage * 20)
                .map((row) => <DeviceRow key={row.device.id} row={row} />)
            ) : (
              <Empty
                text={
                  data.devices.length
                    ? "Filtrelere uyan cihaz bulunamadı."
                    : "Henüz cihaz eklenmedi. Cihaz Ekle ile başlayın."
                }
              />
            )}
            {pageCount > 1 && (
              <nav className="pagination" aria-label="Cihaz sayfaları">
                <button
                  disabled={activePage === 1}
                  onClick={() => filter("page", String(activePage - 1))}
                >
                  Önceki
                </button>
                <span>
                  {activePage} / {pageCount}
                </span>
                <button
                  disabled={activePage === pageCount}
                  onClick={() => filter("page", String(activePage + 1))}
                >
                  Sonraki
                </button>
              </nav>
            )}
          </section>
        </>
      ) : null}
      {adding && (
        <AddDevice
          onClose={() => setAdding(false)}
          onSaved={(device) => {
            setAdding(false);
            void mutate();
            router.push(`/devices/${device.id}`);
          }}
        />
      )}
    </>
  );
}

function DeviceRow({ row }: { row: Projection }) {
  const [selectedId, setSelectedId] = useState<string>();
  const port = physicalPorts(row).find((p) => p.id === selectedId);
  return (
    <article className="device-row-wrapper">
      <div className="device-row">
        <div className="device-miniature">
          <DevicePanel
            row={row}
            compact
            selectedId={port?.id}
            onSelect={(p) => {
              setSelectedId(p.id === selectedId ? undefined : p.id);
              if (p.id !== selectedId) recordActivity({ action: "port.select", page: "dashboard", device_id: row.device.id, port_id: p.id });
            }}
          />
          <span className="schematic-label">Şematik görünüm</span>
        </div>
        <div className="device-identity">
          <Link href={`/devices/${row.device.id}`} className="device-name">
            {row.device.name}
          </Link>
          <p className="mono">{row.device.management_address}</p>
          <p>
            {typeLabels[row.device.device_type]} ·{" "}
            {[row.device.vendor, row.device.model]
              .filter(Boolean)
              .join(" / ") || "Model belirtilmedi"}
          </p>
          <p className="muted">{portDescription(row)}</p>
        </div>
        <div className="device-state">
          <span className={`status ${row.reachability}`}>
            {reachLabels[row.reachability]}
          </span>
          <span className={`status ${row.health_status}`}>
            Sağlık: {healthLabels[row.health_status]}
          </span>
          <span className="muted">{stateLabels[row.data_state]}</span>
        </div>
        <div className="device-traffic">
          <strong>
            {row.ports.total
              ? `${row.ports.counts.unknown === row.ports.total ? "?" : row.ports.counts.up} / ${row.ports.total}`
              : "Veri yok"}
          </strong>
          <span>
            {row.ports.total && row.ports.counts.unknown === row.ports.total
              ? "Aktif port sayısı bilinmiyor"
              : "aktif fiziksel port"}
          </span>
          <span className="mono">RX {formatRate(row.ports.rx_bps)}</span>
          <span className="mono">TX {formatRate(row.ports.tx_bps)}</span>
        </div>
        <div className="device-actions">
          <Link className="button-link" href={`/devices/${row.device.id}`}>
            Detaylar
          </Link>
          <span>
            Son başarılı gözlem
            <br />
            {formatTime(row.last_success_at)}
          </span>
        </div>
      </div>
      {port && (
        <PortDetails
          row={row}
          port={port}
          onClose={() => setSelectedId(undefined)}
        />
      )}
    </article>
  );
}
