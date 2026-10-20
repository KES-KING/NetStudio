"use client";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { api, ApiError, errorMessage } from "../lib/api";
import type { Device, Job } from "../lib/contracts";
import { formatTime } from "../lib/metrics";
import { useSession } from "./ConsoleShell";

type Group = { quality: string; observed_at: string | null; attempted_at: string; source: string;
  attempted_source?: string | null; parser_version: string; reason: string | null; stale_after_seconds: number;
  diagnostics: Record<string, string>; fields: Record<string, string> };
type Polling = { settings: { enabled: boolean; fast_seconds: number; health_seconds: number;
  network_seconds: number; inventory_seconds: number; preferred_source: string };
  state: { last_attempt_at?: string; last_success_at?: string; last_error?: string; effective_intervals?: Record<string, number> };
  due_at: string; generated_at: string; paused_reason: string | null; readiness: string; worker_available: boolean;
  groups: Record<string, Group>; negotiated: Record<string, string> | null };
const labels: Record<string, string> = { fast: "Portlar ve trafik", health: "Cihaz sağlığı", network: "Ağ tabloları", inventory: "Envanter" };
const qualities: Record<string, string> = { ok: "Başarılı", partial: "Kısmi", unsupported: "Desteklenmiyor",
  permission_denied: "Yetki yetersiz", parse_error: "Ayrıştırma hatası", timeout: "Zaman aşımı", error: "Hata", unknown: "Henüz ölçülmedi" };

export function CollectionControls({ device }: { device: Device }) {
  const session = useSession();
  const path = `/api/v1/devices/${device.id}/polling`;
  const { data, error, mutate } = useSWR<Polling>(path, api, { refreshInterval: 15000 });
  const [saving, setSaving] = useState(false), [failure, setFailure] = useState<string>();
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setSaving(true); setFailure(undefined);
    try {
      await api(path, { method: "PUT", body: JSON.stringify({
        enabled: values.get("enabled") === "on", preferred_source: values.get("preferred_source"),
        ...Object.fromEntries(Object.keys(labels).map(g => [g + "_seconds", Number(values.get(g + "_seconds"))])),
      }) });
      await mutate();
    } catch (e) { setFailure(errorMessage(e)); } finally { setSaving(false); }
  }
  return <section className="panel collection-controls" aria-label="Otomatik veri toplama">
    <div className="panel-heading"><h2>Otomatik veri toplama</h2>
      <span>{data?.paused_reason ? "Duraklatıldı" : data?.settings.enabled ? "Etkin" : "Kapalı"}</span></div>
    {error && <p role="alert">{errorMessage(error)}</p>}
    {!data ? <p>Toplama durumu yükleniyor…</p> : <>
      <p className="field-help">Son başarı: {formatTime(data.state.last_success_at ?? null)} · Son deneme: {formatTime(data.state.last_attempt_at ?? null)}
        {" · "}Sonraki kontrol: {data.settings.enabled && !data.paused_reason ? formatTime(data.due_at) : "—"}</p>
      {!data.worker_available && <p className="notice warning">Toplayıcı worker hazır değil. İşler kalıcı kuyrukta bekler.</p>}
      {data.readiness !== "ready" && data.readiness !== "external" && <p className="notice warning">{errorMessage(new ApiError(data.readiness, 409))}</p>}
      {data.paused_reason && <p className="notice warning">{errorMessage(new ApiError(data.paused_reason, 409))} Ayarları düzelttikten sonra kaydederek yeniden başlatın.</p>}
      <p className="field-help">Port ölçümü hedefi: {data.settings.fast_seconds} sn · Etkin: {data.state.effective_intervals?.fast ?? "Henüz ölçülmedi"}
        {data.state.effective_intervals?.fast ? " sn" : ""}</p>
      <details><summary>Ölçüm grupları ve veri kalitesi</summary>
      <div className="table-scroll"><table><thead><tr><th>Veri grubu</th><th>İstenen / etkin</th><th>Son doğru ölçüm</th><th>Durum</th></tr></thead>
        <tbody>{Object.entries(labels).map(([group, label]) => {
          const info = data.groups[group], target = data.settings[(group + "_seconds") as keyof Polling["settings"]];
          return <tr key={group}><td>{label}</td><td>{String(target)} / {data.state.effective_intervals?.[group] ?? "—"} sn</td>
            <td>{formatTime(info?.observed_at ?? null)}</td><td>{info?.observed_at && Date.parse(data.generated_at) - Date.parse(info.observed_at) > info.stale_after_seconds * 1000 ? "Eski · " : ""}
              {qualities[info?.quality ?? "unknown"] ?? info?.quality}
              {info && <details><summary>Kaynak ve eksik alanlar</summary><p>{info.source} · {info.parser_version}</p>
                <p>Son deneme: {formatTime(info.attempted_at)}{info.attempted_source ? ` · ${info.attempted_source}` : ""}</p>
                {info.reason && <p>{errorMessage(new ApiError(info.reason, 409))}</p>}
                {Object.entries(info.diagnostics).map(([name, q]) => <p key={name}>{name}: {qualities[q] ?? q}</p>)}
                {Object.entries(info.fields).filter(([, q]) => q !== "ok").map(([name, q]) => <p key={name}>{name}: {qualities[q] ?? q}</p>)}
              </details>}</td></tr>;
        })}</tbody></table></div></details>
      <p className="field-help">Eski SSH en az 60 sn. Yanıt süresi, CPU ve hata beklemesi etkin aralığı uzatabilir. CLI ortalama hızının kendi ölçüm penceresi korunur.</p>
      {session.permissions.includes("job.create") && <details><summary>Toplama politikasını düzenle</summary>
        <form onSubmit={save} key={JSON.stringify(data.settings)}>
          <label className="checkbox"><input name="enabled" type="checkbox" defaultChecked={data.settings.enabled} />Otomatik toplamayı etkinleştir</label>
          <div className="form-grid">{Object.entries(labels).map(([group, label]) => <label key={group}>{label} (saniye)
            <input name={group + "_seconds"} type="number" required min={{ fast: 30, health: 120, network: 300, inventory: 600 }[group]}
              max={group === "fast" ? 3600 : 86400} defaultValue={Number(data.settings[(group + "_seconds") as keyof Polling["settings"]])} /></label>)}
            <label>Hızlı ölçüm kaynağı<select name="preferred_source" defaultValue={data.settings.preferred_source}>
              <option value="auto">Otomatik · kayıtlıysa SNMPv3</option><option value="ssh">SSH</option><option value="snmp">SNMPv3</option>
            </select></label></div>
          <button disabled={saving}>Toplama ayarlarını kaydet</button>
        </form></details>}
      {failure && <p role="alert" className="notice error">{failure}</p>}
    </>}
  </section>;
}

type Candidate = { id: string; fingerprint: string; public_key: string; previous_fingerprint: string | null; profile: string; expires_at: string };
export function HostDiscovery({ device, onSaved }: { device: Device; onSaved: () => void }) {
  const [job, setJob] = useState<string>(), [candidateId, setCandidateId] = useState<string>();
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState<string>(), [message, setMessage] = useState<string>();
  const { data: state } = useSWR<Job>(job ? `/api/v1/jobs/${job}` : null, api,
    { refreshInterval: v => v && ["queued", "running"].includes(v.status) ? 1000 : 0 });
  const { data: candidate, error } = useSWR<Candidate>(state?.status === "succeeded" && candidateId ?
    `/api/v1/devices/${device.id}/host-key-candidates/${candidateId}` : null, api);
  async function discover() {
    setBusy(true); setFailure(undefined); setMessage(undefined); setJob(undefined); setCandidateId(undefined);
    try {
      const result = await api<{ job_id: string; candidate_id: string }>(`/api/v1/devices/${device.id}/host-key-discoveries`, { method: "POST" });
      setJob(result.job_id); setCandidateId(result.candidate_id);
    } catch (e) { setFailure(errorMessage(e)); } finally { setBusy(false); }
  }
  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setFailure(undefined);
    try {
      await api(`/api/v1/devices/${device.id}/host-key`, { method: "PUT", body: JSON.stringify({
        candidate_id: candidateId, replace_existing: !!device.host_key_fingerprint,
      }) });
      setJob(undefined); setCandidateId(undefined); setMessage("Host anahtarı onaylandı. Bağlantıyı test edip ilk veriyi toplayabilirsiniz."); onSaved();
    } catch (e) { setFailure(errorMessage(e)); } finally { setBusy(false); }
  }
  return <fieldset><legend>SSH anahtarını otomatik getir</legend>
    <p className="field-help">Keşif sırasında parola gönderilmez. Fingerprint’i cihaz konsolu veya güvenilir yönetici kaydıyla karşılaştırın. Bulunan anahtarı 10 dakika içinde onaylayın; güven kaydı kalıcıdır. Değişen anahtar bağlantıyı durdurur.</p>
    <button type="button" disabled={busy || !!state && ["queued", "running"].includes(state.status)} onClick={discover}>Anahtarı bul ve bağlantıyı hazırla</button>
    {state && ["queued", "running"].includes(state.status) && <p role="status">Anahtar keşfi kuyrukta / çalışıyor…</p>}
    {state?.error_code && <p role="alert">{errorMessage(new ApiError(state.error_code, 409))}</p>}
    {candidate && <form onSubmit={approve}>
      {candidate.previous_fingerprint && <p className="mono break-text">Önceki: {candidate.previous_fingerprint}</p>}
      <p className="mono break-text">Bulunan: {candidate.fingerprint}</p>
      <p>Profil: {candidate.profile} · Son onay zamanı: {formatTime(candidate.expires_at)}</p>
      <details><summary>Public host anahtarı</summary><pre className="break-text">{candidate.public_key}</pre></details>
      <label className="checkbox"><input type="checkbox" required />
        Fingerprint’i güvenilir kaynaktan doğruladım{device.host_key_fingerprint ? "; kayıtlı anahtarın değiştirilmesini onaylıyorum." : "."}</label>
      <button className="primary" disabled={busy}>Anahtarı onayla</button>
    </form>}
    {(failure || error) && <p className="notice error" role="alert">{failure ?? errorMessage(error)}</p>}
    {message && <p role="status">{message}</p>}
  </fieldset>;
}

export function SNMPSettings({ device, onSaved }: { device: Device; onSaved: () => void }) {
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState<string>(), [protocol, setProtocol] = useState("sha256");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget, values = new FormData(form);
    setBusy(true); setFailure(undefined);
    try {
      await api(`/api/v1/devices/${device.id}/snmp-credentials`, { method: "PUT", body: JSON.stringify({
        username: values.get("username"), port: Number(values.get("port")), context: values.get("context"),
        auth_protocol: protocol, privacy_protocol: "aes128", auth_password: values.get("auth_password"),
        privacy_password: values.get("privacy_password"), legacy_auth_confirmed: values.get("legacy_auth_confirmed") === "on",
      }) }); form.reset(); onSaved();
    } catch (e) { setFailure(errorMessage(e)); } finally { setBusy(false); }
  }
  return <details><summary>İsteğe bağlı SNMPv3 · {device.snmp_configured ? "Tanımlı" : "Tanımlı değil"}</summary>
    <p className="field-help">Yalnız authPriv. Cihazda SNMP açılmaz; mevcut salt okunur kullanıcınızı girin. SNMPv1/v2c’ye geçiş yapılmaz.</p>
    <form onSubmit={save}><div className="form-grid">
      <label>SNMP kullanıcı adı<input name="username" required maxLength={32} autoComplete="off" /></label>
      <label>SNMP portu<input name="port" type="number" min={1} max={65535} defaultValue={161} required /></label>
      <label>SNMP context<input name="context" maxLength={128} /></label>
      <label>Kimlik doğrulama algoritması<select aria-label="Kimlik doğrulama algoritması" value={protocol} onChange={e => setProtocol(e.target.value)}>
        <option value="sha256">SHA-256 / AES-128</option><option value="sha1">Eski SHA-1 / AES-128</option></select></label>
      <label>SNMP doğrulama parolası<input name="auth_password" type="password" minLength={8} maxLength={128} autoComplete="new-password" required /></label>
      <label>SNMP gizlilik parolası<input name="privacy_password" type="password" minLength={8} maxLength={128} autoComplete="new-password" required /></label>
    </div>{protocol === "sha1" && <label className="checkbox"><input name="legacy_auth_confirmed" type="checkbox" required />Bu cihaz için eski SHA-1 kullanımını onaylıyorum.</label>}
      <button disabled={busy}>SNMPv3 bilgilerini kaydet</button>
      {failure && <p role="alert">{failure}</p>}
    </form></details>;
}
