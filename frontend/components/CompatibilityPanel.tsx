"use client";

import { useRef, useState, type FormEvent } from "react";
import useSWR from "swr";
import { api, errorMessage } from "../lib/api";
import type {
  Device,
  DeviceCompatibility,
  DeviceManagementMode,
  DriverCatalog,
  DriverProfileCatalogEntry,
} from "../lib/contracts";
import {
  capabilityStatusLabels,
  implementationLabels,
  managementModeLabels,
  needsExplicitProfileChoice,
  supportPresentation,
  transportStateLabels,
  verificationLabels,
} from "../lib/compatibility";
import { formatTime } from "../lib/metrics";
import { useSession } from "./ConsoleShell";
import { CatalogProfileFields } from "./DriverProfileFields";

const resolutionLabels: Record<DeviceCompatibility["resolution_status"], string> = {
  unresolved: "Kimlik kanıtı bekleniyor",
  matched: "Kanonik profil eşleşti",
  conflict: "Kimlik kanıtı çelişiyor",
  unsupported: "Desteklenmiyor",
  manual_resolution_required: "Açık profil seçimi gerekli",
  infrastructure_adapter: "Altyapı adaptörü",
  external: "Harici toplayıcı",
};

const transportLabels = { ssh: "SSH", snmp: "SNMP", api: "API" } as const;
const groupLabels: Record<string, string> = {
  fast: "Portlar ve trafik",
  health: "Cihaz sağlığı",
  network: "Ağ tabloları",
  inventory: "Envanter",
};

function ProfileChangeForm({
  device,
  compatibility,
  catalog,
  profile,
  onSaved,
}: {
  device: Device;
  compatibility: DeviceCompatibility;
  catalog: DriverCatalog;
  profile: DriverProfileCatalogEntry | null;
  onSaved: () => Promise<unknown> | unknown;
}) {
  const evidenceVendor = compatibility.identity_evidence.vendor;
  const initialVendor =
    profile?.identity.vendors[0] ??
    catalog.profiles?.find((candidate) =>
      candidate.identity.vendors.includes(evidenceVendor ?? ""),
    )?.identity.vendors[0] ??
    "";
  const [vendor, setVendor] = useState(initialVendor);
  const [profileId, setProfileId] = useState(
    compatibility.configured_profile_id ?? compatibility.resolved_profile_id ?? "",
  );
  const [managementMode, setManagementMode] = useState<DeviceManagementMode>(() =>
    compatibility.management_mode !== "unknown" &&
    profile?.identity.management_modes.includes(compatibility.management_mode)
      ? compatibility.management_mode
      : profile?.identity.management_modes[0] ?? "unknown",
  );
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const errorRef = useRef<HTMLParagraphElement>(null);
  const confirmationRequired =
    needsExplicitProfileChoice(compatibility.resolution_status) ||
    profileId !== compatibility.configured_profile_id ||
    managementMode !== compatibility.management_mode;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      await api(`/api/v1/devices/${device.id}/driver-profile`, {
        method: "PUT",
        body: JSON.stringify({
          configured_profile_id: profileId,
          management_mode: managementMode,
        }),
      });
      setMessage("Kanonik profil kaydedildi; eski bağlantı işleri güvenli biçimde geçersiz kılındı.");
      setConfirmed(false);
      await onSaved();
    } catch (caught) {
      setError(errorMessage(caught));
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="compatibility-profile-editor" open={needsExplicitProfileChoice(compatibility.resolution_status)}>
      <summary>Kanonik profili seç veya değiştir</summary>
      <form onSubmit={submit}>
        <CatalogProfileFields
          catalog={catalog}
          vendor={vendor}
          profileId={profileId}
          managementMode={managementMode}
          onVendorChange={setVendor}
          onProfileChange={setProfileId}
          onManagementModeChange={setManagementMode}
        />
        {confirmationRequired && (
          <label className="checkbox profile-migration-confirmation">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
              required
            />
            Bu seçimin legacy sınıflandırmayı değiştireceğini, açık SSH
            oturumlarını kapatacağını ve bekleyen eski işleri iptal edeceğini
            anlıyorum.
          </label>
        )}
        {error && <p ref={errorRef} tabIndex={-1} role="alert" className="notice error form-error-summary">{error}</p>}
        {message && <p role="status" className="notice success">{message}</p>}
        <button className="primary" disabled={busy || !profileId || (confirmationRequired && !confirmed)}>
          {busy ? "Kaydediliyor…" : "Kanonik profili kaydet"}
        </button>
      </form>
    </details>
  );
}

export function CompatibilityPanel({
  device,
  onChanged,
}: {
  device: Device;
  onChanged: () => Promise<unknown> | unknown;
}) {
  const session = useSession();
  const path = `/api/v1/devices/${device.id}/compatibility`;
  const { data: compatibility, error, mutate } = useSWR<DeviceCompatibility>(path, api);
  const { data: catalog, error: catalogError } = useSWR<DriverCatalog>(
    "/api/v1/driver-catalog",
    api,
  );
  const profileId = compatibility?.resolved_profile_id ?? compatibility?.configured_profile_id;
  const profile = catalog?.profiles?.find((candidate) => candidate.id === profileId) ?? null;

  async function refresh() {
    await Promise.all([mutate(), onChanged()]);
  }

  return (
    <section className="panel compatibility-panel" aria-labelledby="compatibility-title">
      <div className="panel-heading">
        <div>
          <h2 id="compatibility-title">Uyumluluk</h2>
          <p>Kanonik profil, transport ve kanıt kapsamı</p>
        </div>
        <span>{compatibility ? resolutionLabels[compatibility.resolution_status] : "Yükleniyor…"}</span>
      </div>
      {(error || catalogError) && (
        <p className="notice error" role="alert">{errorMessage(error ?? catalogError)}</p>
      )}
      {!compatibility || !catalog ? (
        <p role="status" className="compatibility-loading">Uyumluluk kaydı yükleniyor…</p>
      ) : (
        <div className="compatibility-body">
          {needsExplicitProfileChoice(compatibility.resolution_status) && (
            <p className="notice warning" role="status">
              Legacy veya belirsiz cihaz kimliği sessizce yeniden sınıflandırılmadı.
              Yetkili bir kullanıcı kanonik profili açıkça seçmelidir.
            </p>
          )}
          <div className="compatibility-summary-grid">
            <dl>
              <div><dt>Yapılandırılan profil</dt><dd className="break-text">{compatibility.configured_profile_id ?? "Seçilmedi"}</dd></div>
              <div><dt>Çözümlenen profil</dt><dd className="break-text">{compatibility.resolved_profile_id ?? "Henüz doğrulanmadı"}</dd></div>
              <div><dt>Profil revizyonu</dt><dd>{compatibility.profile_revision ?? "—"}</dd></div>
              <div><dt>Yönetim modu</dt><dd>{managementModeLabels[compatibility.management_mode]}</dd></div>
              <div><dt>Çözüm güveni</dt><dd>%{Math.round(compatibility.resolution_confidence * 100)}</dd></div>
              <div><dt>Son çözüm</dt><dd>{formatTime(compatibility.resolved_at)}</dd></div>
            </dl>
            <div className="compatibility-release">
              <h3>Yayın ve kanıt</h3>
              <p className={`compatibility-support is-${supportPresentation(profile, compatibility).tone}`}>
                {supportPresentation(profile, compatibility).label}
              </p>
              <p>{profile ? implementationLabels[profile.implementation_status] : "Profil yok"}</p>
              <p>{verificationLabels[compatibility.verification_status]}</p>
              <p>
                Eşleşen, süresi geçmemiş kabul kaydı: {compatibility.acceptance.matching_unexpired_records}
              </p>
              <p>
                Production kabulü: {compatibility.acceptance.production_accepted ? "Var" : "Yok"}
              </p>
              {compatibility.release_decision && (
                <details className="compatibility-release-decision">
                  <summary>İmzalı yayın kararı</summary>
                  <p>
                    Kapsam: {compatibility.release_decision.accepted_vendor} · {compatibility.release_decision.accepted_exact_model} · donanım {compatibility.release_decision.accepted_hardware_revision}
                  </p>
                  <p>
                    OS: {compatibility.release_decision.accepted_os_family} · {compatibility.release_decision.accepted_os_version}
                  </p>
                  <p>
                    Yönetim/transport: {managementModeLabels[compatibility.release_decision.accepted_management_mode]} · {transportLabels[compatibility.release_decision.accepted_transport]}
                  </p>
                  <p className="mono break-text">
                    Güvenlik profili: {compatibility.release_decision.accepted_security_profile}
                  </p>
                  <p>Rollout: {compatibility.release_decision.rollout_stage}</p>
                  <p>Geçerlilik: {formatTime(compatibility.release_decision.expires_at)}</p>
                  <p className="mono break-text">
                    SHA-256: {compatibility.release_decision.payload_sha256}
                  </p>
                  {compatibility.release_decision.blocked_reasons.length > 0 && (
                    <ul>
                      {compatibility.release_decision.blocked_reasons.map((reason) => (
                        <li key={reason} className="mono break-text">{reason}</li>
                      ))}
                    </ul>
                  )}
                </details>
              )}
            </div>
          </div>

          {compatibility.resolution_conflicts.length > 0 && (
            <div className="compatibility-conflicts" role="alert">
              <strong>Çözüm çelişkileri</strong>
              <ul>{compatibility.resolution_conflicts.map((conflict) => <li key={conflict} className="mono break-text">{conflict}</li>)}</ul>
            </div>
          )}

          <div className="compatibility-columns">
            <section aria-labelledby="compat-transports-title">
              <h3 id="compat-transports-title">Transportlar</h3>
              {profile ? (
                <ul className="compatibility-status-list">
                  {(Object.entries(profile.transports) as [keyof typeof transportLabels, NonNullable<typeof profile.transports.ssh>][]).map(([kind, transport]) => (
                    <li key={kind}>
                      <strong>{transportLabels[kind]}</strong>
                      <span>{transportStateLabels[transport.state]}</span>
                      {transport.versions.length > 0 && <small className="break-text">{transport.versions.join(", ")}</small>}
                    </li>
                  ))}
                </ul>
              ) : <p className="muted">Profil belirlenmeden transport desteği varsayılmaz.</p>}
            </section>
            <section aria-labelledby="compat-capabilities-title">
              <h3 id="compat-capabilities-title">Capability kanıtı</h3>
              {compatibility.capabilities.length > 0 ? (
                <ul className="compatibility-status-list">
                  {compatibility.capabilities.map((capability) => (
                    <li key={`${capability.transport}:${capability.capability_id}`}>
                      <strong>{groupLabels[capability.capability_id] ?? capability.capability_id}</strong>
                      <span>{capability.stale ? "Eski kanıt" : capabilityStatusLabels[capability.status]}</span>
                      <small>{transportLabels[capability.transport]} · {formatTime(capability.checked_at)}</small>
                      {capability.reason_code && <small className="mono break-text">{capability.reason_code}</small>}
                    </li>
                  ))}
                </ul>
              ) : profile?.capability_summaries.length ? (
                <ul className="compatibility-status-list">
                  {profile.capability_summaries.map((capability) => (
                    <li key={capability.group}>
                      <strong>{groupLabels[capability.group] ?? capability.group}</strong>
                      <span>Henüz cihaz gözlemi yok</span>
                      <small>{verificationLabels[capability.verification_status]}</small>
                    </li>
                  ))}
                </ul>
              ) : <p className="muted">Bu profil için capability beyanı veya cihaz kanıtı yok.</p>}
            </section>
          </div>

          <details className="compatibility-evidence">
            <summary>Redakte kimlik kanıtı</summary>
            {Object.keys(compatibility.identity_evidence).length ? (
              <dl>
                {Object.entries(compatibility.identity_evidence).map(([key, value]) => (
                  <div key={key}><dt>{key}</dt><dd className="break-text">{String(value)}</dd></div>
                ))}
              </dl>
            ) : <p>Kimlik kanıtı henüz toplanmadı.</p>}
          </details>

          {session.permissions.includes("inventory.manage") && (
            <ProfileChangeForm
              key={`${compatibility.configured_profile_id}:${compatibility.management_mode}:${compatibility.resolution_status}`}
              device={device}
              compatibility={compatibility}
              catalog={catalog}
              profile={profile}
              onSaved={refresh}
            />
          )}
        </div>
      )}
    </section>
  );
}
