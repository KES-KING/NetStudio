"use client";
import { useState, type FormEvent } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, errorMessage, requireLogin } from "../lib/api";
import { roleDescriptions, roleLabels } from "../lib/accounts";
import type { CursorPage, UserProfile, UserRole } from "../lib/contracts";
import { useSession } from "./ConsoleShell";
import { Dialog } from "./DeviceForms";
import { UserAvatar } from "./UserAvatar";

export function UserDirectory() {
  const session = useSession();
  const { mutate: mutateAll } = useSWRConfig();
  const [filters, setFilters] = useState({ q: "", role: "" });
  const [cursors, setCursors] = useState<string[]>([]);
  const [editing, setEditing] = useState<UserProfile | "new" | null>(null);
  const [deleting, setDeleting] = useState<UserProfile | null>(null);
  const [notice, setNotice] = useState("");
  const params = new URLSearchParams({ limit: "20" });
  if (filters.q) params.set("q", filters.q);
  if (filters.role) params.set("role", filters.role);
  if (cursors.length) params.set("cursor", cursors[cursors.length - 1]);
  const { data, error, mutate, isLoading } = useSWR<CursorPage<UserProfile>>(`/api/v1/users?${params}`, api);
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    setFilters({ q: String(form.get("q") ?? ""), role: String(form.get("role") ?? "") }); setCursors([]);
  }
  async function saved(message: string) {
    setEditing(null); setDeleting(null); setNotice(message); setCursors([]);
    await Promise.all([mutate(), mutateAll("/api/v1/profile"), mutateAll("/api/v1/session/me")]);
  }
  return (
    <section className="user-directory" aria-labelledby="users-title">
      <div className="section-heading"><div><h2 id="users-title">Kullanıcı yönetimi</h2><p className="field-help">Yalnız superadmin. Yetki değişiklikleri ve silme işlemleri ilgili oturumları sonlandırır.</p></div>
        <button className="primary" onClick={() => setEditing("new")}>Kullanıcı oluştur</button></div>
      <form className="filter-bar" onSubmit={filter}>
        <label className="search-field">Kullanıcı ara<input name="q" type="search" maxLength={160} placeholder="Kullanıcı adı veya görünen ad" /></label>
        <label>Rol filtresi<select name="role"><option value="">Tüm roller</option>{Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <button>Filtrele</button><button type="button" onClick={() => mutate()}>Yenile</button>
      </form>
      {notice && <p className="notice" role="status">{notice}</p>}
      {error ? <p className="notice error" role="alert">{errorMessage(error)}</p> : isLoading ? <p role="status">Kullanıcılar yükleniyor…</p> : !data?.items.length ? <p className="empty-state">Filtreye uyan kullanıcı yok.</p> : (
        <div className="table-scroll"><table><caption className="visually-hidden">Kullanıcılar ve erişim yetkileri</caption>
          <thead><tr><th>Kullanıcı</th><th>Rol</th><th>Lokasyonlar</th><th>Durum</th><th>İşlemler</th></tr></thead>
          <tbody>{data.items.map((user) => <tr key={user.id}>
            <td><div className="user-table-name"><UserAvatar id={user.id} name={user.display_name} version={user.avatar_version} /><div><strong>{user.display_name}</strong><br /><span className="mono">{user.username}</span>{user.id === session.user_id && <span className="muted"> · Siz</span>}</div></div></td>
            <td>{roleLabels[user.role]}</td><td className="user-sites">{user.sites.includes("*") ? "Tüm lokasyonlar" : user.sites.join(", ")}</td>
            <td><span className={`status ${user.enabled ? "reachable" : "disabled"}`}>{user.enabled ? "Aktif" : "Devre dışı"}</span></td>
            <td><div className="row-actions"><button onClick={() => setEditing(user)} aria-label={`${user.username} kullanıcısını düzenle`}>Düzenle</button>
              <button onClick={() => setDeleting(user)} disabled={user.id === session.user_id} aria-label={`${user.username} kullanıcısını sil`}>Sil</button></div></td>
          </tr>)}</tbody></table></div>
      )}
      <nav className="pagination" aria-label="Kullanıcı sayfaları"><button disabled={!cursors.length || isLoading} onClick={() => setCursors((current) => current.slice(0, -1))}>Önceki</button>
        <span>Sayfa {cursors.length + 1}</span><button disabled={!data?.next_cursor || isLoading} onClick={() => data?.next_cursor && setCursors((current) => [...current, data.next_cursor!])}>Sonraki</button></nav>
      {editing && <UserEditor key={editing === "new" ? "new" : editing.id} user={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSaved={saved} />}
      {deleting && <DeleteUser user={deleting} onClose={() => setDeleting(null)} onSaved={saved} />}
    </section>
  );
}

function UserEditor({ user, onClose, onSaved }: { user?: UserProfile; onClose: () => void; onSaved: (message: string) => Promise<void> }) {
  const session = useSession();
  const [role, setRole] = useState<UserRole>(user?.role ?? "viewer");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget, data = new FormData(form);
    if (data.get("password") !== data.get("password_confirmation")) { setError("Parolalar eşleşmiyor."); return; }
    const payload = { username: data.get("username"), display_name: data.get("display_name"), role,
      sites: String(data.get("sites") ?? "").split(",").map((value) => value.trim()).filter(Boolean),
      password: data.get("password"), ...(user ? { enabled: data.get("enabled") === "on" } : {}) };
    setBusy(true); setError("");
    try {
      const result = await api<UserProfile>(user ? `/api/v1/users/${encodeURIComponent(user.id)}` : "/api/v1/users", {
        method: user ? "PATCH" : "POST", body: JSON.stringify(payload),
      });
      form.reset();
      if (result.reauthenticate) { requireLogin("Hesap güvenlik bilgileriniz değişti. Yeniden giriş yapın."); return; }
      await onSaved(user ? "Kullanıcı güncellendi." : "Kullanıcı oluşturuldu.");
    } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  }
  return (
    <Dialog title={user ? "Kullanıcı düzenle" : "Kullanıcı oluştur"} onClose={() => !busy && onClose()}>
      <form className="dialog-body" onSubmit={submit}><div className="form-grid">
        <label>Kullanıcı adı<input name="username" defaultValue={user?.username ?? ""} required maxLength={160} pattern="[A-Za-z0-9][A-Za-z0-9_.@\-]*" autoComplete="off" /></label>
        <label>Görünen ad<input name="display_name" defaultValue={user?.display_name ?? ""} required maxLength={100} autoComplete="off" /></label>
        <label>Yetki rolü<select value={role} onChange={(event) => setRole(event.target.value as UserRole)}>{Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Yetkili lokasyonlar<input name="sites" defaultValue={user?.sites.join(", ") ?? "*"} required maxLength={16000} aria-describedby="sites-help" /></label>
        <label>{user ? "Yeni parola (isteğe bağlı)" : "Parola"}<input name="password" type="password" required={!user} minLength={12} maxLength={1024} autoComplete="new-password" /></label>
        <label>Parola tekrar<input name="password_confirmation" type="password" required={!user} minLength={12} maxLength={1024} autoComplete="new-password" /></label>
      </div>
      <p className="field-help">{roleDescriptions[role]}</p>
      <p id="sites-help" className="field-help">Lokasyonları virgülle ayırın. * tüm lokasyonlara erişim verir. Superadmin kullanıcı ve audit yönetiminde global yetkilidir; cihaz işlemleri lokasyon kapsamını korur.</p>
      {user && <><label className="checkbox"><input name="enabled" type="checkbox" defaultChecked={user.enabled} disabled={user.id === session.user_id} />Hesap aktif</label>
        {user.id === session.user_id && <input type="hidden" name="enabled" value="on" />}
        <p className="field-help">Boş parola mevcut kaydı korur. Rol, lokasyon, kullanıcı adı veya parola değişirse kullanıcı yeniden giriş yapar.</p></>}
      {error && <p className="notice error" role="alert">{error}</p>}
      <div className="form-actions"><button type="button" onClick={onClose} disabled={busy}>Vazgeç</button><button className="primary" disabled={busy}>{busy ? "Kaydediliyor…" : "Kaydet"}</button></div>
      </form>
    </Dialog>
  );
}

function DeleteUser({ user, onClose, onSaved }: { user: UserProfile; onClose: () => void; onSaved: (message: string) => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try { await api(`/api/v1/users/${encodeURIComponent(user.id)}`, { method: "DELETE", body: JSON.stringify({ confirmation_username: data.get("confirmation") }) }); await onSaved("Kullanıcı silindi. Denetim geçmişi korundu."); }
    catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  }
  return <Dialog title="Kullanıcı sil" onClose={() => !busy && onClose()}><form className="dialog-body" onSubmit={submit}>
    <p><strong>{user.username}</strong> hesabı ve avatarı silinecek; açık oturumları kapatılacak. İşlem geri alınamaz. Mevcut audit kayıtları korunur.</p>
    <label className="delete-confirmation">Onay için kullanıcı adı<input name="confirmation" required autoComplete="off" maxLength={160} /></label>
    {error && <p className="notice error" role="alert">{error}</p>}
    <div className="form-actions"><button type="button" disabled={busy} onClick={onClose}>Vazgeç</button><button className="danger" disabled={busy}>{busy ? "Siliniyor…" : "Kullanıcıyı sil"}</button></div>
  </form></Dialog>;
}
