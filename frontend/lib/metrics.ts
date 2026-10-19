import type {
  Projection,
  PhysicalPort,
  PortState,
  HealthState,
  Reachability,
} from "./contracts";

export const reachLabels: Record<Reachability, string> = {
  reachable: "Erişilebilir",
  unreachable: "Erişilemiyor",
  unknown: "Bilinmiyor",
};
export const portLabels: Record<PortState, string> = {
  up: "Aktif",
  down: "Bağlantı yok",
  disabled: "İdari kapalı",
  unknown: "Bilinmiyor",
};
export const healthLabels: Record<HealthState, string> = {
  ok: "Normal",
  warning: "Uyarı",
  critical: "Kritik",
  unknown: "Bilinmiyor",
  unsupported: "Desteklenmiyor",
};
export const typeLabels: Record<string, string> = {
  switch: "Switch",
  router: "Yönlendirici",
  firewall: "Güvenlik duvarı",
  server: "Sunucu",
  other: "Diğer",
};
export const stateLabels: Record<string, string> = {
  no_data: "Veri yok",
  current: "Güncel gözlem",
  stale: "Son veri güncel değil",
  error: "Veri alma hatası",
  unreachable: "Cihaz erişilemiyor",
};

export function formatTime(value: string | null | undefined) {
  if (!value) return "Veri yok";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}
export function formatRate(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "Veri yok";
  if (value >= 1e9)
    return `${(value / 1e9).toLocaleString("tr-TR", { maximumFractionDigits: 2 })} Gbit/s`;
  if (value >= 1e6)
    return `${(value / 1e6).toLocaleString("tr-TR", { maximumFractionDigits: 2 })} Mbit/s`;
  if (value >= 1e3)
    return `${(value / 1e3).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} kbit/s`;
  return `${value.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} bit/s`;
}
export function physicalPorts(row: Projection) {
  return row.device.physical_ports.filter(
    (p) =>
      !p.parent_port_id && !["console", "management"].includes(p.connector),
  );
}
export function portDescription(row: Projection) {
  const ports = physicalPorts(row);
  if (!ports.length) return "Fiziksel port envanteri henüz alınmadı.";
  const counts = new Map<string, number>();
  for (const port of ports)
    counts.set(port.connector, (counts.get(port.connector) ?? 0) + 1);
  return [...counts]
    .map(
      ([kind, count]) =>
        `${count} ${kind === "unknown" ? "türü bilinmeyen port" : kind.toUpperCase()}`,
    )
    .join(" · ");
}
export function sampleForPort(row: Projection, port: PhysicalPort) {
  const children = row.device.physical_ports.filter(
    (p) => p.parent_port_id === port.id,
  );
  const ids = new Set((children.length ? children : [port]).map((p) => p.id));
  const interfaces = row.device.bindings
    .filter(
      (b) =>
        ids.has(b.physical_port_id) &&
        b.binding_quality === "explicit" &&
        row.device.interfaces.some(
          (i) => i.id === b.interface_id && i.kind === "ethernet",
        ),
    )
    .map((b) => b.interface_id);
  return (
    row.telemetry?.interfaces.filter((s) =>
      interfaces.includes(s.interface_id),
    ) ?? []
  );
}
export function filterDevices(
  rows: Projection[],
  query: string,
  type: string,
  status: string,
) {
  const needle = query.trim().toLocaleLowerCase("tr");
  return rows.filter(
    (row) =>
      (!needle ||
        `${row.device.name} ${row.device.management_address}`
          .toLocaleLowerCase("tr")
          .includes(needle)) &&
      (!type || row.device.device_type === type) &&
      (!status || row.reachability === status),
  );
}
export function displayProjection(
  row: Projection,
  unverified = false,
  at = Date.now(),
): Projection {
  const expired =
    row.telemetry &&
    at - Date.parse(row.telemetry.observed_at) >
      row.telemetry.stale_after_seconds * 1000;
  if (!row.telemetry || (!expired && !unverified)) return row;
  return {
    ...row,
    data_state: "stale",
    reachability: "unknown",
    health_status: "unknown",
    ports: {
      ...row.ports,
      counts: { up: 0, down: 0, disabled: 0, unknown: row.ports.total },
      active_ratio: null,
      rx_bps: null,
      tx_bps: null,
      port_states: Object.fromEntries(
        Object.keys(row.ports.port_states).map((id) => [id, "unknown"]),
      ),
    },
  };
}
export function summarize(rows: Projection[]) {
  const reach: Record<Reachability, number> = {
    reachable: 0,
    unreachable: 0,
    unknown: 0,
  };
  const ports: Record<PortState, number> = {
    up: 0,
    down: 0,
    disabled: 0,
    unknown: 0,
  };
  for (const row of rows) {
    reach[row.reachability]++;
    for (const status of Object.keys(ports) as PortState[])
      ports[status] += row.ports.counts[status];
  }
  const total = Object.values(ports).reduce((a, b) => a + b, 0);
  return {
    reach,
    ports,
    total,
    activeRatio:
      total && ports.unknown < total ? (100 * ports.up) / total : null,
  };
}
