"use client";

import type {
  DeviceManagementMode,
  DriverCatalog,
  DriverProfileCatalogEntry,
} from "../lib/contracts";
import {
  catalogVendors,
  availabilityReasonLabels,
  implementedTransports,
  implementationLabels,
  managementModeLabels,
  profileOptionLabel,
  profilesForVendor,
  releaseLabels,
  transportStateLabels,
  type TransportKind,
  verificationLabels,
} from "../lib/compatibility";

const transportLabels: Record<TransportKind, string> = {
  ssh: "SSH",
  snmp: "SNMPv3",
  api: "Üretici / controller API",
};

export function CatalogProfileFields({
  catalog,
  vendor,
  profileId,
  managementMode,
  onVendorChange,
  onProfileChange,
  onManagementModeChange,
}: {
  catalog?: DriverCatalog;
  vendor: string;
  profileId: string;
  managementMode: DeviceManagementMode;
  onVendorChange: (vendor: string) => void;
  onProfileChange: (profileId: string) => void;
  onManagementModeChange: (mode: DeviceManagementMode) => void;
}) {
  const profiles = profilesForVendor(catalog, vendor);
  const selected = profiles.find((profile) => profile.id === profileId);
  const unavailable = profiles.filter((profile) => !profile.selectable);
  const vendors = catalogVendors(catalog);

  return (
    <fieldset className="profile-selector">
      <legend>Kanonik cihaz profili</legend>
      <p className="field-help" id="profile-flow-help">
        Üretici, işletim sistemi profili ve yönetim modu sırasıyla seçilir.
        Seçenekler canlı sürücü kataloğundan gelir; planlı veya engelli profiller
        bilgi amacıyla görünür fakat seçilemez.
      </p>
      <div className="form-grid profile-flow" aria-describedby="profile-flow-help">
        <label>
          Üretici
          <select
            name="catalog_vendor"
            value={vendor}
            onChange={(event) => {
              onVendorChange(event.target.value);
              onProfileChange("");
              onManagementModeChange("unknown");
            }}
            required
            disabled={!catalog}
          >
            <option value="">{catalog ? "Üretici seçin" : "Katalog yükleniyor…"}</option>
            {vendors.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label>
          İşletim sistemi profili
          <select
            name="configured_profile_id"
            value={profileId}
            onChange={(event) => {
              const id = event.target.value;
              const profile = profiles.find((candidate) => candidate.id === id);
              onProfileChange(id);
              onManagementModeChange(profile?.identity.management_modes[0] ?? "unknown");
            }}
            required
            disabled={!vendor}
            aria-describedby="profile-selection-status"
          >
            <option value="">{vendor ? "Profil seçin" : "Önce üretici seçin"}</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id} disabled={!profile.selectable}>
                {profileOptionLabel(profile)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Yönetim modu
          <select
            name="management_mode"
            value={managementMode}
            onChange={(event) => onManagementModeChange(event.target.value as DeviceManagementMode)}
            required
            disabled={!selected}
          >
            {!selected && <option value="unknown">Önce profil seçin</option>}
            {selected?.identity.management_modes.map((mode) => (
              <option key={mode} value={mode}>{managementModeLabels[mode]}</option>
            ))}
          </select>
        </label>
      </div>
      <div id="profile-selection-status" className="profile-selection-status" aria-live="polite">
        {selected ? (
          <>
            <strong>{selected.label}</strong>
            <span>{implementationLabels[selected.implementation_status]}</span>
            <span>{verificationLabels[selected.verification_status]}</span>
            <span>{releaseLabels[selected.release_status]}</span>
            <span className="mono break-text">{selected.id}@{selected.profile_revision}</span>
          </>
        ) : (
          <span>Henüz kanonik profil seçilmedi.</span>
        )}
      </div>
      {unavailable.length > 0 && (
        <details className="unavailable-profiles">
          <summary>Bu üreticide henüz seçilemeyen profiller ({unavailable.length})</summary>
          <ul>
            {unavailable.map((profile) => (
              <li key={profile.id}>
                <strong>{profile.label}</strong> · {profile.availability_reason
                  ? availabilityReasonLabels[profile.availability_reason] ?? profile.availability_reason
                  : implementationLabels[profile.implementation_status]}
                {profile.operator_guidance && <small>{profile.operator_guidance}</small>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </fieldset>
  );
}

export function TransportPicker({
  profile,
  value,
  onChange,
}: {
  profile: DriverProfileCatalogEntry | null;
  value: TransportKind | "";
  onChange: (transport: TransportKind) => void;
}) {
  const available = implementedTransports(profile);
  return (
    <fieldset className="transport-selector">
      <legend>Bağlantı kanalı ve kimlik bilgisi</legend>
      {!profile ? (
        <p className="field-help">Kullanılabilir kanalları görmek için profil seçin.</p>
      ) : (
        <>
          <div className="transport-options" role="radiogroup" aria-label="Bağlantı kanalı">
            {(["ssh", "snmp", "api"] as const).map((kind) => {
              const transport = profile.transports[kind];
              if (!transport) return null;
              const enabled = transport.state === "implemented";
              return (
                <label key={kind} className={`transport-option ${enabled ? "" : "is-disabled"}`}>
                  <input
                    type="radio"
                    name="credential_transport"
                    value={kind}
                    checked={value === kind}
                    disabled={!enabled}
                    onChange={() => onChange(kind)}
                  />
                  <span><strong>{kind === "snmp" && transport.versions.includes("v2c") ? "SNMPv2c" : transportLabels[kind]}</strong><small>{transportStateLabels[transport.state]}</small></span>
                </label>
              );
            })}
          </div>
          {!available.length && (
            <p className="notice warning">Bu profil için uygulanmış bir bağlantı kanalı yoktur.</p>
          )}
          {profile.operator_guidance && (
            <p className="notice warning">{profile.operator_guidance}</p>
          )}
        </>
      )}
    </fieldset>
  );
}
