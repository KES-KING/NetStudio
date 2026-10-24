"""Typed registry and additive catalog-v2 contracts; no device support claims."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.driver_catalog import catalog, legacy_catalog
from app.driver_profiles import (
    REGISTRY,
    AcceptanceSummary,
    LegacyCatalogBinding,
    ProfileAlias,
    validate_registry,
)
from conftest import login


ROOT = Path(__file__).resolve().parents[2]
S00 = json.loads(
    (ROOT / "docs" / "uyumluluk-uygulama" / "S00_KAPSAM_KARARLARI.json").read_text()
)
SNAPSHOT = json.loads(
    (Path(__file__).parent / "snapshots" / "driver_catalog_v2.json").read_text()
)
LEGACY_V1_SHA256 = "50be67067d089f01025b7c96a4ac98306c61bdf21aeee9b32c949ecd3aea14a1"


def _snapshot(value: dict) -> dict:
    return {
        "schema_version": value["schema_version"],
        "catalog_revision": value["catalog_revision"],
        "legacy_driver_ids": [entry["id"] for entry in value["drivers"]],
        "profiles": [
            {
                "id": entry["id"],
                "implementation": entry["implementation_status"],
                "verification": entry["verification_status"],
                "release": entry["release_status"],
                "available": entry["available"],
                "selectable": entry["selectable"],
            }
            for entry in value["profiles"]
        ],
        "adapter_ids": [entry["id"] for entry in value["infrastructure_adapters"]],
        "aliases": value["aliases"],
    }


def test_registry_has_exact_s00_scope_and_statuses_do_not_regress():
    expected = {entry["id"]: entry for entry in S00["profiles"]}
    actual = {profile.id: profile for profile in REGISTRY.profiles}
    assert len(actual) == 38
    assert set(actual) == set(expected)
    for identifier, decision in expected.items():
        profile = actual[identifier]
        if profile.implementation_status != decision["implementation_status"]:
            assert decision["implementation_status"] == "catalog_only"
            assert profile.implementation_status in {"implemented", "blocked"}
        levels = [
            "not_tested", "unit_verified", "fixture_verified",
            "transport_lab_validated", "physical_validated",
        ]
        assert levels.index(profile.verification_status) >= levels.index(
            decision["verification_status"]
        )
        if profile.release_status != decision["release_status"]:
            assert decision["release_status"] == "hidden"
            assert profile.release_status == "experimental"
    bindings = REGISTRY.legacy_bindings
    assert len(bindings) == 16
    assert sum(binding.available for binding in bindings) == 15
    assert sum(not binding.available for binding in bindings) == 1
    expected_aliases = {
        entry["legacy_id"]: (
            entry["target_profile_id"], entry["resolution"], entry["automatic"]
        )
        for entry in S00["legacy_id_decisions"]
    }
    actual_aliases = {
        alias.id: (alias.target_profile_id, alias.policy, alias.automatic)
        for alias in REGISTRY.aliases
    }
    assert actual_aliases == expected_aliases


def test_catalog_v2_matches_reviewed_json_snapshot():
    assert _snapshot(catalog(include_v2=True)) == SNAPSHOT


def test_legacy_catalog_is_value_equivalent_and_flag_can_disable_v2(monkeypatch):
    legacy = legacy_catalog()
    digest = sha256(
        json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == LEGACY_V1_SHA256
    monkeypatch.setenv("NETSTUDIO_DRIVER_CATALOG_V2", "0")
    assert catalog() == legacy
    assert "schema_version" not in legacy


def test_aliases_are_unique_cycle_free_and_fortinet_fails_closed():
    aliases = {alias.id: alias for alias in REGISTRY.aliases}
    assert len(aliases) == len(REGISTRY.aliases)
    assert REGISTRY.resolve("huawei_vrp").canonical_profile_id == "huawei_vrp_v200"
    assert REGISTRY.resolve("fortinet").model_dump() == {
        "requested_id": "fortinet",
        "status": "manual_resolution_required",
        "canonical_profile_id": None,
        "policy": "manual_resolution_required",
    }
    cycle = (
        ProfileAlias(
            id="alias_a", target_profile_id="alias_b",
            policy="conditional_identity_match",
        ),
        ProfileAlias(
            id="alias_b", target_profile_id="alias_a",
            policy="conditional_identity_match",
        ),
    )
    with pytest.raises(ValueError, match="alias_cycle"):
        validate_registry((), cycle)
    duplicate = (
        ProfileAlias(
            id="legacy_name", target_profile_id="cisco_ios",
            policy="conditional_identity_match",
        ),
        ProfileAlias(
            id="legacy_name", target_profile_id="juniper_junos",
            policy="conditional_identity_match",
        ),
    )
    with pytest.raises(ValueError, match="duplicate_alias_id"):
        validate_registry(REGISTRY.profiles, duplicate, REGISTRY.adapters)
    with pytest.raises(ValueError, match="string_pattern_mismatch"):
        ProfileAlias(
            id="Invalid-Alias", target_profile_id="cisco_ios",
            policy="conditional_identity_match",
        )


def test_implemented_profile_requires_adapter_and_command_plan():
    invalid = REGISTRY.profile("cisco_ios").model_copy(update={"commands": ()})
    with pytest.raises(
        ValueError, match="implemented_profile_requires_adapter_and_command_plan"
    ):
        validate_registry((invalid,), ())


def test_legacy_catalog_binding_cannot_diverge_from_canonical_identity():
    mismatch = LegacyCatalogBinding(
        id="cisco_ios", label="Cisco IOS", available=True,
        profile_id="juniper_junos",
    )
    with pytest.raises(ValueError, match="legacy_catalog_profile_mismatch"):
        validate_registry(
            REGISTRY.profiles, REGISTRY.aliases, REGISTRY.adapters, (mismatch,)
        )


def test_capability_source_requires_an_implemented_transport():
    original = REGISTRY.profile("cisco_ios")
    invalid = original.model_copy(update={"transports": (original.transports[1],)})
    with pytest.raises(ValueError, match="capability_transport_not_implemented"):
        validate_registry((invalid,), ())


def test_supported_profile_requires_current_physical_acceptance():
    original = REGISTRY.profile("cisco_ios")
    invalid = original.model_copy(update={
        "verification_status": "physical_validated",
        "release_status": "supported",
        "acceptance": AcceptanceSummary(highest_level="physical_validated"),
    })
    with pytest.raises(ValueError, match="supported_profile_requires_physical_acceptance"):
        validate_registry((invalid,), ())
    valid = invalid.model_copy(update={
        "acceptance": AcceptanceSummary(
            highest_level="physical_validated", matching_unexpired_records=1
        ),
    })
    validate_registry((valid,), ())
    production_without_supported = original.model_copy(update={
        "acceptance": AcceptanceSummary(
            highest_level="fixture_verified", production_accepted=True
        ),
    })
    with pytest.raises(
        ValueError, match="production_acceptance_requires_supported_release"
    ):
        validate_registry((production_without_supported,), ())


def test_catalog_only_profiles_are_never_available_or_selectable():
    value = catalog(include_v2=True)
    for profile in value["profiles"]:
        if profile["implementation_status"] == "catalog_only":
            assert profile["available"] is False
            assert profile["selectable"] is False


def test_authenticated_catalog_endpoint_returns_additive_v2(system):
    client, *_ = system
    login(client)
    response = client.get("/api/v1/driver-catalog")
    assert response.status_code == 200
    value = response.json()
    assert value["schema_version"] == 2
    assert len(value["profiles"]) == 38
    assert len(value["drivers"]) == 16
    fortinet = next(entry for entry in value["drivers"] if entry["id"] == "fortinet")
    assert fortinet["canonical_profile_id"] is None
    assert fortinet["resolution_status"] == "manual_resolution_required"
