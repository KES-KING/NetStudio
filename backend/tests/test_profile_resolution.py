"""Profile resolution tests are metadata-only; they make no device connection."""
import pytest

from app.profile_resolution import IdentityEvidence, resolve_profile


def test_conditional_alias_requires_identity_and_matches_only_exact_os_family():
    unresolved = resolve_profile("dell_force10")
    assert unresolved.status == "manual_resolution_required"
    assert unresolved.configured_profile_id == "dell_os9"
    assert unresolved.resolved_profile_id is None

    matched = resolve_profile("dell_force10", evidence=IdentityEvidence(
        vendor="Dell Technologies", os_family="OS9", os_version="9.14"
    ))
    assert matched.status == "matched"
    assert matched.resolved_profile_id == "dell_os9"
    assert matched.confidence >= .9

    wrong = resolve_profile("dell_force10", evidence=IdentityEvidence(
        vendor="Dell Technologies", os_family="SmartFabric OS10"
    ))
    assert wrong.status == "conflict"
    assert "os_family_mismatch" in wrong.conflicts


def test_fortinet_legacy_value_is_never_guessed_from_client_evidence():
    result = resolve_profile("fortinet", evidence=IdentityEvidence(
        vendor="Fortinet", os_family="FortiSwitchOS"
    ))
    assert result.status == "manual_resolution_required"
    assert result.configured_profile_id is None
    assert result.resolved_profile_id is None


def test_auto_requires_vendor_and_exact_os_and_fails_closed_on_conflict():
    matched = resolve_profile("auto", evidence=IdentityEvidence(
        vendor="Cisco Systems", os_family="IOS"
    ))
    assert matched.status == "matched"
    assert matched.resolved_profile_id == "cisco_ios"

    incomplete = resolve_profile("auto", evidence=IdentityEvidence(vendor="Cisco"))
    assert incomplete.status == "unresolved"
    assert incomplete.resolved_profile_id is None

    conflict = resolve_profile("cisco_ios", evidence=IdentityEvidence(
        vendor="Huawei", os_family="VRP V200"
    ))
    assert conflict.status == "conflict"
    assert set(conflict.conflicts) == {"vendor_mismatch", "os_family_mismatch"}


def test_only_known_canonical_profiles_can_be_selected():
    with pytest.raises(ValueError, match="unknown_driver_profile"):
        resolve_profile("made_up_driver")
