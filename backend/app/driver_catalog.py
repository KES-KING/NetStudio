"""Backward-compatible facade over the typed, code-owned driver registry."""
from dataclasses import asdict
import os

from .driver_profiles import (
    CATALOG_REVISION,
    AOSCX,
    AOSS,
    DATA_CONTRACT,
    DRIVER_VERSION,
    EOS,
    GROUPS,
    H3C_COMWARE7,
    HPE_COMWARE,
    IOS,
    IOSXE,
    JUNOS,
    NTC_VERSION,
    NXOS,
    REFERENCES,
    REGISTRY,
    ROUTEROS,
    VRP,
    AcceptanceSummary,
    Command,
    adapter_catalog_entry,
    commands,
    profile_catalog_entry,
)


# Public compatibility names used by collectors and existing tests.
VERSION = DRIVER_VERSION
CAPABILITIES = DATA_CONTRACT


def _legacy_validation(level: str) -> str:
    return {
        "not_tested": "experimental",
        "unit_verified": "experimental",
        "fixture_verified": "fixture_tested",
        "transport_lab_validated": "lab_validated",
        "physical_validated": "physical_validated",
    }[level]


# Runtime collectors include every implemented canonical profile. Legacy
# bindings remain the source of the v1 projection and preserve its order/IDs.
DRIVERS = {}
PLANNED = {}
for binding in REGISTRY.legacy_bindings:
    if not binding.available:
        PLANNED[binding.id] = binding.label
        continue
    if binding.adapter_id:
        adapter = REGISTRY.adapter(binding.adapter_id)
        DRIVERS[binding.id] = (
            binding.label,
            (),
            list(adapter.tested_versions),
            _legacy_validation(adapter.verification_status),
        )
        continue
    profile = REGISTRY.profile(binding.profile_id)
    DRIVERS[binding.id] = (
        binding.label,
        profile.commands,
        list(profile.tested_versions),
        _legacy_validation(profile.verification_status),
    )

for profile in REGISTRY.profiles:
    if (
        profile.implementation_status == "implemented"
        and profile.runtime_driver_id not in DRIVERS
    ):
        DRIVERS[profile.runtime_driver_id] = (
            profile.label,
            profile.commands,
            list(profile.tested_versions),
            _legacy_validation(profile.verification_status),
        )


def _profile_capabilities(profile_id: str) -> dict[str, list[str]]:
    profile = REGISTRY.profile(profile_id)
    return {**{group: [] for group in GROUPS}, **{
        capability.group: list(capability.fields)
        for capability in profile.capabilities
    }}


SUPPORTED = {}
for identifier in DRIVERS:
    adapter = REGISTRY.adapter(identifier)
    if adapter:
        SUPPORTED[identifier] = {**{group: [] for group in GROUPS}, **{
            capability.group: list(capability.fields)
            for capability in adapter.capabilities
        }}
        continue
    profile = REGISTRY.runtime_profile(identifier)
    SUPPORTED[identifier] = _profile_capabilities(profile.id)


def legacy_catalog() -> dict:
    """Return the pre-v2 response shape byte-for-byte equivalent by value."""
    return {
        "version": VERSION,
        "template_version": NTC_VERSION,
        "data_contract": CAPABILITIES,
        "drivers": [
            {
                "id": binding.id,
                "label": binding.label,
                "available": True,
                "validation_level": level,
                "tested_versions": tested,
                "capabilities": SUPPORTED[binding.id],
                "commands": [asdict(command) for command in plan],
            }
            for binding in REGISTRY.legacy_bindings
            if binding.available
            for _, plan, tested, level in (DRIVERS[binding.id],)
        ] + [
            {
                "id": binding.id,
                "label": binding.label,
                "available": False,
                "validation_level": "experimental",
                "tested_versions": [],
                "capabilities": {},
                "commands": [],
                "reason": "driver_not_implemented",
            }
            for binding in REGISTRY.legacy_bindings
            if not binding.available
        ],
    }


def catalog_v2_enabled(value: str | None = None) -> bool:
    configured = os.getenv("NETSTUDIO_DRIVER_CATALOG_V2", "1") if value is None else value
    return configured.strip().lower() not in {"0", "false", "no", "off"}


def _legacy_v2_metadata(identifier: str) -> dict:
    adapter = REGISTRY.adapter(identifier)
    if adapter:
        entry = adapter_catalog_entry(adapter)
        return {
            "profile_kind": "infrastructure_adapter",
            "profile_schema_version": entry["schema_version"],
            "canonical_profile_id": None,
            "profile_revision": entry["revision"],
            "implementation_status": entry["implementation_status"],
            "verification_status": entry["verification_status"],
            "release_status": entry["release_status"],
            "selectable": entry["selectable"],
            "runtime_selection_id": entry["runtime_selection_id"],
            "identity": None,
            "transports": entry["transports"],
            "acceptance": entry["acceptance"],
            "aliases": [],
            "alias_policies": [],
        }

    profile = REGISTRY.runtime_profile(identifier)
    resolution = REGISTRY.resolve(identifier)
    if profile is None and resolution.canonical_profile_id:
        profile = REGISTRY.profile(resolution.canonical_profile_id)
    if profile:
        entry = profile_catalog_entry(profile)
        return {
            "profile_kind": "driver_profile",
            "profile_schema_version": entry["schema_version"],
            "canonical_profile_id": profile.id,
            "profile_revision": entry["profile_revision"],
            "implementation_status": entry["implementation_status"],
            "verification_status": entry["verification_status"],
            "release_status": entry["release_status"],
            "selectable": identifier in DRIVERS,
            "runtime_selection_id": profile.runtime_driver_id,
            "identity": entry["identity"],
            "transports": entry["transports"],
            "acceptance": entry["acceptance"],
            "aliases": entry["aliases"],
            "alias_policies": entry["alias_policies"],
            "resolution_status": resolution.status,
        }

    # The legacy Fortinet value is intentionally not guessed as either
    # standalone FortiSwitchOS or FortiLink-managed FortiSwitchOS.
    resolution = REGISTRY.resolve(identifier)
    return {
        "profile_kind": "legacy_unresolved",
        "profile_schema_version": 1,
        "canonical_profile_id": None,
        "profile_revision": None,
        "implementation_status": "catalog_only",
        "verification_status": "not_tested",
        "release_status": "hidden",
        "selectable": False,
        "runtime_selection_id": None,
        "identity": None,
        "transports": {},
        "acceptance": AcceptanceSummary(highest_level="not_tested").model_dump(mode="json"),
        "aliases": [],
        "alias_policies": [],
        "resolution_status": resolution.status,
    }


def catalog(*, include_v2: bool | None = None) -> dict:
    legacy = legacy_catalog()
    enabled = catalog_v2_enabled() if include_v2 is None else include_v2
    if not enabled:
        return legacy
    return {
        **legacy,
        "schema_version": 2,
        "catalog_revision": CATALOG_REVISION,
        "drivers": [
            {**entry, **_legacy_v2_metadata(entry["id"])}
            for entry in legacy["drivers"]
        ],
        "profiles": [
            profile_catalog_entry(profile) for profile in REGISTRY.profiles
        ],
        "infrastructure_adapters": [
            adapter_catalog_entry(adapter) for adapter in REGISTRY.adapters
        ],
        "aliases": [alias.model_dump(mode="json") for alias in REGISTRY.aliases],
        "unresolved_aliases": [
            alias.model_dump(mode="json")
            for alias in REGISTRY.aliases
            if alias.target_profile_id is None
        ],
    }


__all__ = [
    "CAPABILITIES", "CATALOG_REVISION", "Command", "DRIVERS", "GROUPS",
    "AOSCX", "AOSS", "EOS", "H3C_COMWARE7", "HPE_COMWARE", "IOS", "IOSXE",
    "JUNOS", "NTC_VERSION", "NXOS", "PLANNED", "ROUTEROS", "SUPPORTED", "VERSION",
    "REFERENCES", "VRP", "catalog", "catalog_v2_enabled", "commands",
    "legacy_catalog",
]
