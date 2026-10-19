"use client";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { api, errorMessage } from "../lib/api";
import type { AuditEvent, CursorPage } from "../lib/contracts";
import { useSession } from "./ConsoleShell";

const eventLabels: Record<string, string> = {
  login: "Oturum açma", logout: "Oturum kapatma", "user.created": "Kullanıcı oluşturma",
  "user.updated": "Kullanıcı düzenleme", "user.deleted": "Kullanıcı silme", "user.disabled": "Kullanıcı devre dışı",
  "profile.updated": "Profil güncelleme", "password.changed": "Parola değişikliği",
  "avatar.updated": "Avatar yükleme", "avatar.deleted": "Avatar kaldırma", "device.created": "Cihaz oluşturma",
  "inventory.updated": "Envanter güncelleme", "credentials.updated": "Cihaz kimlik bilgisi güncelleme",
  "credentials.deleted": "Cihaz kimlik bilgisi silme", "host_key.trusted": "Host anahtarı güven kaydı",
  "telemetry.received": "Telemetri alımı", "ssh.created": "SSH oturum isteği", "ssh.started": "SSH bağlantısı",
  "ssh.ended": "SSH oturumu sonu", "job.created": "İş başlatma", "job.finished": "İş sonucu",
  "audit.viewed": "Audit görüntüleme", "request.denied": "Yetki / oturum reddi", "request.failed": "Başarısız istek",
  "request.completed": "Tamamlanan istek", "page.view": "Sayfa görüntüleme", "inventory.filter": "Envanter filtreleme",
  "port.select": "Port seçimi", "topology.select": "Topoloji seçimi", "secrets.rotated": "Sır anahtarı rotasyonu",
  "topology.saved": "Topoloji yerleşimi kaydetme",
};
const outcomeLabels: Record<string, string> = {
  succeeded: "Başarılı", denied: "Reddedildi", failed: "Başarısız", pending: "Bekliyor", connected: "Bağlandı",
  unchanged: "Değişmedi", created: "Oluşturuldu", replaced: "Değiştirildi", session_ended: "Oturum kapatıldı",
  session_revoked: "Oturum iptal edildi", disconnected: "Bağlantı kesildi", idle_timeout: "Boşta kalma süresi doldu",
};
const emptyFilters = { actor: "", event: "", outcome: "", target_id: "", since: "", until: "" };
function exactTime(value: string) {
  return new Date(value).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "medium" });
}

export default function AuditLog() {
  const session = useSession();
  const allowed = session.permissions.includes("audit.read");
  const [filters, setFilters] = useState(emptyFilters), [cursors, setCursors] = useState<string[]>([]);
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const params = new URLSearchParams({ limit: "50" });
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  if (cursors.length) params.set("cursor", cursors[cursors.length - 1]);
  const { data, error, mutate, isLoading, isValidating } = useSWR<CursorPage<AuditEvent>>(
    allowed ? `/api/v1/audit?${params}` : null, api, { refreshInterval: cursors.length ? 0 : 15000 },
  );
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const next = { ...emptyFilters };
    for (const key of Object.keys(next) as (keyof typeof next)[]) {
      const value = String(data.get(key) ?? "").trim();
      next[key] = value && (key === "since" || key === "until") ? new Date(value).toISOString() : value;
    }
    setFilters(next); setCursors([]); setSelected(null);
  }
  return <>
    <div className="page-heading"><div><p className="eyebrow">GÜVENLİK VE İZLENEBİLİRLİK</p><h1>Denetim kayıtları</h1>
      <p>Kullanıcı işlemleri, güvenli gönderilmiş alanlar ve değişiklik öncesi / sonrası değerler.</p></div>
      {allowed && <button onClick={() => mutate()} disabled={isValidating}>Yenile</button>}</div>
    {!allowed ? <p className="notice warning" role="alert">Bu sayfayı yalnız superadmin görüntüleyebilir.</p> : <>
      <p className="audit-policy">Parolalar, anahtarlar, tokenlar, cookie’ler, avatar dosyaları ve ham SSH içeriği kaydedilmez. Tuş vuruşu kaydı tutulmaz. Arayüz etkileşimleri “client-reported” olarak ayrılır.</p>
      <form className="filter-bar audit-filters" onSubmit={filter}>
        <label>Kullanıcı adı / kimliği<input name="actor" maxLength={160} placeholder="Tam kullanıcı adı veya kimlik" /></label>
        <label>Olay<select name="event"><option value="">Tüm olaylar</option>{Object.entries(eventLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Sonuç<select name="outcome"><option value="">Tüm sonuçlar</option>{Object.entries(outcomeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Hedef kimliği<input name="target_id" maxLength={160} placeholder="Kullanıcı veya cihaz kimliği" /></label>
        <label>Başlangıç (yerel saat)<input name="since" type="datetime-local" /></label>
        <label>Bitiş (yerel saat)<input name="until" type="datetime-local" /></label>
        <div className="toolbar-actions"><button className="primary">Filtrele</button><button type="reset" onClick={() => { setFilters(emptyFilters); setCursors([]); setSelected(null); }}>Temizle</button></div>
      </form>
      <p className="refresh-info">{isValidating ? "Güncelleniyor…" : `Bu sayfada ${data?.items.length ?? 0} olay`} · En yeni olay önce · İlk sayfa 15 sn aralıkla yenilenir</p>
      {error ? <p className="notice error" role="alert">{errorMessage(error)}</p> : isLoading ? <p role="status">Denetim kayıtları yükleniyor…</p> : !data?.items.length ? <p className="empty-state">Bu filtrelerde kayıt yok.</p> : (
        <div className="table-scroll"><table className="audit-table"><caption className="visually-hidden">Denetim olayları</caption>
          <thead><tr><th>Zaman</th><th>Kullanıcı</th><th>Olay / hedef</th><th>Sonuç</th><th>İstek</th><th>Ayrıntı</th></tr></thead>
          <tbody>{data.items.map((event) => <tr key={event.id} aria-selected={selected?.id === event.id}>
            <td className="audit-time">{exactTime(event.occurred_at)}</td>
            <td><strong>{event.username || event.user_id}</strong><br /><small>{event.roles?.join(" · ") || "Rol kaydı yok"}</small></td>
            <td><strong>{eventLabels[event.event] ?? event.event}</strong><br /><code>{event.event}</code>{event.target_id && <small className="audit-target">{event.target_type}: {event.target_id}</small>}</td>
            <td><span className={`status ${["failed", "denied"].includes(event.outcome) ? "warning" : ""}`}>{outcomeLabels[event.outcome] ?? event.outcome}</span></td>
            <td>{event.method ?? "—"} {event.status_code ?? ""}<br /><small>{event.remote_address || "Arka plan / eski kayıt"}</small></td>
            <td><button onClick={() => setSelected(selected?.id === event.id ? null : event)} aria-expanded={selected?.id === event.id} aria-controls="audit-detail" aria-label={`${event.event} ${event.id} olay ayrıntıları`}>Detaylar</button></td>
          </tr>)}</tbody></table></div>
      )}
      <nav className="pagination" aria-label="Denetim sayfaları"><button disabled={!cursors.length || isLoading} onClick={() => { setCursors((current) => current.slice(0, -1)); setSelected(null); }}>Önceki</button>
        <span>Sayfa {cursors.length + 1}</span><button disabled={!data?.next_cursor || isLoading} onClick={() => { if (data?.next_cursor) setCursors((current) => [...current, data.next_cursor!]); setSelected(null); }}>Sonraki</button></nav>
      {selected && <section id="audit-detail" className="panel audit-detail" aria-label="Olay ayrıntıları">
        <div className="panel-heading"><h2>{eventLabels[selected.event] ?? selected.event}</h2><button onClick={() => setSelected(null)}>Ayrıntıyı kapat</button></div>
        <div className="account-form"><dl className="audit-metadata">
          <div><dt>Olay kimliği</dt><dd className="mono">{selected.id}</dd></div>
          <div><dt>Kesin zaman (UTC)</dt><dd className="mono">{selected.occurred_at}</dd></div>
          <div><dt>Kullanıcı kimliği</dt><dd className="mono">{selected.user_id}</dd></div>
          <div><dt>Hedef</dt><dd className="mono">{selected.target_type ?? "—"} / {selected.target_id ?? selected.device_id ?? "—"}</dd></div>
          <div><dt>İstek korelasyonu</dt><dd className="mono">{selected.request_id ?? "Eski / arka plan kaydı"}</dd></div>
          <div><dt>HTTP işlemi</dt><dd className="mono">{selected.method ?? "—"} {selected.route ?? "—"} · {selected.status_code ?? "—"}</dd></div>
          <div><dt>İşlem süresi</dt><dd>{selected.duration_ms == null ? "Kaydedilmedi" : `${selected.duration_ms} ms`}</dd></div>
          <div><dt>Uzak adres</dt><dd className="mono">{selected.remote_address ?? "Kaydedilmedi"}</dd></div>
          <div><dt>İstemci tanımı (güvenilmeyen bilgi)</dt><dd>{selected.user_agent || "Kaydedilmedi"}</dd></div>
          <div><dt>İş / SSH oturum kimliği</dt><dd className="mono">{selected.session_id ?? "—"}</dd></div>
        </dl><h3>Güvenli girdi ve değişiklik ayrıntıları</h3>
        {Object.keys(selected.details ?? {}).length ? <pre className="audit-json">{JSON.stringify(selected.details, null, 2)}</pre> : <p className="field-help">Bu olayda ek ayrıntı yok. Eski kayıtların ayrıntıları geriye dönük üretilmez.</p>}
        </div>
      </section>}
    </>}
  </>;
}
