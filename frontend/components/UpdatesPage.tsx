"use client";
import { useState } from "react";
import useSWR from "swr";
import { api, errorMessage } from "../lib/api";
import { formatTime } from "../lib/metrics";
import { updateErrors, updatePhases, type UpdateState } from "../lib/updates";

const endpoint = "/api/v1/system/updates";
export default function UpdatesPage() {
  const { data, error, mutate } = useSWR<UpdateState>(endpoint, api, { refreshInterval: 10000 });
  const [busy, setBusy] = useState(false), [notice, setNotice] = useState(""), [failure, setFailure] = useState("");
  const [consent, setConsent] = useState(false);
  async function action(path: string, body?: object, method = "POST") {
    setBusy(true); setFailure(""); setNotice("");
    try { await api(`${endpoint}/${path}`, { method, body: body ? JSON.stringify(body) : undefined }); await mutate(); setNotice(path === "install" ? "Kurulum isteği sunucu güncelleyicisine iletildi." : "Güncelleme bilgileri yenilendi."); }
    catch (e) { const code = e instanceof Error ? e.message : ""; setFailure(updateErrors[code] ?? errorMessage(e)); }
    finally { setBusy(false); }
  }
  if (error) return <p role="alert" className="notice error">{errorMessage(error)}</p>;
  if (!data) return <p role="status">Güncellemeler yükleniyor…</p>;
  const active = data.runs.find((run) => !["succeeded", "failed", "cancelled", "recovery_required"].includes(run.status));
  return <>
    <section className="panel update-overview"><div className="panel-heading"><h2>Güncelleme sistemi</h2><span>{data.repository} · {data.branch}</span></div>
      <div className="update-body">
        <p className={`notice ${data.recovery_required ? "error" : ""}`}>{data.recovery_required ? "Kurtarma gerekiyor. Yeni kurulumlar durduruldu." : active ? updatePhases[active.status] : data.available ? "Yeni güncelleme hazır." : data.installed_revision ? "Yeni commit bildirimi yok. Son kontrol zamanını inceleyin." : "Kurulu commit bilinmiyor; güncel olduğu varsayılmıyor."}</p>
        <dl className="device-facts update-facts"><div><dt>Kurulu commit</dt><dd className="mono">{data.installed_revision?.slice(0, 12) ?? "Doğrulanmadı"}</dd></div>
          <div><dt>main üzerindeki commit</dt><dd>{data.latest_revision ? <a className="mono" href={`${data.repository_url}/commit/${data.latest_revision}`} target="_blank" rel="noopener noreferrer">{data.latest_revision.slice(0, 12)} ↗</a> : "Henüz alınmadı"}</dd></div>
          <div><dt>Son başarılı kontrol</dt><dd>{formatTime(data.checked_at)}</dd></div><div><dt>Sonraki kontrol</dt><dd>{formatTime(data.next_check_at)}</dd></div>
          <div><dt>Sunucu güncelleyicisi</dt><dd>{data.agent_online ? "Bağlı" : "Bağlı değil"}</dd></div><div><dt>Otomatik kurulum</dt><dd>{data.automatic ? "Açık" : "Kapalı"}</dd></div></dl>
        {data.error_code && <p className="notice error" role="alert">{updateErrors[data.error_code] ?? data.error_code}</p>}
        {!data.agent_online && <p className="source-note">Commitler görüntülenebilir; kurulum için sunucuda ayrı güncelleyici yapılandırılmalıdır. API için Docker socket erişimi verilmez. <a href={`${data.repository_url}/blob/main/docs/updates.md`} target="_blank" rel="noopener noreferrer">Kurulum rehberi ↗</a></p>}
        {data.can_manage ? <>
          <label className="update-consent"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />main üzerindeki kodun sunucuda çalıştırılacağını, yedek sonrası servislerin yeniden başlayacağını ve kısa kesinti olacağını anladım.</label>
          <div className="toolbar-actions update-actions"><button disabled={busy} onClick={() => void action("check")}>Güncellemeleri kontrol et</button>
            <button disabled={busy || (!data.automatic && (!consent || !data.agent_online || !data.installed_revision || data.recovery_required))} onClick={() => void action("policy", { automatic: !data.automatic, acknowledge_main_execution: consent }, "PUT")}>{data.automatic ? "Otomatik kurulumu kapat" : "Otomatik kurulumu aç"}</button>
            <button className="primary" disabled={busy || !consent || !data.available || !data.agent_online || !!active || data.recovery_required} onClick={() => void action("install", { revision: data.latest_revision, acknowledge_restart: true })}>Güncellemeyi kur</button></div>
        </> : <p className="source-note">Güncelleme politikası ve kurulum yalnız superadmin tarafından yönetilebilir.</p>}
        <p className="source-note">Otomatik kontrol 10 dakikalık aralıklarla yapılır; manuel kontrol de sunucu hız sınırına uyar. Açık SSH oturumları ve toplama işleri beklenir. Başarısız kurulum aynı commit için otomatik tekrarlanmaz.</p>
        {notice && <p role="status" className="notice">{notice}</p>}{failure && <p role="alert" className="notice error">{failure}</p>}
      </div>
    </section>
    <section className="panel"><div className="panel-heading"><h2>Gelen commitler</h2><a href={`${data.repository_url}/commits/main/`} target="_blank" rel="noopener noreferrer">GitHub üzerinde tümü ↗</a></div>
      <div className="commit-list">{!data.commits.length ? <p>Henüz commit bilgisi alınmadı.</p> : data.commits.map((commit) => <article key={commit.sha}>
        <div className="commit-heading"><a href={commit.url} target="_blank" rel="noopener noreferrer"><strong>{commit.title}</strong> ↗</a><code>{commit.sha.slice(0, 12)}</code></div>
        <p className="source-note">{commit.author} · {formatTime(commit.committed_at)}{commit.sha === data.installed_revision ? " · Kurulu sürüm" : ""}</p>
        <details><summary>Commit açıklaması</summary><p className="commit-description">{commit.description}</p></details>
      </article>)}</div>
    </section>
    <section className="panel"><div className="panel-heading"><h2>Kurulum geçmişi</h2><span>Son 20 işlem</span></div><div className="update-body">
      {!data.runs.length ? <p>Henüz kurulum isteği yok.</p> : <ol className="update-runs">{data.runs.map((run) => <li key={run.id}><strong>{updatePhases[run.status] ?? run.status}</strong><a href={`${data.repository_url}/commit/${run.revision}`} target="_blank" rel="noopener noreferrer"><code>{run.revision.slice(0, 12)} ↗</code></a><span>{formatTime(run.updated_at)} · {run.automatic ? "Otomatik" : "Manuel"}</span>{run.error_code && <p className="notice error">{updateErrors[run.error_code] ?? run.error_code}</p>}</li>)}</ol>}
    </div></section>
  </>;
}
