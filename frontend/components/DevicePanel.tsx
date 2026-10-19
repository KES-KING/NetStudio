"use client";
import { useMemo } from "react";
import type { PhysicalPort, Projection } from "../lib/contracts";
import {
  formatRate,
  formatTime,
  physicalPorts,
  portLabels,
  sampleForPort,
} from "../lib/metrics";

function PortGeometry({ kind }: { kind: PhysicalPort["connector"] }) {
  return (
    <svg
      viewBox="0 0 44 32"
      aria-hidden="true"
      className={`port-geometry ${kind}`}
    >
      {kind === "rj45" ? (
        <>
          <path d="M3 7h9V3h20v4h9v22H3Z" />
          <path
            className="port-contact"
            d="M12 9v7m4-7v7m4-7v7m4-7v7m4-7v7m4-7v7"
          />
        </>
      ) : kind === "sfp" ? (
        <>
          <path d="M3 7h38v18H3Z" />
          <path className="port-contact" d="M9 21h26M15 25v4h14v-4" />
        </>
      ) : kind === "qsfp" ? (
        <>
          <path d="M1 5h42v22H1Z" />
          <path className="port-contact" d="M7 10h30M7 22h30M16 27v3h12v-3" />
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
  const ports = useMemo(
    () => physicalPorts(row).sort((a, b) => a.ordinal - b.ordinal),
    [row],
  );
  const groupKey = (port: PhysicalPort) => `${port.component_id}:${port.group}`;
  const groups = [
    ...new Map(
      ports.map((port) => {
        const component = row.device.components.find(
          (c) => c.id === port.component_id,
        );
        const title = [
          component?.kind !== "chassis" ? component?.label : null,
          component?.slot ? `Slot ${component.slot}` : null,
          port.group || "Portlar",
        ]
          .filter(Boolean)
          .join(" · ");
        return [groupKey(port), title];
      }),
    ).entries(),
  ];
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
          <div className="chassis">
            <div className="chassis-groups">
              {groups.map(([group, title]) => (
                <div className="port-group" key={group}>
                  <span className="group-label">{title}</span>
                  <div className="port-grid">
                    {ports
                      .filter((p) => groupKey(p) === group)
                      .map((port) => {
                        const status =
                          row.ports.port_states[port.id] ?? "unknown";
                        return (
                          <button
                            type="button"
                            key={port.id}
                            className={`physical-port ${status} ${selectedId === port.id ? "selected" : ""}`}
                            aria-pressed={selectedId === port.id}
                            aria-label={`${port.label}, ${portLabels[status]}`}
                            title={`${port.label} · ${port.connector.toUpperCase()} · ${portLabels[status]}`}
                            onClick={() => onSelect(port)}
                          >
                            <PortGeometry kind={port.connector} />
                            <span className="port-number">{port.label}</span>
                          </button>
                        );
                      })}
                  </div>
                </div>
              ))}
            </div>
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
