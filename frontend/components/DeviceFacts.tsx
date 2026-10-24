"use client";
import { useMemo, useState, type ReactNode } from "react";
import type { Projection } from "../lib/contracts";
import { formatRate, formatTime, healthLabels, portDescription, stateLabels, typeLabels } from "../lib/metrics";

const number = (value: number | null | undefined, unit = "") => value == null || !Number.isFinite(value)
  ? "Veri yok" : `${value.toLocaleString("tr-TR", { maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ""}`;
const state = (value: boolean | null | undefined) => value == null ? "Bilinmiyor" : value ? "Açık" : "Kapalı";
const profiles: Record<string, string> = { auto: "Otomatik", standard: "Standart", huawei_legacy: "Eski VRP", legacy_sha1: "Eski SSH · SHA-1", legacy_cbc: "Eski SSH · CBC/Group1", advanced: "Gelişmiş" };
const qualities: Record<string, string> = { ok: "Geçerli", partial: "Kısmi", unknown: "Bilinmiyor", unsupported: "Desteklenmiyor", error: "Ölçüm hatası" };
const rateReasons: Record<string, string> = {
  baseline_required: "İkinci sayaç örneği bekleniyor", counter_reset_or_wrap: "Sayaç sıfırlanması veya taşması",
  counter_discontinuity: "Sayaç sürekliliği değişti", counter_epoch_unknown: "Sayaç sürekliliği doğrulanamadı",
  invalid_or_missing_interval: "Geçersiz veya eksik ölçüm aralığı",
};
const collectors: Record<string, string> = {
  external: "Harici gözlem", auto: "Otomatik sürücü", linux_ssh: "Linux · salt okunur SSH",
  huawei_vrp: "Huawei VRP", cisco_ios: "Cisco IOS", cisco_iosxe: "Cisco IOS-XE",
  cisco_nxos: "Cisco NX-OS", juniper_junos: "Juniper Junos",
  aruba_aoscx: "Aruba AOS-CX", hp_procurve: "Aruba AOS-Switch",
  arista_eos: "Arista EOS", hp_comware: "HPE Comware",
  h3c_comware7: "H3C Comware V7", mikrotik_routeros: "MikroTik RouterOS",
  dell_os10: "Dell SmartFabric OS10", dell_force10: "Dell Networking OS9",
  dell_os6: "Dell Networking OS6", extreme_exos: "Extreme Switch Engine",
  extreme_vsp: "Extreme Fabric Engine", extreme_slxos: "Extreme SLX-OS",
  fortinet_fortiswitchos: "Fortinet FortiSwitchOS",
};
function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}

export function DeviceSummary({ row }: { row: Projection }) {
  return <dl className="device-summary" aria-label="Cihaz ölçüm özeti">
    <div><dt>Aktif / toplam port</dt><dd>{row.ports.total ? `${row.ports.counts.unknown === row.ports.total ? "?" : row.ports.counts.up} / ${row.ports.total}` : "Envanter yok"}</dd><small>{row.ports.counts.unknown} bilinmiyor · {row.ports.counts.disabled} idari kapalı</small></div>
    <div><dt>Alınan trafik · RX</dt><dd>{formatRate(row.ports.rx_bps)}</dd><small>{row.ports.measured_interfaces} ölçülen arayüz</small></div>
    <div><dt>Gönderilen trafik · TX</dt><dd>{formatRate(row.ports.tx_bps)}</dd><small>Yalnız ölçüm kapsamındaki arayüzler</small></div>
    <div><dt>Cihaz sağlığı</dt><dd className={`status ${row.health_status}`}>{healthLabels[row.health_status]}</dd><small>{stateLabels[row.data_state]}</small></div>
  </dl>;
}

export function DeviceFacts({ row }: { row: Projection }) {
  const d = row.device, h = row.telemetry?.health;
  return <section className="panel device-facts-panel" aria-label="Teknik bilgiler ve sağlık">
    <div className="panel-heading"><h2>Teknik bilgiler ve sağlık</h2><span>{row.data_state === "current" ? "Güncel gözlem" : "Son bilinen bilgiler"}</span></div>
    <div className="device-fact-columns">
      <section><h3>Cihaz kimliği</h3><dl className="device-facts">
        <Fact label="Üretici / model">{[d.vendor, d.model].filter(Boolean).join(" / ") || "Belirtilmedi"}</Fact>
        <Fact label="Hostname / tür">{d.name} / {typeLabels[d.device_type]}</Fact>
        <Fact label="Site">{d.site || "Belirtilmedi"}</Fact>
        <Fact label="Platform / işletim sistemi">{[d.platform, d.os_version].filter(Boolean).join(" / ") || "Veri yok"}</Fact>
        <Fact label="Seri numarası">{d.serial || "Veri yok"}</Fact>
        <Fact label="Fiziksel envanter">{portDescription(row)}</Fact>
        <Fact label="Arayüz / bileşen">{d.interfaces.length} arayüz · {d.components.length} bileşen</Fact>
      </dl><p className="source-note">Envanter: {formatTime(d.inventory_observed_at)} · {d.inventory_source ?? "Kaynak yok"}</p></section>
      <section><h3>Sağlık ve kaynak kullanımı</h3><dl className="device-facts">
        <Fact label="CPU / RAM">{number(h?.cpu_percent, "%")} / {number(h?.memory_percent, "%")}</Fact>
        <Fact label="Çalışma süresi">{h?.uptime_seconds == null ? "Veri yok" : `${Math.floor(h.uptime_seconds / 86400)} gün ${Math.floor(h.uptime_seconds / 3600) % 24} sa ${Math.floor(h.uptime_seconds / 60) % 60} dk`}</Fact>
        <Fact label="Sıcaklık">{number(h?.temperature_c, "°C")}</Fact>
        <Fact label="Fan / güç kaynağı">{h?.fan || "Veri yok"} / {h?.power_supply || "Veri yok"}</Fact>
        <Fact label="PoE tüketimi">{number(h?.poe_watts, "W")}</Fact>
      </dl>
        <p className="device-health-evaluation">{h?.evaluation ?? (h?.status === "unsupported" ? "Toplayıcı bu sağlık metriğini desteklemiyor." : "Sağlık değerlendirmesi alınmadı. Erişilebilirlik sağlıklı olmayı garanti etmez.")}</p>
        {h?.alerts.length ? <ul className="device-alerts">{h.alerts.map((alert, i) => <li key={i}>{alert}</li>)}</ul> : <p className="muted">{h?.status === "ok" && row.data_state === "current" ? "Kaynak aktif uyarı bildirmedi." : "Aktif uyarı durumu doğrulanmadı."}</p>}
        <p className="source-note">{row.data_state !== "current" ? "Son bilinen sağlık değerleri · " : ""}{formatTime(row.telemetry?.observed_at)} · {row.telemetry?.source ?? "Veri kaynağı yok"}</p>
      </section>
      <section><h3>Bağlantı ve veri güveni</h3><dl className="device-facts">
        <Fact label="Yönetim IP / SSH"><span className="mono">{d.management_address} : {d.ssh_port}</span></Fact>
        <Fact label="Veri toplayıcı">{collectors[d.collector] ?? d.collector}</Fact>
        <Fact label="SSH profili">{profiles[d.ssh_profile ?? "standard"] ?? d.ssh_profile}</Fact>
        <Fact label="Eski algoritma izni">{d.allow_legacy_ssh ? "Bu cihazda izinli" : "Kapalı"}</Fact>
        <Fact label="Kimlik bilgisi">{d.credential_configured ? "Tanımlı · şifreli" : "Tanımlı değil"}</Fact>
        <Fact label="Host anahtarı">{d.host_key_fingerprint ? "Doğrulanmış anahtar kayıtlı" : "Güven kaydı gerekli"}</Fact>
        <Fact label="SNMPv3">{d.snmp_configured ? "Yapılandırılmış" : "Yapılandırılmamış"}</Fact>
        <Fact label="Erişim politikası">{d.read_only ? "Salt okunur" : "Salt okunur kısıtı yok"}</Fact>
      </dl></section>
    </div>
    <details className="device-components"><summary>Chassis / stack / modül envanteri ({d.components.length})</summary>
      {d.components.length ? <ul>{d.components.map((c) => <li key={c.id}><strong>{c.label}</strong> · {c.kind}{c.slot ? ` · Yuva ${c.slot}` : ""}</li>)}</ul> : <p>Bileşen envanteri alınmadı.</p>}
    </details>
  </section>;
}

export function DeviceInterfaces({ row }: { row: Projection }) {
  const [query, setQuery] = useState(""), [page, setPage] = useState(0);
  const samples = useMemo(() => new Map(row.telemetry?.interfaces.map((s) => [s.interface_id, s]) ?? []), [row.telemetry]);
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("tr-TR");
    return row.device.interfaces.filter((i) => {
      const s = samples.get(i.id);
      return `${i.name} ${i.kind} ${s?.addresses.join(" ") ?? ""} ${s?.vrf ?? ""} ${s?.access_vlan ?? ""} ${s?.pvid ?? ""}`.toLocaleLowerCase("tr-TR").includes(term);
    });
  }, [row.device.interfaces, query, samples]);
  const pages = Math.max(1, Math.ceil(filtered.length / 12)), current = Math.min(page, pages - 1);
  return <section className="panel device-interfaces" aria-label="Arayüz ayrıntıları">
    <div className="panel-heading"><div><h2>Arayüz ayrıntıları</h2><p>Fiziksel ve mantıksal arayüzler · {row.device.interfaces.length} kayıt</p></div>
      <label>Arayüz ara<input type="search" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} placeholder="Ad, IP, VLAN veya VRF" /></label>
    </div>
    <p className="source-note">{stateLabels[row.data_state]} · {formatTime(row.telemetry?.observed_at)} · {row.telemetry?.source ?? "Veri kaynağı yok"}{row.data_state !== "current" && " · Satırlardaki değerler son bilinen gözlemdir."}<br />{row.ports.traffic_scope} Hızlar kaynağın bildirdiği ölçüm aralığına aittir; aşağıdaki satırlar ayrıca toplanmaz.</p>
    <div className="device-interface-scroll" tabIndex={0} role="region" aria-label="Yatay kaydırılabilir arayüz tablosu">
      <table><caption className="visually-hidden">Arayüz durumu, adresleme ve trafik ölçümleri</caption>
        <thead><tr>{["Arayüz / tür", "Admin / oper", "IP / VRF", "VLAN / kip", "Kapasite / duplex", "RX / TX", "RX hata / discard", "TX hata / discard", "Ölçüm niteliği"].map((s) => <th key={s} scope="col">{s}</th>)}</tr></thead>
        <tbody>{filtered.slice(current * 12, current * 12 + 12).map((i) => {
          const s = samples.get(i.id);
          return <tr key={i.id}>
            <th scope="row"><span className="mono">{i.name}</span><small>{i.kind}{i.if_index != null ? ` · ifIndex ${i.if_index}` : ""}</small></th>
            <td>{state(s?.admin_up)} / {state(s?.oper_up)}</td>
            <td>{s?.addresses.length ? s.addresses.map((a) => <div key={a} className="mono">{a}</div>) : "Veri yok"}<small>VRF: {s?.vrf ?? "Bildirilmedi"}</small></td>
            <td>{s?.access_vlan ?? s?.pvid ?? "Veri yok"}<small>{s?.vlan_mode && s.vlan_mode !== "unknown" ? s.vlan_mode : "Kip bilinmiyor"}</small></td>
            <td>{formatRate(s?.capacity_bps)}<small>{s?.duplex && s.duplex !== "unknown" ? s.duplex === "full" ? "Tam duplex" : "Yarı duplex" : "Duplex bilinmiyor"}</small></td>
            <td>{formatRate(s?.rx_bps)}<small>{formatRate(s?.tx_bps)}</small></td>
            <td>{number(s?.errors)} / {number(s?.discards)}</td><td>{number(s?.tx_errors)} / {number(s?.tx_discards)}</td>
            <td>{s ? qualities[s.quality] ?? s.quality : "Ölçüm yok"}{s?.rate_interval_seconds != null && <small>{number(s.rate_interval_seconds, "sn")} aralık</small>}{s?.rate_reason && <small>{rateReasons[s.rate_reason] ?? s.rate_reason}</small>}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
    {!filtered.length && <p className="source-note">{query ? "Aramanızla eşleşen arayüz yok." : "Arayüz envanteri henüz alınmadı."}</p>}
    <div className="device-table-pagination"><span role="status">{filtered.length} kayıt · Sayfa {current + 1} / {pages}</span>
      <button disabled={current === 0} onClick={() => setPage(current - 1)}>Önceki arayüzler</button><button disabled={current + 1 >= pages} onClick={() => setPage(current + 1)}>Sonraki arayüzler</button>
    </div>
  </section>;
}
