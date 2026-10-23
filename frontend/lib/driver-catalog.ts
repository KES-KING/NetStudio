import type {
  DriverCatalog,
  DriverProfileCatalogEntry,
} from "./contracts";

export type DriverProfileLookup = {
  status:
    | "canonical"
    | "alias"
    | "manual_resolution_required"
    | "unavailable";
  profile: DriverProfileCatalogEntry | null;
};

export function canonicalDriverProfiles(
  catalog: DriverCatalog,
): DriverProfileCatalogEntry[] {
  return Array.isArray(catalog.profiles) ? catalog.profiles : [];
}

export function findDriverProfile(
  catalog: DriverCatalog,
  identifier: string,
): DriverProfileLookup {
  const profiles = canonicalDriverProfiles(catalog);
  const canonical = profiles.find((profile) => profile.id === identifier);
  if (canonical) return { status: "canonical", profile: canonical };

  const alias = catalog.aliases?.find((candidate) => candidate.id === identifier);
  if (!alias) return { status: "unavailable", profile: null };
  if (!alias.target_profile_id)
    return { status: "manual_resolution_required", profile: null };
  return {
    status: "alias",
    profile:
      profiles.find((profile) => profile.id === alias.target_profile_id) ?? null,
  };
}
