"""S11 signed physical-acceptance, release-review and rollout gates.

Only redacted metadata and hashes are persisted. Raw lab output stays in the
controlled evidence store. A row affects the catalog only while its detached
Ed25519 signature, source revision, profile revision, parser version and expiry
all remain valid.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import re
from typing import Annotated, Literal, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, TypeAdapter, field_validator, model_validator
import sqlalchemy as sa

from .contracts import ManagementMode, StrictModel
from .database import now
from .driver_profiles import CATALOG_REVISION, DRIVER_VERSION, REGISTRY


SHA256_PATTERN = r"^[0-9a-f]{64}$"
REVISION_PATTERN = r"^[0-9a-f]{40}$"
IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_.:-]{1,119}$"
MAX_PHYSICAL_EVIDENCE_AGE = timedelta(days=180)
MAX_BENCHMARK_AGE = timedelta(days=90)
MAX_CLOCK_SKEW = timedelta(minutes=5)
REQUIRED_OPERATIONAL_GATES = frozenset({
    "migration_upgrade", "e2e", "worker_restart", "lease_recovery",
    "last_good_preserved", "rollback_without_data_loss",
})
BASE_NEGATIVE_GATES = frozenset({
    "credential_failure", "timeout", "malformed_output",
    "identity_mismatch",
})


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class EvidenceReference(StrictModel):
    reference: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=SHA256_PATTERN)
    sanitized: Literal[True]
    redaction_reviewers: tuple[str, str] = Field(min_length=2, max_length=2)

    @field_validator("redaction_reviewers")
    @classmethod
    def distinct_reviewers(cls, value):
        if len(set(value)) != 2:
            raise ValueError("two_distinct_redaction_reviewers_required")
        return value


class LabAuthorization(StrictModel):
    reference: str = Field(min_length=1, max_length=240)
    scope_sha256: str = Field(pattern=SHA256_PATTERN)
    valid_until: datetime
    isolated_lab: Literal[True]
    read_only: Literal[True]


class AcceptedTarget(StrictModel):
    vendor: str = Field(min_length=1, max_length=120)
    model_family: str = Field(min_length=1, max_length=160)
    exact_model: str = Field(min_length=1, max_length=160)
    hardware_revision: str = Field(min_length=1, max_length=120)
    os_family: str = Field(min_length=1, max_length=120)
    os_version: str = Field(min_length=1, max_length=160)
    management_mode: ManagementMode
    transport: Literal["ssh", "snmp", "api"]
    security_profile: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def exact_scope(self):
        exact = (
            self.vendor, self.exact_model, self.hardware_revision,
            self.os_family, self.os_version,
        )
        if any(value.strip() in {"*", "unknown", "redacted", "n/a"} for value in exact):
            raise ValueError("physical_acceptance_requires_exact_tuple")
        if self.management_mode == "unknown":
            raise ValueError("physical_acceptance_requires_management_mode")
        if not fnmatchcase(self.exact_model.casefold(), self.model_family.casefold()):
            raise ValueError("exact_model_outside_model_family")
        return self


class CapabilityAcceptance(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    result: Literal["pass", "partial", "fail", "not_supported", "not_run"]
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class GateResult(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    result: Literal["pass", "fail", "blocked", "not_run"]
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class BenchmarkEvidence(StrictModel):
    result: Literal["pass", "fail", "not_run"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    duration_hours: float = Field(default=0, ge=0, le=24 * 31)
    device_count: int = Field(default=0, ge=0, le=100_000)
    evidence_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    metrics_complete: bool = False

    @model_validator(mode="after")
    def valid_window(self):
        if self.result == "pass":
            if not all((self.started_at, self.completed_at, self.expires_at, self.evidence_sha256)):
                raise ValueError("benchmark_pass_requires_complete_evidence")
            start, completed, expiry = map(
                _aware, (self.started_at, self.completed_at, self.expires_at)
            )
            if completed <= start or expiry <= completed:
                raise ValueError("benchmark_window_invalid")
            measured = (completed - start).total_seconds() / 3600
            if abs(measured - self.duration_hours) > 0.05:
                raise ValueError("benchmark_duration_mismatch")
            if expiry - completed > MAX_BENCHMARK_AGE:
                raise ValueError("benchmark_expiry_exceeds_policy")
        return self


class ErrorBudget(StrictModel):
    max_error_rate_percent: float = Field(gt=0, le=100)
    max_partial_rate_percent: float = Field(ge=0, le=100)
    max_queue_lateness_p95_seconds: float = Field(gt=0, le=86_400)
    breach_action: Literal["hold", "rollback"] = "rollback"


class RolloutPolicy(StrictModel):
    stages: tuple[Literal["canary", "pilot", "general"], ...]
    minimum_observation_hours: int = Field(ge=1, le=720)
    error_budget: ErrorBudget

    @field_validator("stages")
    @classmethod
    def ordered_stages(cls, value):
        if value != ("canary", "pilot", "general"):
            raise ValueError("rollout_stages_must_be_canary_pilot_general")
        return value


class Review(StrictModel):
    role: Literal["driver_developer", "lab_owner", "security_reviewer", "release_owner"]
    reviewer_ref: str = Field(min_length=1, max_length=160)
    decision: Literal["approve"]


class PublishDecision(StrictModel):
    schema_version: Literal[1] = 1
    action: Literal["publish"]
    decision_id: str = Field(min_length=8, max_length=64)
    source_revision: str = Field(pattern=REVISION_PATTERN)
    catalog_revision: str = Field(min_length=1, max_length=80)
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    profile_revision: int = Field(ge=1)
    parser_version: str = Field(min_length=1, max_length=80)
    target: AcceptedTarget
    authorization: LabAuthorization
    physical_evidence: EvidenceReference
    observed_at: datetime
    capabilities: tuple[CapabilityAcceptance, ...] = Field(min_length=1, max_length=32)
    negative_tests: tuple[GateResult, ...] = Field(min_length=1, max_length=32)
    operational_tests: tuple[GateResult, ...] = Field(min_length=1, max_length=32)
    benchmark: BenchmarkEvidence
    release_status: Literal["candidate", "supported"]
    rollout_policy: RolloutPolicy
    reviewers: tuple[Review, ...] = Field(min_length=2, max_length=8)
    signed_at: datetime
    expires_at: datetime
    production_accepted: Literal[False] = False

    @model_validator(mode="after")
    def unique_rows(self):
        for name, rows in (
            ("capability", self.capabilities),
            ("negative", self.negative_tests),
            ("operational", self.operational_tests),
        ):
            ids = [row.id for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate_{name}_result")
        roles = [review.role for review in self.reviewers]
        if len(roles) != len(set(roles)):
            raise ValueError("duplicate_release_review_role")
        observed, signed, expiry = map(
            _aware, (self.observed_at, self.signed_at, self.expires_at)
        )
        if signed < observed or expiry <= signed:
            raise ValueError("release_decision_window_invalid")
        if expiry - observed > MAX_PHYSICAL_EVIDENCE_AGE:
            raise ValueError("physical_evidence_expiry_exceeds_policy")
        if _aware(self.authorization.valid_until) < signed:
            raise ValueError("lab_authorization_expired_before_review")
        return self


class WithdrawDecision(StrictModel):
    schema_version: Literal[1] = 1
    action: Literal["withdraw"]
    decision_id: str = Field(min_length=8, max_length=64)
    supersedes_decision_id: str = Field(min_length=8, max_length=64)
    source_revision: str = Field(pattern=REVISION_PATTERN)
    catalog_revision: str = Field(min_length=1, max_length=80)
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    profile_revision: int = Field(ge=1)
    reason_code: Literal[
        "evidence_withdrawn", "scope_changed", "parser_changed",
        "security_policy_changed", "rollout_error_budget_exceeded",
    ]
    reviewers: tuple[Review, ...] = Field(min_length=2, max_length=4)
    signed_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def valid_withdrawal(self):
        roles = {review.role for review in self.reviewers}
        if not {"security_reviewer", "release_owner"} <= roles:
            raise ValueError("withdrawal_requires_security_and_release_review")
        if _aware(self.expires_at) <= _aware(self.signed_at):
            raise ValueError("release_decision_window_invalid")
        return self


ReleasePayload = Annotated[
    Union[PublishDecision, WithdrawDecision], Field(discriminator="action")
]
RELEASE_PAYLOAD = TypeAdapter(ReleasePayload)


class Signature(StrictModel):
    algorithm: Literal["ed25519"]
    key_id: str = Field(pattern=IDENTIFIER_PATTERN)
    value: str = Field(min_length=80, max_length=128)


class SignedEnvelope(StrictModel):
    payload: dict
    signature: Signature


class TrustKey(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    algorithm: Literal["ed25519"]
    public_key_base64: str = Field(min_length=40, max_length=64)


class TrustRoots(StrictModel):
    schema_version: Literal[1] = 1
    keys: tuple[TrustKey, ...]

    @field_validator("keys")
    @classmethod
    def unique_keys(cls, value):
        if len({key.id for key in value}) != len(value):
            raise ValueError("duplicate_release_trust_key")
        return value


class RolloutObservation(StrictModel):
    schema_version: Literal[1] = 1
    observation_id: str = Field(min_length=8, max_length=64)
    decision_id: str = Field(min_length=8, max_length=64)
    source_revision: str = Field(pattern=REVISION_PATTERN)
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    profile_revision: int = Field(ge=1)
    stage: Literal["canary", "pilot", "general"]
    window_started_at: datetime
    observed_at: datetime
    recorded_at: datetime
    device_count: int = Field(ge=1, le=100_000)
    job_count: int = Field(ge=1)
    error_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    queue_lateness_p95_seconds: float = Field(ge=0, le=86_400)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def valid_observation(self):
        if self.error_count + self.partial_count > self.job_count:
            raise ValueError("rollout_counts_exceed_jobs")
        start, observed, recorded = map(
            _aware, (self.window_started_at, self.observed_at, self.recorded_at)
        )
        if not start < observed <= recorded:
            raise ValueError("rollout_observation_window_invalid")
        return self


def canonical_bytes(payload: StrictModel | dict) -> bytes:
    value = payload.model_dump(mode="json") if isinstance(payload, StrictModel) else payload
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def payload_digest(payload: StrictModel | dict) -> str:
    return sha256(canonical_bytes(payload)).hexdigest()


def load_trust_roots(path: str | Path | None = None) -> dict[str, Ed25519PublicKey]:
    selected = Path(path or os.getenv(
        "NETSTUDIO_RELEASE_TRUST_ROOTS_FILE",
        str(Path(__file__).with_name("release_trust_roots.json")),
    ))
    if not selected.is_file():
        return {}
    roots = TrustRoots.model_validate_json(selected.read_text())
    result = {}
    for key in roots.keys:
        try:
            raw = base64.b64decode(key.public_key_base64, validate=True)
            result[key.id] = Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, TypeError) as error:
            raise ValueError(f"invalid_release_trust_key:{key.id}") from error
    return result


def validate_trust_roots_file(path: str | Path) -> TrustRoots:
    roots = TrustRoots.model_validate_json(Path(path).read_text())
    if not roots.keys:
        raise ValueError("release_trust_roots_empty")
    # Decode every key now; malformed material must not replace a working file.
    load_trust_roots(path)
    return roots


def verify_envelope(
    envelope: SignedEnvelope,
    trusted_keys: dict[str, Ed25519PublicKey],
) -> ReleasePayload:
    key = trusted_keys.get(envelope.signature.key_id)
    if key is None:
        raise ValueError("release_signer_not_trusted")
    payload = RELEASE_PAYLOAD.validate_python(envelope.payload)
    try:
        signature = base64.b64decode(envelope.signature.value, validate=True)
        key.verify(signature, canonical_bytes(payload))
    except (InvalidSignature, ValueError, TypeError) as error:
        raise ValueError("release_signature_invalid") from error
    return payload


def verify_rollout_envelope(
    envelope: SignedEnvelope,
    trusted_keys: dict[str, Ed25519PublicKey],
) -> RolloutObservation:
    key = trusted_keys.get(envelope.signature.key_id)
    if key is None:
        raise ValueError("release_signer_not_trusted")
    payload = RolloutObservation.model_validate(envelope.payload)
    try:
        signature = base64.b64decode(envelope.signature.value, validate=True)
        key.verify(signature, canonical_bytes(payload))
    except (InvalidSignature, ValueError, TypeError) as error:
        raise ValueError("release_signature_invalid") from error
    return payload


def _required_negative_gates(profile) -> set[str]:
    gates = set(BASE_NEGATIVE_GATES)
    kinds = {transport.kind for transport in profile.transports if transport.state == "implemented"}
    if "ssh" in kinds:
        gates.add("host_key_change")
    if "snmp" in kinds:
        gates.add("snmp_authentication_failure")
    if "api" in kinds:
        gates.add("tls_failure")
    return gates


def validate_publish_decision(value: PublishDecision, *, at: datetime | None = None) -> None:
    at = _aware(at or now())
    profile = REGISTRY.profile(value.profile_id)
    if not profile or profile.profile_revision != value.profile_revision:
        raise ValueError("release_profile_revision_unknown")
    if profile.implementation_status != "implemented":
        raise ValueError("release_profile_not_implemented")
    if value.catalog_revision != CATALOG_REVISION or value.parser_version != DRIVER_VERSION:
        raise ValueError("release_code_revision_mismatch")
    if _aware(value.signed_at) > at + MAX_CLOCK_SKEW:
        raise ValueError("release_decision_signed_in_future")
    if _aware(value.expires_at) <= at:
        raise ValueError("release_decision_expired")
    if _aware(value.authorization.valid_until) < _aware(value.observed_at):
        raise ValueError("lab_authorization_did_not_cover_observation")
    normal = lambda item: re.sub(r"[^a-z0-9]+", "", item.casefold())
    if not any(normal(value.target.vendor) == normal(item) for item in profile.identity.vendors):
        raise ValueError("release_vendor_mismatch")
    if not any(normal(value.target.os_family) == normal(item) for item in profile.identity.os_families):
        raise ValueError("release_os_family_mismatch")
    if (
        profile.identity.model_patterns
        and not any(fnmatchcase(
            value.target.exact_model.casefold(), pattern.casefold()
        ) for pattern in profile.identity.model_patterns)
    ):
        raise ValueError("release_model_mismatch")
    if (
        profile.identity.version_constraints
        and not any(fnmatchcase(
            value.target.os_version.casefold(), pattern.casefold()
        ) for pattern in profile.identity.version_constraints)
    ):
        raise ValueError("release_os_version_mismatch")
    if value.target.management_mode not in profile.identity.management_modes:
        raise ValueError("release_management_mode_mismatch")
    implemented_transports = {
        transport.kind for transport in profile.transports
        if transport.state == "implemented"
    }
    if value.target.transport not in implemented_transports:
        raise ValueError("release_transport_not_implemented")
    physical_results = (
        *value.capabilities, *value.negative_tests, *value.operational_tests,
    )
    if any(
        result.evidence_sha256 != value.physical_evidence.sha256
        for result in physical_results
    ):
        raise ValueError("physical_evidence_not_bound_to_all_results")

    capabilities = {result.id: result.result for result in value.capabilities}
    candidate_required = {"system_identity", "inventory"}
    if not candidate_required <= {
        capability for capability, result in capabilities.items() if result == "pass"
    }:
        raise ValueError("candidate_requires_identity_and_inventory")
    operations = {result.id: result.result for result in value.operational_tests}
    if not {"migration_upgrade", "e2e"} <= {
        gate for gate, result in operations.items() if result == "pass"
    }:
        raise ValueError("candidate_requires_migration_and_e2e")
    roles = {review.role for review in value.reviewers}
    if not {"lab_owner", "release_owner"} <= roles:
        raise ValueError("candidate_requires_lab_and_release_review")

    if value.release_status != "supported":
        return
    required_capabilities = {"system_identity"} | {
        capability.group for capability in profile.capabilities
    }
    if not required_capabilities <= {
        capability for capability, result in capabilities.items() if result == "pass"
    }:
        raise ValueError("supported_requires_all_declared_capabilities")
    negatives = {result.id: result.result for result in value.negative_tests}
    if not _required_negative_gates(profile) <= {
        gate for gate, result in negatives.items() if result == "pass"
    }:
        raise ValueError("supported_requires_fail_closed_negative_tests")
    if not REQUIRED_OPERATIONAL_GATES <= {
        gate for gate, result in operations.items() if result == "pass"
    }:
        raise ValueError("supported_requires_operational_and_rollback_tests")
    if not {
        "driver_developer", "lab_owner", "security_reviewer", "release_owner"
    } <= roles:
        raise ValueError("supported_requires_four_role_review")
    benchmark = value.benchmark
    if (
        benchmark.result != "pass"
        or benchmark.duration_hours < 24
        or not benchmark.metrics_complete
        or _aware(benchmark.expires_at) <= at
    ):
        raise ValueError("supported_requires_current_24h_benchmark")
    if _aware(benchmark.completed_at) > _aware(value.signed_at):
        raise ValueError("benchmark_completed_after_release_review")


def _decision_row(payload: ReleasePayload, envelope: SignedEnvelope) -> dict:
    return {
        "id": payload.decision_id,
        "source_revision": payload.source_revision,
        "profile_id": payload.profile_id,
        "profile_revision": payload.profile_revision,
        "action": payload.action,
        "release_status": payload.release_status if payload.action == "publish" else None,
        "payload": payload.model_dump(mode="json"),
        "payload_sha256": payload_digest(payload),
        "signer_key_id": envelope.signature.key_id,
        "signature": envelope.signature.value,
        "signed_at": payload.signed_at,
        "expires_at": payload.expires_at,
    }


def save_release_decision(
    store,
    envelope: SignedEnvelope,
    *,
    trusted_keys: dict[str, Ed25519PublicKey],
    artifact_sha256: str | None,
    actor: str,
    benchmark_artifact_sha256: str | None = None,
) -> ReleasePayload:
    payload = verify_envelope(envelope, trusted_keys)
    imported_at = _aware(now())
    if _aware(payload.signed_at) > imported_at + MAX_CLOCK_SKEW:
        raise ValueError("release_decision_signed_in_future")
    if _aware(payload.expires_at) <= imported_at:
        raise ValueError("release_decision_expired")
    if payload.action == "publish":
        validate_publish_decision(payload, at=imported_at)
        if artifact_sha256 != payload.physical_evidence.sha256:
            raise ValueError("physical_evidence_hash_mismatch")
        if (
            payload.benchmark.evidence_sha256 is not None
            and benchmark_artifact_sha256 != payload.benchmark.evidence_sha256
        ):
            raise ValueError("benchmark_evidence_hash_mismatch")
    with store.engine.begin() as conn:
        if conn.execute(sa.select(store.driver_release_decisions.c.id).where(
            store.driver_release_decisions.c.id == payload.decision_id
        )).first():
            raise ValueError("release_decision_already_exists")
        if payload.action == "withdraw":
            profile = REGISTRY.profile(payload.profile_id)
            if (
                not profile
                or profile.profile_revision != payload.profile_revision
                or payload.catalog_revision != CATALOG_REVISION
            ):
                raise ValueError("release_profile_revision_unknown")
            prior = conn.execute(sa.select(store.driver_release_decisions).where(
                store.driver_release_decisions.c.id == payload.supersedes_decision_id
            )).mappings().first()
            if not prior or prior["action"] != "publish" or any((
                prior["profile_id"] != payload.profile_id,
                prior["profile_revision"] != payload.profile_revision,
                prior["source_revision"] != payload.source_revision,
            )):
                raise ValueError("withdrawal_target_mismatch")
            if prior["payload_sha256"] != payload_digest(prior["payload"]):
                raise ValueError("withdrawal_target_invalid")
            try:
                prior_payload = verify_envelope(_stored_envelope(prior), trusted_keys)
            except (ValueError, TypeError) as error:
                raise ValueError("withdrawal_target_invalid") from error
            if not isinstance(prior_payload, PublishDecision):
                raise ValueError("withdrawal_target_invalid")
            if _aware(payload.signed_at) <= _aware(prior["signed_at"]):
                raise ValueError("withdrawal_must_follow_original_decision")
            if _aware(payload.expires_at) < _aware(prior["expires_at"]):
                raise ValueError("withdrawal_must_cover_original_expiry")
        conn.execute(store.driver_release_decisions.insert().values(
            **_decision_row(payload, envelope)
        ))
        if payload.action == "publish":
            for capability in payload.capabilities:
                record_id = sha256(
                    f"{payload.decision_id}:{capability.id}".encode()
                ).hexdigest()
                result = {
                    "pass": "pass", "partial": "fail", "fail": "fail",
                    "not_supported": "blocked", "not_run": "blocked",
                }[capability.result]
                conn.execute(store.driver_acceptance.insert().values(
                    id=record_id,
                    source_revision=payload.source_revision,
                    profile_id=payload.profile_id,
                    profile_revision=payload.profile_revision,
                    vendor=payload.target.vendor,
                    model_family=payload.target.model_family,
                    exact_model=payload.target.exact_model,
                    hardware_revision=payload.target.hardware_revision,
                    os_family=payload.target.os_family,
                    os_version=payload.target.os_version,
                    management_mode=payload.target.management_mode,
                    transport=payload.target.transport,
                    security_profile=payload.target.security_profile,
                    capability_id=capability.id,
                    parser_version=payload.parser_version,
                    test_suite_revision=f"s11:{payload.decision_id}",
                    validation_level="physical_validated",
                    result=result,
                    evidence_ref=payload.physical_evidence.reference,
                    evidence_sha256=capability.evidence_sha256,
                    evidence_sanitized=True,
                    observed_at=payload.observed_at,
                    recorded_at=payload.signed_at,
                    expires_at=payload.expires_at,
                    reviewed_by=",".join(sorted(review.role for review in payload.reviewers)),
                ))
        else:
            withdrawal_sha256 = payload_digest(payload)
            for capability in prior_payload.capabilities:
                record_id = sha256(
                    f"{payload.decision_id}:{capability.id}".encode()
                ).hexdigest()
                conn.execute(store.driver_acceptance.insert().values(
                    id=record_id,
                    source_revision=prior_payload.source_revision,
                    profile_id=prior_payload.profile_id,
                    profile_revision=prior_payload.profile_revision,
                    vendor=prior_payload.target.vendor,
                    model_family=prior_payload.target.model_family,
                    exact_model=prior_payload.target.exact_model,
                    hardware_revision=prior_payload.target.hardware_revision,
                    os_family=prior_payload.target.os_family,
                    os_version=prior_payload.target.os_version,
                    management_mode=prior_payload.target.management_mode,
                    transport=prior_payload.target.transport,
                    security_profile=prior_payload.target.security_profile,
                    capability_id=capability.id,
                    parser_version=prior_payload.parser_version,
                    test_suite_revision=f"s11:{prior_payload.decision_id}",
                    validation_level="physical_validated",
                    result="withdrawn",
                    evidence_ref=f"withdrawal:{payload.decision_id}",
                    evidence_sha256=withdrawal_sha256,
                    evidence_sanitized=True,
                    observed_at=payload.signed_at,
                    recorded_at=payload.signed_at,
                    expires_at=payload.expires_at,
                    reviewed_by=",".join(sorted(review.role for review in payload.reviewers)),
                ))
        store.record(
            actor,
            "driver.release.decision",
            payload.action,
            target_type="driver_profile",
            target_id=payload.profile_id,
            details={
                "profile_id": payload.profile_id,
                "profile_revision": payload.profile_revision,
                "result": payload.action,
                "status": getattr(payload, "release_status", None),
                "reason": getattr(payload, "reason_code", None),
            },
            conn=conn,
        )
    return payload


def save_rollout_observation(
    store,
    envelope: SignedEnvelope,
    *,
    trusted_keys: dict[str, Ed25519PublicKey],
    artifact_sha256: str | None,
    actor: str,
) -> RolloutObservation:
    payload = verify_rollout_envelope(envelope, trusted_keys)
    if artifact_sha256 != payload.evidence_sha256:
        raise ValueError("rollout_evidence_hash_mismatch")
    if _aware(payload.recorded_at) > _aware(now()) + MAX_CLOCK_SKEW:
        raise ValueError("rollout_observation_recorded_in_future")
    with store.engine.begin() as conn:
        decision = conn.execute(sa.select(store.driver_release_decisions).where(
            store.driver_release_decisions.c.id == payload.decision_id,
            store.driver_release_decisions.c.action == "publish",
        )).mappings().first()
        if not decision or decision["payload_sha256"] != payload_digest(decision["payload"]):
            raise ValueError("rollout_decision_invalid")
        try:
            decision_payload = verify_envelope(_stored_envelope(decision), trusted_keys)
        except (ValueError, TypeError) as error:
            raise ValueError("rollout_decision_invalid") from error
        if not isinstance(decision_payload, PublishDecision):
            raise ValueError("rollout_decision_mismatch")
        validate_publish_decision(decision_payload)
        if any((
            decision["source_revision"] != payload.source_revision,
            decision["profile_id"] != payload.profile_id,
            decision["profile_revision"] != payload.profile_revision,
        )):
            raise ValueError("rollout_decision_mismatch")
        if payload.stage not in decision_payload.rollout_policy.stages:
            raise ValueError("rollout_stage_not_allowed")
        if _aware(payload.window_started_at) < _aware(decision_payload.signed_at):
            raise ValueError("rollout_before_release_decision")
        if _aware(payload.recorded_at) > _aware(decision_payload.expires_at):
            raise ValueError("rollout_after_release_expiry")
        if conn.execute(sa.select(store.driver_rollout_observations.c.id).where(
            store.driver_rollout_observations.c.id == payload.observation_id
        )).first():
            raise ValueError("rollout_observation_already_exists")
        history = []
        history_rows = conn.execute(sa.select(
            store.driver_rollout_observations
        ).where(
            store.driver_rollout_observations.c.decision_id == payload.decision_id
        ).order_by(
            store.driver_rollout_observations.c.recorded_at,
            store.driver_rollout_observations.c.id,
        )).mappings()
        for row in history_rows:
            if row["payload_sha256"] != payload_digest(row["payload"]):
                raise ValueError("rollout_history_invalid")
            try:
                prior = verify_rollout_envelope(_stored_envelope(row), trusted_keys)
            except (ValueError, TypeError) as error:
                raise ValueError("rollout_history_invalid") from error
            if any((
                prior.decision_id != decision_payload.decision_id,
                prior.source_revision != decision_payload.source_revision,
                prior.profile_id != decision_payload.profile_id,
                prior.profile_revision != decision_payload.profile_revision,
            )):
                raise ValueError("rollout_history_invalid")
            history.append(prior)
        transition_error = _rollout_transition_error(
            payload, history, decision_payload
        )
        if transition_error:
            raise ValueError(transition_error)
        conn.execute(store.driver_rollout_observations.insert().values(
            id=payload.observation_id,
            decision_id=payload.decision_id,
            source_revision=payload.source_revision,
            profile_id=payload.profile_id,
            profile_revision=payload.profile_revision,
            stage=payload.stage,
            payload=payload.model_dump(mode="json"),
            payload_sha256=payload_digest(payload),
            signer_key_id=envelope.signature.key_id,
            signature=envelope.signature.value,
            observed_at=payload.observed_at,
            recorded_at=payload.recorded_at,
        ))
        store.record(
            actor,
            "driver.release.rollout_observed",
            payload.stage,
            target_type="driver_profile",
            target_id=payload.profile_id,
            details={
                "profile_id": payload.profile_id,
                "profile_revision": payload.profile_revision,
                "status": payload.stage,
            },
            conn=conn,
        )
    return payload


def _stored_envelope(row) -> SignedEnvelope:
    return SignedEnvelope(payload=row["payload"], signature={
        "algorithm": "ed25519",
        "key_id": row["signer_key_id"],
        "value": row["signature"],
    })


def _rollout_breaches(value: RolloutObservation, policy: RolloutPolicy) -> list[str]:
    budget = policy.error_budget
    errors = value.error_count / value.job_count * 100
    partial = value.partial_count / value.job_count * 100
    reasons = []
    if errors > budget.max_error_rate_percent:
        reasons.append("rollout_error_rate_exceeded")
    if partial > budget.max_partial_rate_percent:
        reasons.append("rollout_partial_rate_exceeded")
    if value.queue_lateness_p95_seconds > budget.max_queue_lateness_p95_seconds:
        reasons.append("rollout_queue_lateness_exceeded")
    window = (_aware(value.observed_at) - _aware(value.window_started_at)).total_seconds() / 3600
    if window < policy.minimum_observation_hours:
        reasons.append("rollout_observation_too_short")
    return reasons


def _rollout_transition_error(
    value: RolloutObservation,
    history: list[RolloutObservation],
    decision: PublishDecision,
) -> str | None:
    stages = decision.rollout_policy.stages
    current = stages.index(value.stage)
    if not history:
        return None if current == 0 else "rollout_previous_stage_not_accepted"
    highest = max(stages.index(item.stage) for item in history)
    if current < highest:
        return "rollout_stage_regression"
    if current > highest + 1:
        return "rollout_previous_stage_not_accepted"
    prior_breaches = {
        reason for item in history
        for reason in _rollout_breaches(item, decision.rollout_policy)
    }
    if current > highest and prior_breaches:
        return "rollout_blocked_by_prior_breach"
    if current > 0:
        predecessor = stages[current - 1]
        if not any(
            item.stage == predecessor
            and not _rollout_breaches(item, decision.rollout_policy)
            for item in history
        ):
            return "rollout_previous_stage_not_accepted"
    return None


def release_states(
    store,
    *,
    trusted_keys: dict[str, Ed25519PublicKey] | None = None,
    at: datetime | None = None,
    source_revision: str | None = None,
) -> dict[tuple[str, int], dict]:
    """Return only currently trusted decisions; invalid rows fail closed."""
    at = _aware(at or now())
    source_revision = source_revision or os.getenv("NETSTUDIO_BUILD_REVISION", "")
    if not re.fullmatch(REVISION_PATTERN, source_revision):
        return {}
    if trusted_keys is None:
        try:
            trusted_keys = load_trust_roots()
        except (OSError, ValueError):
            return {}
    if not trusted_keys:
        return {}
    table = store.driver_release_decisions
    with store.engine.connect() as conn:
        rows = list(conn.execute(sa.select(table).where(
            table.c.source_revision == source_revision,
            table.c.signed_at <= at,
            table.c.expires_at > at,
        ).order_by(table.c.signed_at, table.c.id)).mappings())
        publish_ids = [row["id"] for row in rows if row["action"] == "publish"]
        rollout_rows = [] if not publish_ids else list(conn.execute(sa.select(
            store.driver_rollout_observations
        ).where(
            store.driver_rollout_observations.c.decision_id.in_(publish_ids),
            store.driver_rollout_observations.c.recorded_at <= at,
        ).order_by(
            store.driver_rollout_observations.c.recorded_at,
            store.driver_rollout_observations.c.id,
        )).mappings())
    valid: dict[str, ReleasePayload] = {}
    active: dict[tuple[str, int], PublishDecision] = {}
    for row in rows:
        if row["payload_sha256"] != payload_digest(row["payload"]):
            continue
        try:
            payload = verify_envelope(_stored_envelope(row), trusted_keys)
            if payload.action == "publish":
                validate_publish_decision(payload, at=at)
            else:
                profile = REGISTRY.profile(payload.profile_id)
                target = valid.get(payload.supersedes_decision_id)
                if (
                    not isinstance(target, PublishDecision)
                    or not profile
                    or profile.profile_revision != payload.profile_revision
                    or payload.catalog_revision != CATALOG_REVISION
                    or _aware(payload.signed_at) <= _aware(target.signed_at)
                ):
                    continue
        except (ValueError, TypeError):
            continue
        valid[payload.decision_id] = payload
        key = (payload.profile_id, payload.profile_revision)
        if isinstance(payload, PublishDecision):
            active[key] = payload
        elif active.get(key) is target:
            del active[key]

    rollout_by_decision: dict[str, dict] = {}
    for row in rollout_rows:
        if row["payload_sha256"] != payload_digest(row["payload"]):
            continue
        try:
            value = verify_rollout_envelope(_stored_envelope(row), trusted_keys)
            decision = valid.get(value.decision_id)
            if not isinstance(decision, PublishDecision):
                continue
            if any((
                value.source_revision != decision.source_revision,
                value.profile_id != decision.profile_id,
                value.profile_revision != decision.profile_revision,
                _aware(value.window_started_at) < _aware(decision.signed_at),
                _aware(value.recorded_at) > _aware(decision.expires_at),
            )):
                continue
        except (ValueError, TypeError):
            continue
        state = rollout_by_decision.setdefault(value.decision_id, {
            "history": [], "reasons": set(), "latest": None,
        })
        transition_error = _rollout_transition_error(
            value, state["history"], decision
        )
        if transition_error:
            state["reasons"].add(transition_error)
        state["reasons"].update(_rollout_breaches(value, decision.rollout_policy))
        state["history"].append(value)
        state["latest"] = value

    result = {}
    for key, decision in active.items():
        rollout = rollout_by_decision.get(decision.decision_id)
        reasons = sorted(rollout["reasons"]) if rollout else []
        latest = rollout["latest"] if rollout else None
        status = decision.release_status
        if reasons:
            status = "experimental"
        elif decision.release_status == "supported" and (
            latest is None or latest.stage != "general"
        ):
            status = "candidate"
            reasons = [
                "rollout_not_started" if latest is None
                else "rollout_general_not_reached"
            ]
        result[key] = {
            "release_status": status,
            "release_decision": {
                "decision_id": decision.decision_id,
                "payload_sha256": payload_digest(decision),
                "signer_key_id": next(
                    row["signer_key_id"] for row in rows if row["id"] == decision.decision_id
                ),
                "signed_at": decision.signed_at,
                "expires_at": decision.expires_at,
                "accepted_vendor": decision.target.vendor,
                "accepted_model_family": decision.target.model_family,
                "accepted_exact_model": decision.target.exact_model,
                "accepted_hardware_revision": decision.target.hardware_revision,
                "accepted_os_family": decision.target.os_family,
                "accepted_os_version": decision.target.os_version,
                "accepted_management_mode": decision.target.management_mode,
                "accepted_transport": decision.target.transport,
                "accepted_security_profile": decision.target.security_profile,
                "benchmark_status": decision.benchmark.result,
                "rollout_stage": latest.stage if latest else "not_started",
                "blocked_reasons": reasons,
                "production_accepted": False,
            },
        }
    return result


def public_release_decisions(store) -> list[dict]:
    """Audit-reader projection without artifact paths, signatures or reviewer IDs."""
    table = store.driver_release_decisions
    with store.engine.connect() as conn:
        rows = conn.execute(sa.select(table).order_by(
            table.c.signed_at.desc(), table.c.id.desc()
        )).mappings()
        return [{
            "decision_id": row["id"],
            "source_revision": row["source_revision"],
            "profile_id": row["profile_id"],
            "profile_revision": row["profile_revision"],
            "action": row["action"],
            "release_status": row["release_status"],
            "payload_sha256": row["payload_sha256"],
            "signer_key_id": row["signer_key_id"],
            "signed_at": row["signed_at"],
            "expires_at": row["expires_at"],
        } for row in rows]
