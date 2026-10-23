import { describe, expect, it } from "vitest";
import {
  canonicalDriverProfiles,
  findDriverProfile,
} from "../lib/driver-catalog";
import type {
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
  });
});
