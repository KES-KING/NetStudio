"use client";
import { useState, type FormEvent } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, errorMessage, requireLogin } from "../lib/api";
import { roleDescriptions, roleLabels } from "../lib/accounts";
import type { UserProfile } from "../lib/contracts";
import { useSession } from "./ConsoleShell";
import { UserAvatar } from "./UserAvatar";
import { UserDirectory } from "./UserDirectory";

export default function AccountPage({ embedded = false }: { embedded?: boolean }) {
  const session = useSession();
  const { mutate: mutateAll } = useSWRConfig();
  const { data: profile, error, mutate } = useSWR<UserProfile>("/api/v1/profile", api, { refreshInterval: 30000 });
  const [notice, setNotice] = useState("");
  async function saved(message: string) {
    setNotice(message);
    await Promise.all([mutate(), mutateAll("/api/v1/session/me")]);
  }
  return (
    <>
      {!embedded && <div className="page-heading"><div><p className="eyebrow">HESAP VE ERİŞİM</p><h1>Hesabım</h1>
        <p>Profil, avatar ve oturum güvenliği{session.permissions.includes("user.manage") ? "; kullanıcı ve yetki yönetimi." : "."}</p></div>
        <span className="status">{session.roles.map((role) => roleLabels[role]).join(" · ")}</span>
      </div>}
      {notice && <p className="notice" role="status">{notice}</p>}
      {error ? <p role="alert" className="notice error">{errorMessage(error)}</p> : !profile ? <p role="status">Profil yükleniyor…</p> : (
        <>
          <div className="profile-grid">
            <ProfileForm key={`${profile.id}:${profile.updated_at}`} profile={profile} onSaved={saved} />
            <AvatarForm profile={profile} onSaved={saved} />
          </div>
          <PasswordForm />
        </>
      )}
      {!embedded && session.permissions.includes("user.manage") && <UserDirectory />}
    </>
  );
}

function ProfileForm({ profile, onSaved }: { profile: UserProfile; onSaved: (message: string) => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api("/api/v1/profile", { method: "PUT", body: JSON.stringify({ display_name: data.get("display_name") }) });
      await onSaved("Profiliniz güncellendi.");
    } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  }
  return (
    <section className="panel" aria-labelledby="profile-title">
      <div className="panel-heading"><h2 id="profile-title">Profilim</h2><span>{roleLabels[profile.role]}</span></div>
      <form className="account-form" onSubmit={submit}>
        <div className="form-grid">
          <label>Kullanıcı adı<input value={profile.username} readOnly autoComplete="username" /></label>
          <label>Görünen ad<input name="display_name" defaultValue={profile.display_name} minLength={1} maxLength={100} required autoComplete="name" /></label>
        </div>
        <p className="field-help">{roleDescriptions[profile.role]}</p>
        <p className="field-help">Yetkili lokasyonlar: <span className="mono">{profile.sites.includes("*") ? "Tüm lokasyonlar (*)" : profile.sites.join(", ")}</span></p>
        <p className="field-help">Kullanıcı adı ve yetki değişikliklerini superadmin yapabilir.</p>
        {error && <p className="notice error" role="alert">{error}</p>}
        <div className="form-actions"><button className="primary" disabled={busy}>{busy ? "Kaydediliyor…" : "Profili kaydet"}</button></div>
      </form>
    </section>
  );
}

function AvatarForm({ profile, onSaved }: { profile: UserProfile; onSaved: (message: string) => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget;
    const file = new FormData(form).get("avatar");
    if (!(file instanceof File) || !file.size) { setError("Bir görsel seçin."); return; }
    if (file.size > 2 * 1024 * 1024) { setError("Avatar dosyası en fazla 2 MB olabilir."); return; }
    setBusy(true); setError("");
    try {
      await api("/api/v1/profile/avatar", { method: "PUT", body: file, headers: { "Content-Type": file.type } });
      form.reset(); await onSaved("Avatarınız güncellendi.");
    } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError("");
    try { await api("/api/v1/profile/avatar", { method: "DELETE" }); await onSaved("Avatar kaldırıldı."); }
    catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  }
  return (
    <section className="panel" aria-labelledby="avatar-title">
      <div className="panel-heading"><h2 id="avatar-title">Avatar</h2><span>İsteğe bağlı</span></div>
      <form className="account-form" onSubmit={upload}>
        <div className="avatar-editor"><UserAvatar id={profile.id} name={profile.display_name} version={profile.avatar_version} large />
          <div><label>Avatar görseli<input name="avatar" type="file" accept="image/png,image/jpeg,image/webp" required aria-describedby="avatar-help" /></label>
          <p id="avatar-help" className="field-help">PNG, JPEG veya WebP · en fazla 2 MB / 2048 × 2048 piksel. Animasyon ve SVG kabul edilmez.</p></div>
        </div>
        <p className="field-help">Görsel 256 piksele küçültülür; EXIF ve diğer metadata kaldırılır. Harici avatar servisi kullanılmaz.</p>
        {error && <p className="notice error" role="alert">{error}</p>}
        <div className="form-actions"><button type="button" onClick={remove} disabled={busy || !profile.avatar_version}>Avatarı kaldır</button>
          <button className="primary" disabled={busy}>{busy ? "İşleniyor…" : "Avatarı yükle"}</button></div>
      </form>
    </section>
  );
}

function PasswordForm() {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget, data = new FormData(form);
    if (data.get("new_password") !== data.get("confirmation")) { setError("Yeni parolalar eşleşmiyor."); return; }
    setBusy(true); setError("");
    try {
      await api("/api/v1/profile/password", { method: "PUT", body: JSON.stringify({ current_password: data.get("current_password"), new_password: data.get("new_password") }) });
      form.reset(); requireLogin("Parolanız değiştirildi ve tüm oturumlarınız kapatıldı. Yeniden giriş yapın.");
    } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  }
  return (
    <section className="panel account-security" aria-labelledby="password-title">
      <div className="panel-heading"><h2 id="password-title">Parola ve oturum güvenliği</h2></div>
      <form className="account-form" onSubmit={submit}>
        <div className="password-grid">
          <label>Mevcut parola<input name="current_password" type="password" required maxLength={1024} autoComplete="current-password" /></label>
          <label>Yeni parola<input name="new_password" type="password" required minLength={12} maxLength={1024} autoComplete="new-password" /></label>
          <label>Yeni parola tekrar<input name="confirmation" type="password" required minLength={12} maxLength={1024} autoComplete="new-password" /></label>
        </div>
        <p className="field-help">En az 12 karakter. Değişiklik tüm uygulama ve SSH oturumlarınızı sonlandırır. Parolalar audit kaydına girmez.</p>
        {error && <p className="notice error" role="alert">{error}</p>}
        <div className="form-actions"><button disabled={busy}>{busy ? "Değiştiriliyor…" : "Parolayı değiştir"}</button></div>
      </form>
    </section>
  );
}
