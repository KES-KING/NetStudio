import type {
  Device,
  DeviceCompatibility,
  DeviceManagementMode,
  DriverCatalog,
  DriverProfileCatalogEntry,
  DriverTransportSummary,
} from "./contracts";
import { canonicalDriverProfiles, findDriverProfile } from "./driver-catalog";

export type TransportKind = "ssh" | "snmp" | "api";

export const managementModeLabels: Record<DeviceManagementMode, string> = {
  standalone: "Bağımsız yönetim",
  controller_managed: "Controller yönetimli",
  cloud_managed: "Bulut yönetimli",
  local_managed: "Yerel yönetimli",
  unknown: "Yönetim modu bilinmiyor",
};

export const implementationLabels = {
  implemented: "Uygulandı",
  catalog_only: "Planlı · henüz uygulanmadı",
  blocked: "Karar kapısında · engelli",
  unsupported_by_protocol: "Protokol tarafından desteklenmiyor",
  unsupported_by_policy: "Güvenlik politikası tarafından desteklenmiyor",
  retired: "Kullanımdan kaldırıldı",
} as const;

export const verificationLabels = {
  not_tested: "Test edilmedi",
  unit_verified: "Birim testi doğrulandı · fiziksel kabul değil",
  fixture_verified: "Fixture doğrulandı · fiziksel kabul değil",
  transport_lab_validated: "İzole transport laboratuvarında doğrulandı",
  physical_validated: "Fiziksel cihazda doğrulandı",
} as const;

export const releaseLabels = {
  hidden: "Yayınlanmamış",
  experimental: "Deneysel · production desteği değil",
  candidate: "Aday · fiziksel kabul tamamlanmalı",
  supported: "Katalogda desteklenen profil · cihaz kapsamı ayrıca doğrulanır",
} as const;

export const transportStateLabels: Record<
  DriverTransportSummary["state"],
  string
> = {
  implemented: "Kullanılabilir",
  planned: "Planlı",
  blocked: "Karar kapısında",
  unsupported_by_protocol: "Protokol desteklemiyor",
  unsupported_by_policy: "Politika desteklemiyor",
};

export const availabilityReasonLabels: Record<string, string> = {
  snmp_v2c_installation_disabled:
    "Kurulum genelinde SNMPv2c kapalı; NETSTUDIO_ALLOW_SNMP_V2C=1 gerekir",
};

export const capabilityStatusLabels: Record<string, string> = {
  ok: "Başarılı",
  partial: "Kısmi",
  unknown: "Henüz doğrulanmadı",
  unsupported: "Desteklenmiyor",
  permission_denied: "Yetki yetersiz",
  parse_error: "Ayrıştırma hatası",
  timeout: "Zaman aşımı",
  error: "Toplama hatası",
};

export function catalogVendors(catalog?: DriverCatalog): string[] {
  if (!catalog) return [];
  return Array.from(
    new Set(
      canonicalDriverProfiles(catalog).flatMap(
        (profile) => profile.identity.vendors,
      ),
    ),
  ).sort((left, right) => left.localeCompare(right, "tr"));
}

export function profilesForVendor(
  catalog: DriverCatalog | undefined,
  vendor: string,
): DriverProfileCatalogEntry[] {
  if (!catalog || !vendor) return [];
  return canonicalDriverProfiles(catalog)
    .filter((profile) => profile.identity.vendors.includes(vendor))
    .sort(
      (left, right) =>
        Number(right.selectable) - Number(left.selectable) ||
        left.label.localeCompare(right.label, "tr"),
    );
}

export function profileOptionLabel(profile: DriverProfileCatalogEntry): string {
  const status = profile.availability_reason
    ? availabilityReasonLabels[profile.availability_reason] ?? profile.availability_reason
    : implementationLabels[profile.implementation_status];
  return `${profile.label} · ${status}`;
}

export function implementedTransports(
  profile?: DriverProfileCatalogEntry | null,
): TransportKind[] {
  if (!profile) return [];
  return (["ssh", "snmp", "api"] as const).filter(
    (kind) => profile.transports[kind]?.state === "implemented",
  );
}

export function profileForDevice(
  catalog: DriverCatalog | undefined,
  device: Device,
): DriverProfileCatalogEntry | null {
  if (!catalog) return null;
  for (const identifier of [
    device.resolved_profile_id,
    device.configured_profile_id,
    device.resolved_collector,
    device.collector,
  ]) {
    if (!identifier) continue;
    const match = findDriverProfile(catalog, identifier);
    if (match.profile) return match.profile;
  }
  return null;
}

export function needsExplicitProfileChoice(
  status?: DeviceCompatibility["resolution_status"] | null,
): boolean {
  return ["unresolved", "conflict", "manual_resolution_required"].includes(
    status ?? "",
  );
}

export function supportPresentation(
  profile: DriverProfileCatalogEntry | null,
  compatibility: DeviceCompatibility,
): { tone: "neutral" | "warning" | "success"; label: string } {
  if (!profile)
    return { tone: "warning", label: "Kanonik profil henüz belirlenmedi" };
  if (profile.release_status === "supported") {
    const exactPhysicalAcceptance =
      compatibility.acceptance.highest_level === "physical_validated" &&
      compatibility.acceptance.matching_unexpired_records > 0;
    return exactPhysicalAcceptance
      ? { tone: "success", label: "Destekleniyor · fiziksel kapsam eşleşti" }
      : {
          tone: "warning",
          label: "Bu cihaz tuple’ı kabul kapsamı dışında",
        };
  }
  if (profile.release_status === "candidate")
    return {
      tone: "warning",
      label: "Aday · fiziksel kabul tamamlanmadı",
    };
  if (profile.release_status === "experimental")
    return {
      tone: "neutral",
      label: "Deneysel · production desteği değildir",
    };
  return { tone: "neutral", label: "Gizli / yayınlanmamış profil" };
}

export function blankCredentialDraft(_device?: Pick<Device, "credential_configured">) {
  return {
    username: "",
    password: "",
    private_key: "",
    passphrase: "",
  };
}
