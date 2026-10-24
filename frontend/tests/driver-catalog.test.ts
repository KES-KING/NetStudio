import { describe, expect, it } from "vitest";
import {
  canonicalDriverProfiles,
  findDriverProfile,
} from "../lib/driver-catalog";
import {
  blankCredentialDraft,
  catalogVendors,
  implementedTransports,
  needsExplicitProfileChoice,
  profileOptionLabel,
  profilesForVendor,
  supportPresentation,
} from "../lib/compatibility";
import type {
  DeviceCompatibility,
  DriverCatalog,
  DriverProfileCatalogEntry,
} from "../lib/contracts";

const legacy = {
  version: "legacy",
  template_version: "9.3.0",
  drivers: [],
} satisfies DriverCatalog;

const profile = {
  schema_version: 1,
  id: "huawei_vrp_v200",
  profile_revision: 1,
  label: "Huawei VRP V200",
  wave: "P0",
  aliases: ["huawei_vrp"],
  alias_policies: [],
  implementation_status: "implemented",
  verification_status: "fixture_verified",
  release_status: "experimental",
  available: true,
  selectable: true,
  runtime_selection_id: "huawei_vrp",
  identity: {
    vendors: ["Huawei"],
    os_families: ["VRP V200"],
    management_modes: ["standalone"],
    model_patterns: [],
    version_constraints: [],
  },
  transports: {},
  capabilities: {},
  capability_summaries: [],
  acceptance: {
    highest_level: "fixture_verified",
    matching_unexpired_records: 0,
    production_accepted: false,
  },
  tested_versions: [],
  commands: [],
} satisfies DriverProfileCatalogEntry;

describe("additive driver catalog v2 contract", () => {
  it("keeps a legacy response usable when v2 fields are absent", () => {
    expect(canonicalDriverProfiles(legacy)).toEqual([]);
    expect(findDriverProfile(legacy, "huawei_vrp")).toEqual({
      status: "unavailable",
      profile: null,
    });
  });

  it("derives vendor and enabled/disabled profile choices only from catalog v2", () => {
    const planned = {
      ...profile,
      id: "huawei_vrp_v600",
      label: "Huawei VRP V600",
      implementation_status: "catalog_only",
      verification_status: "not_tested",
      release_status: "hidden",
      available: false,
      selectable: false,
      runtime_selection_id: null,
      aliases: [],
    } satisfies DriverProfileCatalogEntry;
    const catalog = {
      ...legacy,
      schema_version: 2,
      profiles: [planned, profile],
    } satisfies DriverCatalog;
    expect(catalogVendors(catalog)).toEqual(["Huawei"]);
    expect(
      profilesForVendor(catalog, "Huawei").map((entry) => [
        entry.id,
        entry.selectable,
      ]),
    ).toEqual([
      ["huawei_vrp_v200", true],
      ["huawei_vrp_v600", false],
    ]);
    expect(implementedTransports({
      ...profile,
      transports: {
        ssh: { state: "implemented", security: [], versions: [], decision_gate: null },
        api: { state: "blocked", security: [], versions: [], decision_gate: "ADR" },
      },
    })).toEqual(["ssh"]);
  });

  it("resolves canonical and compatibility alias entries", () => {
    const catalog = {
      ...legacy,
      schema_version: 2,
      catalog_revision: "test",
      profiles: [profile],
      aliases: [
        {
          id: "huawei_vrp",
          target_profile_id: "huawei_vrp_v200",
          policy: "conditional_identity_match",
          automatic: false,
        },
      ],
    } satisfies DriverCatalog;
    expect(findDriverProfile(catalog, "huawei_vrp_v200")).toEqual({
      status: "canonical",
      profile,
    });
    expect(findDriverProfile(catalog, "huawei_vrp")).toEqual({
      status: "alias",
      profile,
    });
  });

  it("fails closed for an unresolved alias and ignores future additive fields", () => {
    const catalog = {
      ...legacy,
      schema_version: 2,
      profiles: [profile],
      aliases: [
        {
          id: "fortinet",
          target_profile_id: null,
          policy: "manual_resolution_required",
          automatic: false,
          future_alias_field: "ignored",
        },
      ],
      future_top_level_field: { nested: true },
    } as unknown as DriverCatalog;
    expect(canonicalDriverProfiles(catalog)).toEqual([profile]);
    expect(findDriverProfile(catalog, "fortinet")).toEqual({
      status: "manual_resolution_required",
      profile: null,
    });
    expect(needsExplicitProfileChoice("manual_resolution_required")).toBe(true);
  });

  it("does not label a supported profile when the exact acceptance scope misses", () => {
    const supported = { ...profile, release_status: "supported" } satisfies DriverProfileCatalogEntry;
    const compatibility = {
      acceptance: {
        highest_level: "fixture_verified",
        matching_unexpired_records: 0,
        production_accepted: false,
      },
    } as DeviceCompatibility;
    expect(supportPresentation(supported, compatibility)).toEqual({
      tone: "warning",
      label: "Bu cihaz tuple’ı kabul kapsamı dışında",
    });
    expect(supportPresentation(supported, {
      ...compatibility,
      acceptance: {
        highest_level: "physical_validated",
        matching_unexpired_records: 1,
        production_accepted: false,
      },
    })).toEqual({
      tone: "success",
      label: "Destekleniyor · fiziksel kapsam eşleşti",
    });
    expect(supportPresentation(supported, {
      ...compatibility,
      release_decision: {
        decision_id: "decision-s11-rollout",
        payload_sha256: "a".repeat(64),
        signer_key_id: "release-2026",
        signed_at: "2026-10-24T09:00:00Z",
        expires_at: "2027-01-22T09:00:00Z",
        accepted_vendor: "Cisco",
        accepted_model_family: "WS-C2960X-*",
        accepted_exact_model: "WS-C2960X-48FPD-L",
        accepted_hardware_revision: "V02",
        accepted_os_family: "IOS",
        accepted_os_version: "15.2(7)E",
        accepted_management_mode: "standalone",
        accepted_transport: "ssh",
        accepted_security_profile: "ssh2_host_key_pinned_read_only",
        benchmark_status: "pass",
        rollout_stage: "canary",
        blocked_reasons: ["rollout_error_rate_exceeded"],
        production_accepted: false,
      },
    })).toEqual({
      tone: "warning",
      label: "Yayın kapısı kapandı · rollout hata bütçesi aşıldı",
    });
    expect(supportPresentation(
      { ...supported, release_status: "candidate" },
      {
        ...compatibility,
        release_decision: {
          decision_id: "decision-s11-pending-rollout",
          payload_sha256: "b".repeat(64),
          signer_key_id: "release-2026",
          signed_at: "2026-10-24T09:00:00Z",
          expires_at: "2027-01-22T09:00:00Z",
          accepted_vendor: "Cisco",
          accepted_model_family: "WS-C2960X-*",
          accepted_exact_model: "WS-C2960X-48FPD-L",
          accepted_hardware_revision: "V02",
          accepted_os_family: "IOS",
          accepted_os_version: "15.2(7)E",
          accepted_management_mode: "standalone",
          accepted_transport: "ssh",
          accepted_security_profile: "ssh2_host_key_pinned_read_only",
          benchmark_status: "pass",
          rollout_stage: "canary",
          blocked_reasons: ["rollout_general_not_reached"],
          production_accepted: false,
        },
      },
    )).toEqual({
      tone: "warning",
      label: "Aday · rollout general aşamasına ulaşmadı",
    });
  });

  it("never derives credential field values from the device read model", () => {
    expect(blankCredentialDraft({ credential_configured: true })).toEqual({
      username: "",
      password: "",
      private_key: "",
      passphrase: "",
    });
  });

  it("renders the SNMPv2c installation gate without inventing a transport", () => {
    const swos = {
      ...profile,
      id: "mikrotik_swos",
      label: "MikroTik SwOS",
      implementation_status: "implemented",
      availability_reason: "snmp_v2c_installation_disabled",
      available: false,
      selectable: false,
      transports: {
        ssh: { state: "unsupported_by_protocol", security: [], versions: [], decision_gate: null },
        snmp: { state: "unsupported_by_policy", security: ["installation_opt_in"], versions: ["v2c"], decision_gate: "installation_and_device_risk_approval_required" },
      },
    } satisfies DriverProfileCatalogEntry;
    expect(implementedTransports(swos)).toEqual([]);
    expect(profileOptionLabel(swos)).toContain("NETSTUDIO_ALLOW_SNMP_V2C=1");
  });
});
