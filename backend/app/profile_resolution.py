"""Fail-closed profile resolution and redacted compatibility projections.

This module never connects to a device and never accepts raw command output.
Transport collectors may pass a bounded ``IdentityEvidence`` after their normal
host-key/TLS and authorization checks; browser-facing profile selection cannot.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from fnmatch import fnmatchcase
import re
from typing import Literal
from uuid import uuid4

from pydantic import Field
import sqlalchemy as sa

from .contracts import ManagementMode, StrictModel
from .database import now
from .driver_profiles import DRIVER_VERSION, REGISTRY, VerificationStatus
from .legacy_compat import getenv


ResolutionStatus = Literal[
    "unresolved", "matched", "conflict", "unsupported",
    "manual_resolution_required", "infrastructure_adapter", "external",
]
ResolutionSource = Literal[
    "canonical", "legacy_alias", "automatic", "manual",
    "infrastructure_adapter", "external",
]
ConflictCode = Literal[
    "legacy_alias_ambiguous", "identity_evidence_required",
    "vendor_mismatch", "os_family_mismatch", "model_mismatch",
    "version_mismatch", "management_mode_mismatch", "multiple_candidates",
    "configured_profile_mismatch", "transport_identity_mismatch",
]


class IdentityEvidence(StrictModel):
    vendor: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=160)
    os_family: str | None = Field(default=None, max_length=120)
    os_version: str | None = Field(default=None, max_length=160)
    hardware_revision: str | None = Field(default=None, max_length=120)
    sys_object_id: str | None = Field(
        default=None, max_length=160, pattern=r"^(?:\.?\d+)+$"
    )
    management_mode: ManagementMode = "unknown"


class ProfileResolutionResult(StrictModel):
    requested_id: str
    configured_profile_id: str | None = None
    resolved_profile_id: str | None = None
    profile_revision: int | None = Field(default=None, ge=1)
    management_mode: ManagementMode = "unknown"
    status: ResolutionStatus
    confidence: float = Field(ge=0, le=1)
    conflicts: list[ConflictCode] = Field(default_factory=list, max_length=16)
    reason_code: str | None = Field(default=None, max_length=120)
    source: ResolutionSource
    runtime_collector_id: str | None = None
    identity_evidence: IdentityEvidence = Field(default_factory=IdentityEvidence)


class DriverProfileSelection(StrictModel):
    configured_profile_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    management_mode: ManagementMode = "unknown"


class AcceptanceRecord(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()), max_length=64)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    profile_revision: int = Field(ge=1)
    vendor: str = Field(min_length=1, max_length=120)
    model_family: str = Field(min_length=1, max_length=160)
    exact_model: str = Field(min_length=1, max_length=160)
    hardware_revision: str = Field(min_length=1, max_length=120)
    os_family: str = Field(min_length=1, max_length=120)
    os_version: str = Field(min_length=1, max_length=160)
    management_mode: ManagementMode
    transport: Literal["ssh", "snmp", "api"]
    security_profile: str = Field(min_length=1, max_length=120)
    capability_id: str = Field(min_length=1, max_length=120)
    parser_version: str = Field(min_length=1, max_length=80)
    test_suite_revision: str = Field(min_length=1, max_length=80)
    validation_level: VerificationStatus
    result: Literal["pass", "fail", "blocked", "withdrawn"]
    evidence_ref: str = Field(min_length=1, max_length=500)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sanitized: Literal[True] = True
    observed_at: datetime
    recorded_at: datetime
    expires_at: datetime
    reviewed_by: str = Field(min_length=1, max_length=160)


def _normal(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def _contains_identity(actual: str | None, expected: tuple[str, ...]) -> bool:
    value = _normal(actual)
    return bool(value) and any(
        _normal(candidate) in value or value in _normal(candidate)
        for candidate in expected
    )


def _same_identity(actual: str | None, expected: tuple[str, ...]) -> bool:
    value = _normal(actual)
    return bool(value) and any(value == _normal(candidate) for candidate in expected)


def _pattern_match(actual: str | None, patterns: tuple[str, ...]) -> bool:
    if not actual or not patterns:
        return True
    value = actual.casefold()
    return any(fnmatchcase(value, pattern.casefold()) for pattern in patterns)


def _identity_result(profile, evidence: IdentityEvidence):
    conflicts: list[ConflictCode] = []
    supplied = matched = 0
    weights = {"vendor": .55, "os_family": .35, "model": .05, "os_version": .05}
    score = 0.0

    for field, expected, matcher, conflict in (
        ("vendor", profile.identity.vendors, _contains_identity, "vendor_mismatch"),
        ("os_family", profile.identity.os_families, _same_identity, "os_family_mismatch"),
        ("model", profile.identity.model_patterns, _pattern_match, "model_mismatch"),
        ("os_version", profile.identity.version_constraints, _pattern_match, "version_mismatch"),
    ):
        value = getattr(evidence, field)
        if not value or not expected:
            continue
        supplied += 1
        if matcher(value, expected):
            matched += 1
            score += weights[field]
        else:
            conflicts.append(conflict)
    if (
        evidence.management_mode != "unknown"
        and evidence.management_mode not in profile.identity.management_modes
    ):
        conflicts.append("management_mode_mismatch")
    elif evidence.management_mode != "unknown":
        score += .05
    # Vendor + OS family are the minimum evidence for automatic identity. A
    # model string alone is never allowed to promote support.
    strong = bool(evidence.vendor and evidence.os_family and matched >= 2)
    return min(score, 1.0), conflicts, strong, supplied


def resolve_profile(
    requested_id: str,
    management_mode: ManagementMode = "unknown",
    evidence: IdentityEvidence | None = None,
    *,
    source: ResolutionSource = "manual",
) -> ProfileResolutionResult:
    evidence = evidence or IdentityEvidence(management_mode=management_mode)
    if evidence.management_mode == "unknown" and management_mode != "unknown":
        evidence = evidence.model_copy(update={"management_mode": management_mode})

    if requested_id == "external":
        return ProfileResolutionResult(
            requested_id=requested_id, management_mode=management_mode,
            status="external", confidence=1, source="external",
            identity_evidence=evidence,
        )
    if requested_id == "auto":
        return _resolve_auto(management_mode, evidence)
    adapter = REGISTRY.adapter(requested_id)
    if adapter:
        return ProfileResolutionResult(
            requested_id=requested_id, management_mode=management_mode,
            status="infrastructure_adapter", confidence=1,
            source="infrastructure_adapter", runtime_collector_id=adapter.runtime_driver_id,
            identity_evidence=evidence,
        )

    registry_resolution = REGISTRY.resolve(requested_id)
    if registry_resolution.status == "unknown":
        raise ValueError("unknown_driver_profile")
    if registry_resolution.status == "manual_resolution_required":
        return ProfileResolutionResult(
            requested_id=requested_id, management_mode=management_mode,
            status="manual_resolution_required", confidence=0,
            conflicts=["legacy_alias_ambiguous"],
            reason_code="legacy_alias_ambiguous", source="legacy_alias",
            identity_evidence=evidence,
        )

    profile_id = registry_resolution.canonical_profile_id
    profile = REGISTRY.profile(profile_id)
    alias = registry_resolution.status == "alias"
    score, conflicts, strong, supplied = _identity_result(profile, evidence)
    if conflicts:
        return ProfileResolutionResult(
            requested_id=requested_id, configured_profile_id=profile.id,
            profile_revision=profile.profile_revision,
            management_mode=management_mode, status="conflict",
            confidence=score, conflicts=conflicts,
            reason_code="identity_conflict",
            source="legacy_alias" if alias else source,
            runtime_collector_id=profile.runtime_driver_id,
            identity_evidence=evidence,
        )
    if alias and registry_resolution.policy == "conditional_identity_match" and not strong:
        return ProfileResolutionResult(
            requested_id=requested_id, configured_profile_id=profile.id,
            profile_revision=profile.profile_revision,
            management_mode=management_mode,
            status="manual_resolution_required", confidence=score,
            conflicts=["identity_evidence_required"],
            reason_code="identity_evidence_required", source="legacy_alias",
            runtime_collector_id=profile.runtime_driver_id,
            identity_evidence=evidence,
        )
    if profile.implementation_status in {
        "blocked", "unsupported_by_protocol", "unsupported_by_policy", "retired"
    }:
        status, reason = "unsupported", profile.implementation_status
    elif strong:
        status, reason = "matched", None
    else:
        status, reason = "unresolved", "identity_evidence_required" if supplied else None
    return ProfileResolutionResult(
        requested_id=requested_id, configured_profile_id=profile.id,
        resolved_profile_id=profile.id if status == "matched" else None,
        profile_revision=profile.profile_revision,
        management_mode=management_mode, status=status,
        confidence=score, reason_code=reason,
        source="legacy_alias" if alias else source,
        runtime_collector_id=profile.runtime_driver_id,
        identity_evidence=evidence,
    )


def _resolve_auto(
    management_mode: ManagementMode, evidence: IdentityEvidence
) -> ProfileResolutionResult:
    candidates = []
    for profile in REGISTRY.profiles:
        score, conflicts, strong, _ = _identity_result(profile, evidence)
        if strong and not conflicts:
            candidates.append((score, profile))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        return ProfileResolutionResult(
            requested_id="auto", management_mode=management_mode,
            status="unresolved", confidence=0,
            reason_code="identity_evidence_required", source="automatic",
            identity_evidence=evidence,
        )
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return ProfileResolutionResult(
            requested_id="auto", management_mode=management_mode,
            status="conflict", confidence=candidates[0][0],
            conflicts=["multiple_candidates"], reason_code="multiple_candidates",
            source="automatic", identity_evidence=evidence,
        )
    score, profile = candidates[0]
    return ProfileResolutionResult(
        requested_id="auto", resolved_profile_id=profile.id,
        profile_revision=profile.profile_revision,
        management_mode=management_mode, status="matched", confidence=score,
        source="automatic", runtime_collector_id=profile.runtime_driver_id,
        identity_evidence=evidence,
    )


def canonical_profile_for_collector(collector: str) -> str | None:
    profile = REGISTRY.runtime_profile(collector) or REGISTRY.profile(collector)
    if profile:
        return profile.id
    resolution = REGISTRY.resolve(collector)
    return resolution.canonical_profile_id


def runtime_collector_for_profile(profile_id: str) -> str:
    profile = REGISTRY.profile(profile_id)
    if profile is None:
        raise ValueError("unknown_driver_profile")
    return profile.runtime_driver_id or "external"


def collector_matches_profile(collector: str, profile_id: str) -> bool:
    # A canonical selection is operational only when its actual runtime
    # collector is selected. Catalog-only profiles intentionally resolve to
    # ``external``; implemented profiles must never remain there silently.
    return collector == runtime_collector_for_profile(profile_id)


def binding_values(
    result: ProfileResolutionResult,
    *,
    device_id: str,
    legacy_collector_id: str,
    actor: str,
    binding_revision: int = 1,
) -> dict:
    at = now()
    return {
        "device_id": device_id,
        "configured_profile_id": result.configured_profile_id,
        "legacy_collector_id": legacy_collector_id,
        "resolved_profile_id": result.resolved_profile_id,
        "profile_revision": result.profile_revision,
        "management_mode": result.management_mode,
        "resolution_status": result.status,
        "resolution_confidence": result.confidence,
        "resolution_conflicts": result.conflicts,
        "identity_evidence": result.identity_evidence.model_dump(
            mode="json", exclude_none=True
        ),
        "resolved_at": at if result.status == "matched" else None,
        "updated_at": at,
        "updated_by": actor,
        "binding_revision": binding_revision,
    }


def _identity_changed(prior: dict | None, evidence: IdentityEvidence) -> bool:
    if not prior:
        return False
    old = IdentityEvidence.model_validate(prior.get("identity_evidence") or {})
    return any(getattr(old, key) != getattr(evidence, key) for key in (
        "vendor", "model", "os_family", "os_version", "hardware_revision",
        "sys_object_id",
    ))


def _invalidate_profile_caches(store, device_id: str, conn) -> None:
    """Discard only derived capability caches; retain secrets and last-good data."""
    conn.execute(store.capabilities.delete().where(
        store.capabilities.c.device_id == device_id
    ))
    conn.execute(store.capability_observations_v2.delete().where(
        store.capability_observations_v2.c.device_id == device_id
    ))


def record_collected_resolution(
    store, device, conn, *, observed_profile_id: str | None = None,
    identity_evidence: dict | IdentityEvidence | None = None,
    identity_conflicts: list[str] | None = None,
    force_revalidation: bool = False,
) -> dict | None:
    """Persist a parser-validated runtime identity without storing raw output."""
    runtime_id = device.resolved_collector
    prior = store.get_driver_binding(device.id, conn)
    configured = prior["configured_profile_id"] if prior else None
    mode = prior["management_mode"] if prior else device.management_mode
    cache_invalidated = False
    profile = (
        REGISTRY.profile(observed_profile_id)
        if observed_profile_id else REGISTRY.runtime_profile(runtime_id)
    )
    if identity_evidence is None and force_revalidation and prior:
        evidence = IdentityEvidence.model_validate(prior["identity_evidence"] or {})
        result = ProfileResolutionResult(
            requested_id=prior["configured_profile_id"] or "auto",
            configured_profile_id=prior["configured_profile_id"],
            profile_revision=prior["profile_revision"],
            management_mode=prior["management_mode"], status="unresolved",
            confidence=0, conflicts=["identity_evidence_required"],
            reason_code="device_reboot_detected", source="automatic",
            runtime_collector_id=runtime_id, identity_evidence=evidence,
        )
        _invalidate_profile_caches(store, device.id, conn)
        cache_invalidated = True
    elif profile is None:
        return prior
    else:
        evidence = IdentityEvidence.model_validate(identity_evidence or {
            "vendor": device.vendor or None,
            "model": device.model or None,
            "os_family": profile.identity.os_families[0],
            "os_version": device.os_version or None,
            "management_mode": mode,
        })
        if evidence.management_mode == "unknown" and mode != "unknown":
            evidence = evidence.model_copy(update={"management_mode": mode})
        if identity_conflicts:
            configured_profile = REGISTRY.profile(configured) if configured else None
            result = ProfileResolutionResult(
                requested_id=configured or "auto",
                configured_profile_id=configured,
                profile_revision=(
                    configured_profile.profile_revision if configured_profile
                    else profile.profile_revision
                ),
                management_mode=mode, status="conflict", confidence=0,
                conflicts=["transport_identity_mismatch"],
                reason_code="transport_identity_mismatch", source="automatic",
                runtime_collector_id=runtime_id, identity_evidence=evidence,
            )
        elif configured and configured != profile.id:
            configured_profile = REGISTRY.profile(configured)
            result = ProfileResolutionResult(
                requested_id=configured, configured_profile_id=configured,
                profile_revision=(
                    configured_profile.profile_revision if configured_profile
                    else profile.profile_revision
                ),
                management_mode=mode, status="conflict", confidence=1,
                conflicts=["configured_profile_mismatch"],
                reason_code="configured_profile_mismatch", source="automatic",
                runtime_collector_id=runtime_id, identity_evidence=evidence,
            )
        elif profile.implementation_status != "implemented":
            result = ProfileResolutionResult(
                requested_id=configured or "auto",
                configured_profile_id=configured,
                profile_revision=profile.profile_revision,
                management_mode=mode, status="unsupported", confidence=1,
                reason_code="driver_profile_not_implemented", source="automatic",
                runtime_collector_id=None, identity_evidence=evidence,
            )
        else:
            resolved = resolve_profile(
                profile.id, management_mode=mode, evidence=evidence,
                source="automatic",
            )
            result = resolved.model_copy(update={
                "requested_id": configured or "auto",
                "configured_profile_id": configured,
                "runtime_collector_id": runtime_id or profile.runtime_driver_id,
            })
        identity_changed = bool(
            prior and prior["resolution_status"] == "matched"
            and _identity_changed(prior, evidence)
        )
        cache_invalidated = bool(identity_conflicts or force_revalidation or identity_changed or (
            prior and prior["resolved_profile_id"] not in {None, profile.id}
        ) or (
            prior and prior["profile_revision"] != profile.profile_revision
        ))
        if cache_invalidated:
            _invalidate_profile_caches(store, device.id, conn)
    values = binding_values(
        result, device_id=device.id,
        legacy_collector_id=prior["legacy_collector_id"] if prior else device.collector,
        actor="system:collector",
        binding_revision=(prior["binding_revision"] + 1) if prior else 1,
    )
    changed = not prior or any(prior[key] != values[key] for key in (
        "configured_profile_id", "resolved_profile_id", "profile_revision",
        "management_mode", "resolution_status", "resolution_confidence",
        "resolution_conflicts", "identity_evidence",
    ))
    if changed:
        store.save_driver_binding(values, conn)
        store.record(
            "system:collector", "driver.profile.resolved", result.status,
            device.id, details={
                "configured_profile_id": configured,
                "resolved_profile_id": result.resolved_profile_id,
                "profile_revision": result.profile_revision,
                "management_mode": mode,
                "resolution_status": result.status,
                "source": "collector",
                "cache_invalidated": cache_invalidated,
            }, conn=conn,
        )
        return values
    return prior


def save_capability_observation(store, binding, capability_id, metadata, conn):
    if binding and binding["resolution_status"] != "matched":
        return
    profile_id = binding and (
        binding["resolved_profile_id"] or binding["configured_profile_id"]
    )
    revision = binding and binding["profile_revision"]
    if not profile_id or not revision or metadata.source not in {"ssh", "snmp", "api"}:
        return
    import hashlib
    import json

    checked_at = metadata.attempted_at
    digest = hashlib.sha256(json.dumps({
        "profile_id": profile_id,
        "profile_revision": revision,
        "transport": metadata.source,
        "capability_id": capability_id,
        "status": metadata.quality,
        "reason_code": metadata.reason,
        "complete": metadata.complete,
        "checked_at": checked_at.isoformat(),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    values = {
        "device_id": binding["device_id"], "profile_id": profile_id,
        "profile_revision": revision, "transport": metadata.source,
        "capability_id": capability_id, "status": metadata.quality,
        "reason_code": metadata.reason[:120] if metadata.reason else None,
        "checked_at": checked_at,
        "expires_at": checked_at + timedelta(seconds=metadata.stale_after_seconds),
        "evidence_digest": digest,
    }
    table = store.capability_observations_v2
    condition = sa.and_(
        table.c.device_id == values["device_id"],
        table.c.profile_id == profile_id,
        table.c.profile_revision == revision,
        table.c.transport == metadata.source,
        table.c.capability_id == capability_id,
    )
    if not conn.execute(table.update().where(condition).values(**values)).rowcount:
        conn.execute(table.insert().values(**values))


def _redacted_acceptance(row) -> dict:
    return {key: row[key] for key in (
        "source_revision", "profile_id", "profile_revision", "vendor",
        "model_family", "exact_model", "hardware_revision", "os_family",
        "os_version", "management_mode", "transport", "security_profile",
        "capability_id", "parser_version", "test_suite_revision",
        "validation_level", "result", "evidence_sha256",
        "evidence_sanitized", "observed_at", "recorded_at", "expires_at",
    )}


def acceptance_records(store, *, profile_id: str | None = None) -> list[dict]:
    table = store.driver_acceptance
    query = sa.select(table)
    if profile_id:
        query = query.where(table.c.profile_id == profile_id)
    with store.engine.connect() as conn:
        rows = conn.execute(query.order_by(table.c.recorded_at.desc())).mappings()
        return [_redacted_acceptance(row) for row in rows]


def _tuple_match(value: str, pattern: str) -> bool:
    return pattern == "*" or fnmatchcase(value.casefold(), pattern.casefold())


def acceptance_summary(
    store, profile_id: str, profile_revision: int, *, device=None,
    identity_evidence: dict | None = None,
):
    table = store.driver_acceptance
    with store.engine.connect() as conn:
        rows = list(conn.execute(sa.select(table).where(
            table.c.profile_id == profile_id,
            table.c.profile_revision == profile_revision,
            table.c.result == "pass",
            table.c.expires_at > now(),
        )).mappings())
    if device is not None:
        evidence = identity_evidence or {}
        build_revision = getenv("NETSTUDIO_BUILD_REVISION", "")
        rows = [row for row in rows if (
            row["source_revision"] == build_revision
            and _normal(evidence.get("vendor") or device.vendor) == _normal(row["vendor"])
            and _tuple_match(device.model or "", row["model_family"])
            and _normal(evidence.get("model") or device.model) == _normal(row["exact_model"])
            and bool(evidence.get("hardware_revision"))
            and _normal(evidence.get("hardware_revision")) == _normal(row["hardware_revision"])
            and _normal(evidence.get("os_family")) == _normal(row["os_family"])
            and _normal(evidence.get("os_version") or device.os_version) == _normal(row["os_version"])
            # ``unknown`` is a real fail-closed tuple value, not a wildcard.
            # A record accepted without a known management mode must never
            # broaden to standalone, controller, cloud, or local management.
            and row["management_mode"] == device.management_mode
            and device.driver_version == DRIVER_VERSION
            and device.driver_version == row["parser_version"]
        )]
    rank = {
        "not_tested": 0, "unit_verified": 1, "fixture_verified": 2,
        "transport_lab_validated": 3, "physical_validated": 4,
    }
    highest = max((row["validation_level"] for row in rows), key=rank.get, default="not_tested")
    return {
        "highest_level": highest,
        "matching_unexpired_records": len(rows),
        # Production acceptance is installation/release specific and is never
        # inferred from a physical compatibility record.
        "production_accepted": False,
    }


def catalog_acceptance_summaries(store) -> dict[tuple[str, int], dict]:
    """Build all public profile summaries with one bounded database read."""
    build_revision = getenv("NETSTUDIO_BUILD_REVISION", "")
    if not re.fullmatch(r"[0-9a-f]{40}", build_revision):
        return {}
    table = store.driver_acceptance
    with store.engine.connect() as conn:
        rows = list(conn.execute(sa.select(table).where(
            table.c.result == "pass",
            table.c.expires_at > now(),
            table.c.source_revision == build_revision,
            table.c.parser_version == DRIVER_VERSION,
        )).mappings())
    grouped: dict[tuple[str, int], list] = {}
    for row in rows:
        grouped.setdefault((row["profile_id"], row["profile_revision"]), []).append(row)
    rank = {
        "not_tested": 0, "unit_verified": 1, "fixture_verified": 2,
        "transport_lab_validated": 3, "physical_validated": 4,
    }
    result = {}
    for key, matches in grouped.items():
        highest = max((row["validation_level"] for row in matches), key=rank.get)
        result[key] = {
            "highest_level": highest,
            "matching_unexpired_records": len(matches),
            "production_accepted": False,
        }
    return result


def compatibility_view(store, device) -> dict:
    binding = store.get_driver_binding(device.id)
    if not binding:
        # This is possible only while an old database is waiting for migration.
        # Never infer support from the payload in the read path.
        binding = {
            "configured_profile_id": None, "legacy_collector_id": device.collector,
            "resolved_profile_id": None, "profile_revision": None,
            "management_mode": "unknown", "resolution_status": "unresolved",
            "resolution_confidence": 0.0, "resolution_conflicts": [],
            "identity_evidence": {}, "resolved_at": None,
        }
    profile_id = binding["resolved_profile_id"] or binding["configured_profile_id"]
    profile = REGISTRY.profile(profile_id) if profile_id else None
    capabilities = []
    with store.engine.connect() as conn:
        rows = conn.execute(sa.select(store.capability_observations_v2).where(
            store.capability_observations_v2.c.device_id == device.id
        ).order_by(
            store.capability_observations_v2.c.transport,
            store.capability_observations_v2.c.capability_id,
        )).mappings()
        for row in rows:
            expiry = row["expires_at"]
            comparison_time = now()
            if expiry.tzinfo is None:
                comparison_time = comparison_time.replace(tzinfo=None)
            capabilities.append({key: row[key] for key in (
                "profile_id", "profile_revision", "transport", "capability_id",
                "status", "reason_code", "checked_at", "expires_at",
                "evidence_digest",
            )} | {"stale": expiry <= comparison_time})
    summary = (
        acceptance_summary(
            store, profile.id, binding["profile_revision"], device=device,
            identity_evidence=binding["identity_evidence"],
        )
        if profile and binding["profile_revision"] and binding["resolution_status"] == "matched" else
        {"highest_level": "not_tested", "matching_unexpired_records": 0,
         "production_accepted": False}
    )
    return {
        "device_id": device.id,
        "configured_profile_id": binding["configured_profile_id"],
        "legacy_collector_id": binding["legacy_collector_id"],
        "resolved_profile_id": binding["resolved_profile_id"],
        "profile_revision": binding["profile_revision"],
        "management_mode": binding["management_mode"],
        "resolution_status": binding["resolution_status"],
        "resolution_confidence": binding["resolution_confidence"],
        "resolution_conflicts": binding["resolution_conflicts"],
        "identity_evidence": IdentityEvidence.model_validate(
            binding["identity_evidence"] or {}
        ).model_dump(mode="json", exclude_none=True),
        "resolved_at": binding["resolved_at"],
        "implementation_status": profile.implementation_status if profile else None,
        "verification_status": profile.verification_status if profile else "not_tested",
        "release_status": profile.release_status if profile else "hidden",
        "runtime_collection_ready": bool(
            profile and profile.implementation_status == "implemented"
            and binding["resolution_status"] == "matched"
        ),
        "capabilities": capabilities,
        "acceptance": summary,
    }


def save_acceptance_record(store, value: AcceptanceRecord, *, actor: str, conn):
    """Trusted release-process hook; intentionally not exposed as an HTTP route."""
    profile = REGISTRY.profile(value.profile_id)
    if not profile or profile.profile_revision != value.profile_revision:
        raise ValueError("acceptance_profile_revision_unknown")
    if value.expires_at <= value.recorded_at or value.recorded_at < value.observed_at:
        raise ValueError("acceptance_expiry_invalid")
    conn.execute(store.driver_acceptance.insert().values(**value.model_dump()))
    store.record(
        actor, "driver.acceptance.recorded", value.result,
        target_type="driver_profile", target_id=value.profile_id,
        details={
            "profile_id": value.profile_id,
            "profile_revision": value.profile_revision,
            "validation_level": value.validation_level,
            "result": value.result,
            "capability_id": value.capability_id,
            "management_mode": value.management_mode,
        }, conn=conn,
    )
