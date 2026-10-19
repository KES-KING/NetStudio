"use client";
import { useMemo } from "react";
import type { PhysicalPort, PortState, Projection } from "../lib/contracts";
import { groupPanelPorts, panelPortBanks } from "../lib/panel-layout";
import {
  formatRate,
  formatTime,
  physicalPorts,
  portLabels,
  sampleForPort,
} from "../lib/metrics";

const linkIndicatorLabels: Record<PortState, string> = {
  up: "UP",
  down: "DOWN",
  disabled: "ADM",
  unknown: "?",
};

function PortGeometry({ kind }: { kind: PhysicalPort["connector"] }) {
  return (
    <svg
      viewBox="0 0 44 32"
      aria-hidden="true"
      className={`port-geometry ${kind}`}
    >
      {kind === "rj45" ? (
        <>
          <path className="port-rim" d="M2 3h40v27H2Z" />
          <path d="M5 7h34v17h-9v4H14v-4H5Z" />
          <path
            className="port-contact"
            d="M11 7v7m3-7v7m3-7v7m3-7v7m3-7v7m3-7v7m3-7v7m3-7v7"
          />
        </>
      ) : kind === "sfp" ? (
        <>
          <path className="port-rim" d="M2 6h40v21H2Z" />
          <path d="M5 9h34v15H5Z" />
          <path className="port-metal" d="M8 21h28M15 27v3h14v-3M2 13h3m34 0h3" />
        </>
      ) : kind === "qsfp" ? (
        <>
          <path className="port-rim" d="M1 4h42v24H1Z" />
          <path d="M4 7h36v18H4Z" />
          <path className="port-metal" d="M7 10h30M7 22h30M16 28v3h12v-3" />
        </>
      ) : (
        <>
          <rect x="4" y="6" width="36" height="22" strokeDasharray="3 2" />
          <path d="M16 17h12" />
        </>
      )}
    </svg>
  );
}

function RackEar() {
  return (
    <div className="rack-ear" aria-hidden="true">
      <svg viewBox="0 0 24 100" preserveAspectRatio="none">
        <rect className="rack-hole-rim" x="4" y="14" width="16" height="11" rx="5" />
        <rect className="rack-hole" x="6" y="16" width="12" height="7" rx="3" />
        <rect className="rack-hole-rim" x="4" y="75" width="16" height="11" rx="5" />
        <rect className="rack-hole" x="6" y="77" width="12" height="7" rx="3" />
      </svg>
    </div>
  );
}

export function DevicePanel({
  row,
  compact = false,
  selectedId,
  onSelect,
}: {
  row: Projection;
  compact?: boolean;
  selectedId?: string;
  onSelect: (port: PhysicalPort) => void;
}) {
  const ports = useMemo(() => physicalPorts(row), [row]);
  const groups = useMemo(
    () => groupPanelPorts(ports, row.device.components),
    [ports, row.device.components],
  );
  const rack = row.device.device_type === "switch";
  return (
    <div className={`device-panel ${compact ? "compact" : ""}`}>
      {!compact && (
        <div className="panel-caption">
          <span>Şematik görünüm · envanter grupları</span>
          <span>{ports.length} fiziksel ağ portu</span>
        </div>
      )}
      {ports.length ? (
        <div
          className="chassis-scroll"
          tabIndex={0}
          aria-label={`${row.device.name} ön paneli, yatay kaydırılabilir`}
        >
          <div className={`chassis ${rack ? "rack-chassis" : ""}`}>
            {rack && <RackEar />}
            <div className="chassis-body">
              <div className="chassis-nameplate">
                <strong className="chassis-name">{row.device.name}</strong>
                <span className="chassis-model">
                  {row.device.model || "Model belirtilmedi"}
                </span>
              </div>
              <div className="chassis-groups">
                {groups.map((group) => (
                  <div
                    className={`port-group ${group.optical ? "optical-group" : ""}`}
                    key={group.id}
                    data-connector={group.connector}
                  >
                    <span className="group-label">{group.title}</span>
                    <div
                      className={`port-banks ${group.connector === "rj45" ? "rj45-banks" : ""}`}
                    >
                      {panelPortBanks(group).map((bank, bankIndex) => (
                        <div
                          className="port-grid port-bank"
                          data-port-bank={bankIndex + 1}
                          key={bank[0]?.id ?? bankIndex}
                        >
                          {bank.map((port) => {
                            const status =
                              row.ports.port_states[port.id] ?? "unknown";
                            return (
                              <button
                                type="button"
                                key={port.id}
                                className={`physical-port connector-${port.connector} ${status} ${selectedId === port.id ? "selected" : ""}`}
                                data-port-id={port.id}
                                aria-pressed={selectedId === port.id}
                                aria-label={`${port.label}, ${portLabels[status]}`}
                                title={`${port.label} · ${port.connector.toUpperCase()} · ${portLabels[status]}`}
                                onClick={() => onSelect(port)}
                              >
                                <span className="port-face">
                                  <PortGeometry kind={port.connector} />
                                  <span className="port-indicator" aria-hidden="true" />
                                </span>
                                <span className="port-marking">
                                  <span className="port-number">{port.label}</span>
                                  <span className="port-link-label" aria-hidden="true">
                                    {linkIndicatorLabels[status]}
                                  </span>
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {rack && <RackEar />}
          </div>
        </div>
      ) : (
        <div className="no-inventory">
          <span>
            {row.device.device_type === "switch" ? "Switch" : "Cihaz"}
          </span>
          <p>Fiziksel port envanteri alınmadı.</p>
        </div>
      )}
      {!compact && (
        <div className="port-legend" aria-label="Port durumları">
          {Object.entries(portLabels).map(([key, label]) => (
            <span className={`status ${key}`} key={key}>
              {label}
            </span>
          ))}
          <span className="selected-key">
            UP: aktif · DOWN: bağlantı yok · ADM: idari kapalı · ?: bilinmiyor
          </span>
          <span className="selected-key">Seçili port: dış çerçeve</span>
        </div>
      )}
    </div>
  );
}

export function PortDetails({
  row,
  port,
  onClose,
}: {
  row: Projection;
  port: PhysicalPort;
  onClose: () => void;
}) {
  const samples = sampleForPort(row, port);
  const childIds = row.device.physical_ports
    .filter((p) => p.parent_port_id === port.id)
    .map((p) => p.id);
  const bindings = row.device.bindings.filter(
    (b) =>
      (childIds.length
        ? childIds.includes(b.physical_port_id)
        : b.physical_port_id === port.id) && b.binding_quality === "explicit",
  );
  const state = row.ports.port_states[port.id] ?? "unknown";
  const stale = row.data_state !== "current";
  return (
    <section
      className="port-details"
      aria-label={`${port.label} port detayları`}
    >
      <div className="panel-heading">
        <h2>
          {port.label}{" "}
          <span className="muted">/ {port.connector.toUpperCase()}</span>
        </h2>
        <button onClick={onClose}>Detayı kapat</button>
      </div>
      <div className="detail-body">
        <p>
          <span className={`status ${state}`}>{portLabels[state]}</span>
          {port.description && <span> · {port.description}</span>}
        </p>
        <p className="muted">
          {bindings
            .map(
              (b) =>
                row.device.interfaces.find((i) => i.id === b.interface_id)
                  ?.name,
            )
            .filter(Boolean)
            .join(" · ") || "Doğrulanmış arayüz eşlemesi yok"}
        </p>
        {!samples.length && (
          <p className="notice">
            Bu port için gözlem verisi yok. Bağlantı durumu bilinmiyor.
          </p>
        )}
        {samples.map((sample) => (
          <div key={sample.interface_id}>
            <h3 className="mono">
              {row.device.interfaces.find((i) => i.id === sample.interface_id)
                ?.name ?? sample.interface_id}
            </h3>
            {stale && (
              <p className="notice warning">
                Son bilinen değerler · {formatTime(row.telemetry?.observed_at)}{" "}
                · Güncel olarak değerlendirilmiyor.
              </p>
            )}
            <dl className="technical-grid">
              <div>
                <dt>İdari durum</dt>
                <dd>
                  {sample.admin_up == null
                    ? "Bilinmiyor"
                    : sample.admin_up
                      ? "Açık"
                      : "Kapalı"}
                </dd>
              </div>
              <div>
                <dt>Bağlantı durumu</dt>
                <dd>
                  {sample.oper_up == null
                    ? "Bilinmiyor"
                    : sample.oper_up
                      ? "Link up"
                      : "Link down"}
                </dd>
              </div>
              <div>
                <dt>Bağlantı kapasitesi</dt>
                <dd>{formatRate(sample.capacity_bps)}</dd>
              </div>
              <div>
                <dt>Duplex</dt>
                <dd>
                  {sample.duplex === "unknown" ? "Bilinmiyor" : sample.duplex}
                </dd>
              </div>
              <div>
                <dt>RX / TX</dt>
                <dd>
                  {formatRate(sample.rx_bps)} / {formatRate(sample.tx_bps)}
                  {sample.rate_interval_seconds != null && (
                    <span className="field-help"> · cihazın son {sample.rate_interval_seconds} saniyelik ortalaması</span>
                  )}
                </dd>
              </div>
              <div>
                <dt>Kalite</dt>
                <dd>
                  {sample.quality === "unsupported"
                    ? "Desteklenmiyor"
                    : sample.quality === "error"
                      ? "Veri alma hatası"
                      : sample.quality === "ok"
                        ? "Doğrulandı"
                        : sample.quality === "partial"
                          ? "Kısmi veri"
                          : "Bilinmiyor"}
                </dd>
              </div>
              {sample.errors != null && (
                <div>
                  <dt>RX hata sayacı</dt>
                  <dd>{sample.errors}</dd>
                </div>
              )}
              {sample.discards != null && (
                <div>
                  <dt>RX discard sayacı</dt>
                  <dd>{sample.discards}</dd>
                </div>
              )}
              {sample.access_vlan != null && (
                <div>
                  <dt>VLAN / mod</dt>
                  <dd>
                    {sample.access_vlan} / {sample.vlan_mode}
                  </dd>
                </div>
              )}
              {sample.tx_errors != null && (
                <div><dt>TX hata sayacı</dt><dd>{sample.tx_errors}</dd></div>
              )}
              {sample.tx_discards != null && (
                <div><dt>TX discard sayacı</dt><dd>{sample.tx_discards}</dd></div>
              )}
              {sample.pvid != null && (
                <div><dt>PVID (access/trunk kanıtı değil)</dt><dd>{sample.pvid}</dd></div>
              )}
              {sample.poe_watts != null && (
                <div>
                  <dt>PoE tüketimi</dt>
                  <dd>{sample.poe_watts} W</dd>
                </div>
              )}
              {sample.transceiver_present != null && (
                <div>
                  <dt>Transceiver</dt>
                  <dd>
                    {sample.transceiver_present ? "Takılı" : "Boş"}
                    {sample.transceiver_model
                      ? ` · ${sample.transceiver_model}`
                      : ""}
                  </dd>
                </div>
              )}
              {!!sample.addresses.length && (
                <div>
                  <dt>IP adresleri</dt>
                  <dd className="mono">{sample.addresses.join(", ")}</dd>
                </div>
              )}
            </dl>
            {sample.rate_reason && (
              <p className="muted">
                Trafik hızı hesaplanamadı:{" "}
                {(
                  {
                    baseline_required: "İkinci sayaç örneği bekleniyor",
                    counter_reset_or_wrap: "Sayaç sıfırlanması veya taşması",
                    counter_discontinuity: "Sayaç sürekliliği değişti",
                    counter_epoch_unknown: "Sayaç sürekliliği doğrulanamadı; cihazın hız ölçümü de bulunmuyor",
                    invalid_or_missing_interval:
                      "Geçersiz veya eksik zaman aralığı",
                  } as Record<string, string>
                )[sample.rate_reason] ?? "Geçerli ölçüm yok"}
                .
              </p>
            )}
          </div>
        ))}
        <p className="source-note">
          Gözlem: {formatTime(row.telemetry?.observed_at)} · Kaynak:{" "}
          {row.telemetry?.source ?? "Veri yok"}. Link up bilgisi fiziksel
          kablo/modül varlığını kanıtlamaz.
        </p>
      </div>
    </section>
  );
}
