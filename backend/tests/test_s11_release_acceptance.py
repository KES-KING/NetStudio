"""S11 signed physical acceptance, expiry, withdrawal and rollout gates.

All evidence in this module is synthetic. Passing tests never constitutes
physical-device or production acceptance.
"""
import base64
from datetime import timedelta
from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import pytest
import sqlalchemy as sa

from app.database import now
from app.driver_profiles import CATALOG_REVISION, DRIVER_VERSION
from app.profile_resolution import (
    AcceptanceRecord,
    acceptance_summary,
    record_collected_resolution,
    save_acceptance_record,
)
from app.release_acceptance import (
    PublishDecision,
    RolloutObservation,
    SignedEnvelope,
    WithdrawDecision,
    canonical_bytes,
    release_states,
    save_release_decision,
    save_rollout_observation,
    validate_publish_decision,
)
from conftest import add_device, login


SOURCE_REVISION = "a" * 40
ARTIFACT = b"synthetic redacted physical-lab evidence placeholder"
ARTIFACT_HASH = sha256(ARTIFACT).hexdigest()


def key_pair():
    private = Ed25519PrivateKey.generate()
    return private, {"release-test": private.public_key()}


def envelope(payload, private):
    signature = private.sign(canonical_bytes(payload))
    return SignedEnvelope(payload=payload.model_dump(mode="json"), signature={
        "algorithm": "ed25519", "key_id": "release-test",
        "value": base64.b64encode(signature).decode(),
    })


def publish(*, status="supported", decision_id="decision-s11-supported"):
    signed = now() - timedelta(hours=5)
    observed = signed - timedelta(hours=26)
    capabilities = tuple({
        "id": capability, "result": "pass", "evidence_sha256": ARTIFACT_HASH,
    } for capability in (
        "system_identity", "fast", "health", "network", "inventory",
    ))
    negative = tuple({
        "id": gate, "result": "pass", "evidence_sha256": ARTIFACT_HASH,
    } for gate in (
        "credential_failure", "timeout", "malformed_output", "identity_mismatch",
        "host_key_change", "snmp_authentication_failure",
    ))
    operational = tuple({
        "id": gate, "result": "pass", "evidence_sha256": ARTIFACT_HASH,
    } for gate in (
        "migration_upgrade", "e2e", "worker_restart", "lease_recovery",
        "last_good_preserved", "rollback_without_data_loss",
    ))
    benchmark = {
        "result": "pass", "started_at": observed,
        "completed_at": signed - timedelta(hours=1),
        "expires_at": signed + timedelta(days=30), "duration_hours": 25,
        "device_count": 1, "evidence_sha256": ARTIFACT_HASH,
        "metrics_complete": True,
    } if status == "supported" else {"result": "not_run"}
    reviewers = tuple({
        "role": role, "reviewer_ref": f"test:{role}", "decision": "approve",
    } for role in (
        "driver_developer", "lab_owner", "security_reviewer", "release_owner",
    ))
    return PublishDecision(
        action="publish", decision_id=decision_id,
        source_revision=SOURCE_REVISION, catalog_revision=CATALOG_REVISION,
        profile_id="cisco_ios", profile_revision=2,
        parser_version=DRIVER_VERSION,
        target={
            "vendor": "Cisco", "model_family": "WS-C2960X-*",
            "exact_model": "WS-C2960X-48FPD-L", "hardware_revision": "V02",
            "os_family": "IOS", "os_version": "15.2(7)E",
            "management_mode": "standalone", "transport": "ssh",
            "security_profile": "ssh2_host_key_pinned_read_only",
        },
        authorization={
            "reference": "AUTH-TEST-SYNTHETIC", "scope_sha256": "b" * 64,
            "valid_until": signed + timedelta(days=30), "isolated_lab": True,
            "read_only": True,
        },
        physical_evidence={
            "reference": "CONTROLLED-TEST-ARTIFACT", "sha256": ARTIFACT_HASH,
            "sanitized": True,
            "redaction_reviewers": ("test:redactor-a", "test:redactor-b"),
        },
        observed_at=observed, capabilities=capabilities,
        negative_tests=negative, operational_tests=operational,
        benchmark=benchmark, release_status=status,
        rollout_policy={
            "stages": ("canary", "pilot", "general"),
            "minimum_observation_hours": 1,
            "error_budget": {
                "max_error_rate_percent": 2,
                "max_partial_rate_percent": 5,
                "max_queue_lateness_p95_seconds": 30,
                "breach_action": "rollback",
            },
        },
        reviewers=reviewers, signed_at=signed,
        expires_at=signed + timedelta(days=90), production_accepted=False,
    )


def rollout(decision, stage, sequence):
    recorded = decision.signed_at + timedelta(hours=sequence * 1.25)
    return RolloutObservation(
        observation_id=f"rollout-s11-{stage}-{sequence}",
        decision_id=decision.decision_id,
        source_revision=SOURCE_REVISION, profile_id="cisco_ios",
        profile_revision=2, stage=stage,
        window_started_at=recorded - timedelta(minutes=65),
        observed_at=recorded - timedelta(minutes=1), recorded_at=recorded,
        device_count=2, job_count=100, error_count=0, partial_count=0,
        queue_lateness_p95_seconds=5, evidence_sha256="d" * 64,
    )


def test_supported_requires_complete_physical_operational_and_benchmark_gates():
    value = publish()
    validate_publish_decision(value)
    with pytest.raises(ValueError, match="supported_requires_current_24h_benchmark"):
        validate_publish_decision(value.model_copy(update={
            "benchmark": value.benchmark.model_copy(update={"metrics_complete": False})
        }))
    with pytest.raises(ValueError, match="supported_requires_all_declared_capabilities"):
        validate_publish_decision(value.model_copy(update={
            "capabilities": tuple(
                item.model_copy(update={"result": "partial"})
                if item.id == "network" else item for item in value.capabilities
            )
        }))
    with pytest.raises(ValueError, match="supported_requires_operational_and_rollback_tests"):
        validate_publish_decision(value.model_copy(update={
            "operational_tests": tuple(
                item.model_copy(update={"result": "not_run"})
                if item.id == "rollback_without_data_loss" else item
                for item in value.operational_tests
            )
        }))
    with pytest.raises(ValueError, match="physical_evidence_not_bound_to_all_results"):
        validate_publish_decision(value.model_copy(update={
            "negative_tests": tuple(
                item.model_copy(update={"evidence_sha256": "0" * 64})
                if item.id == "timeout" else item for item in value.negative_tests
            )
        }))
    future = now() + timedelta(minutes=10)
    with pytest.raises(ValueError, match="release_decision_signed_in_future"):
        validate_publish_decision(value.model_copy(update={
            "signed_at": future,
            "expires_at": future + timedelta(days=30),
        }))


def test_signed_decision_promotes_only_current_code_and_tampering_fails_closed(
    system, monkeypatch
):
    client, store, _, _ = system
    private, trusted = key_pair()
    decision = publish()
    save_release_decision(
        store, envelope(decision, private), trusted_keys=trusted,
        artifact_sha256=ARTIFACT_HASH,
        benchmark_artifact_sha256=ARTIFACT_HASH, actor="test:release",
    )
    pending = release_states(
        store, trusted_keys=trusted, source_revision=SOURCE_REVISION
    )[("cisco_ios", 2)]
    assert pending["release_status"] == "candidate"
    assert pending["release_decision"]["blocked_reasons"] == ["rollout_not_started"]
    for sequence, stage in enumerate(("canary", "pilot", "general"), start=1):
        observation = rollout(decision, stage, sequence)
        save_rollout_observation(
            store, envelope(observation, private), trusted_keys=trusted,
            artifact_sha256="d" * 64, actor="test:release",
        )
    assert release_states(
        store, trusted_keys=trusted, source_revision=SOURCE_REVISION
    )[("cisco_ios", 2)]["release_status"] == "supported"
    assert release_states(
        store, trusted_keys=trusted, source_revision="c" * 40
    ) == {}

    monkeypatch.setenv("NETSTUDIO_BUILD_REVISION", SOURCE_REVISION)
    trust_file = system[3].with_name("release-trust.json")
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    trust_file.write_text(
        '{"schema_version":1,"keys":[{"id":"release-test",'
        '"algorithm":"ed25519","public_key_base64":"'
        + base64.b64encode(public).decode() + '"}]}'
    )
    monkeypatch.setenv("NETSTUDIO_RELEASE_TRUST_ROOTS_FILE", str(trust_file))
    login(client)
    catalog = client.get("/api/v1/driver-catalog").json()
    ios = next(item for item in catalog["profiles"] if item["id"] == "cisco_ios")
    assert ios["release_status"] == "supported"
    assert ios["verification_status"] == "physical_validated"
    assert ios["release_decision"]["production_accepted"] is False

    created = add_device(
        client, name="Exact accepted Cisco", vendor="Cisco",
        model="WS-C2960X-48FPD-L", collector="cisco_ios",
        configured_profile_id="cisco_ios", management_mode="standalone",
    )
    device = store.get_device(created["id"]).model_copy(update={
        "os_version": "15.2(7)E", "driver_version": DRIVER_VERSION,
    })
    store.save_device(device)
    with store.engine.begin() as conn:
        record_collected_resolution(
            store, device, conn, observed_profile_id="cisco_ios",
            identity_evidence={
                "vendor": "Cisco", "model": "WS-C2960X-48FPD-L",
                "hardware_revision": "V02", "os_family": "IOS",
                "os_version": "15.2(7)E", "management_mode": "standalone",
            },
        )
    compatibility = client.get(
        f"/api/v1/devices/{created['id']}/compatibility"
    ).json()
    assert compatibility["release_status"] == "supported"
    assert compatibility["verification_status"] == "physical_validated"
    assert compatibility["acceptance"]["matching_unexpired_records"] == 5
    assert compatibility["release_decision"]["decision_id"] == decision.decision_id
    assert compatibility["release_decision"]["accepted_exact_model"] == "WS-C2960X-48FPD-L"
    assert compatibility["release_decision"]["accepted_hardware_revision"] == "V02"
    assert compatibility["release_decision"]["accepted_transport"] == "ssh"
    records = client.get("/api/v1/driver-release-decisions").json()["items"]
    assert records[0]["payload_sha256"]
    assert "payload" not in records[0]
    assert "signature" not in records[0]
    assert "reviewer" not in str(records[0])
    assert "CONTROLLED" not in str(records[0])

    with store.engine.begin() as conn:
        row = conn.execute(sa.select(store.driver_release_decisions.c.payload).where(
            store.driver_release_decisions.c.id == decision.decision_id
        )).scalar_one()
        conn.execute(store.driver_release_decisions.update().where(
            store.driver_release_decisions.c.id == decision.decision_id
        ).values(payload={**row, "release_status": "candidate"}))
    assert release_states(
        store, trusted_keys=trusted, source_revision=SOURCE_REVISION
    ) == {}
    trust_file.write_text("not-json")
    response = client.get("/api/v1/driver-catalog")
    assert response.status_code == 200
    ios = next(item for item in response.json()["profiles"] if item["id"] == "cisco_ios")
    assert ios["release_status"] == "experimental"


def test_artifact_hash_untrusted_signature_expiry_and_withdrawal_are_fail_closed(system):
    _, store, _, _ = system
    private, trusted = key_pair()
    decision = publish(decision_id="decision-s11-withdraw")
    signed = envelope(decision, private)
    with pytest.raises(ValueError, match="physical_evidence_hash_mismatch"):
        save_release_decision(
            store, signed, trusted_keys=trusted, artifact_sha256="0" * 64,
            benchmark_artifact_sha256=ARTIFACT_HASH,
            actor="test:release",
        )
    with pytest.raises(ValueError, match="release_signer_not_trusted"):
        save_release_decision(
            store, signed, trusted_keys={}, artifact_sha256=ARTIFACT_HASH,
            benchmark_artifact_sha256=ARTIFACT_HASH,
            actor="test:release",
        )
    with pytest.raises(ValueError, match="benchmark_evidence_hash_mismatch"):
        save_release_decision(
            store, signed, trusted_keys=trusted, artifact_sha256=ARTIFACT_HASH,
            benchmark_artifact_sha256="0" * 64, actor="test:release",
        )
    save_release_decision(
        store, signed, trusted_keys=trusted, artifact_sha256=ARTIFACT_HASH,
        benchmark_artifact_sha256=ARTIFACT_HASH,
        actor="test:release",
    )
    assert release_states(
        store, trusted_keys=trusted,
        source_revision=SOURCE_REVISION,
        at=decision.expires_at + timedelta(seconds=1),
    ) == {}

    withdrawal = WithdrawDecision(
        action="withdraw", decision_id="withdraw-s11-supported",
        supersedes_decision_id=decision.decision_id,
        source_revision=SOURCE_REVISION, catalog_revision=CATALOG_REVISION,
        profile_id="cisco_ios", profile_revision=2,
        reason_code="evidence_withdrawn",
        reviewers=(
            {"role": "security_reviewer", "reviewer_ref": "test:security", "decision": "approve"},
            {"role": "release_owner", "reviewer_ref": "test:release", "decision": "approve"},
        ),
        signed_at=decision.signed_at + timedelta(minutes=1),
        expires_at=decision.expires_at,
    )
    save_release_decision(
        store, envelope(withdrawal, private), trusted_keys=trusted,
        artifact_sha256=None, actor="test:release",
    )
    assert release_states(
        store, trusted_keys=trusted, source_revision=SOURCE_REVISION
    ) == {}
    assert acceptance_summary(
        store, "cisco_ios", 2, decision_id=decision.decision_id
    )["matching_unexpired_records"] == 0


def test_withdrawing_an_older_decision_does_not_hide_a_newer_publish(system):
    _, store, _, _ = system
    private, trusted = key_pair()
    older = publish(decision_id="decision-s11-older")
    newer = publish(decision_id="decision-s11-newer").model_copy(update={
        "signed_at": older.signed_at + timedelta(hours=1),
        "expires_at": older.expires_at + timedelta(hours=1),
    })
    for decision in (older, newer):
        save_release_decision(
            store, envelope(decision, private), trusted_keys=trusted,
            artifact_sha256=ARTIFACT_HASH,
            benchmark_artifact_sha256=ARTIFACT_HASH, actor="test:release",
        )
    withdrawal = WithdrawDecision(
        action="withdraw", decision_id="withdraw-s11-older",
        supersedes_decision_id=older.decision_id,
        source_revision=SOURCE_REVISION, catalog_revision=CATALOG_REVISION,
        profile_id="cisco_ios", profile_revision=2,
        reason_code="evidence_withdrawn",
        reviewers=(
            {"role": "security_reviewer", "reviewer_ref": "test:security", "decision": "approve"},
            {"role": "release_owner", "reviewer_ref": "test:release", "decision": "approve"},
        ),
        signed_at=newer.signed_at + timedelta(minutes=1),
        expires_at=newer.expires_at,
    )
    save_release_decision(
        store, envelope(withdrawal, private), trusted_keys=trusted,
        artifact_sha256=None, actor="test:release",
    )
    state = release_states(
        store, trusted_keys=trusted, source_revision=SOURCE_REVISION,
    )[("cisco_ios", 2)]
    assert state["release_decision"]["decision_id"] == newer.decision_id
    assert acceptance_summary(
        store, "cisco_ios", 2, decision_id=newer.decision_id
    )["matching_unexpired_records"] == 5


def test_rollout_error_budget_breach_automatically_removes_supported_state(system):
    _, store, _, _ = system
    private, trusted = key_pair()
    decision = publish(decision_id="decision-s11-rollout")
    save_release_decision(
        store, envelope(decision, private), trusted_keys=trusted,
        artifact_sha256=ARTIFACT_HASH,
        benchmark_artifact_sha256=ARTIFACT_HASH, actor="test:release",
    )
    recorded = decision.signed_at + timedelta(hours=2)
    observation = RolloutObservation(
        observation_id="rollout-s11-canary", decision_id=decision.decision_id,
        source_revision=SOURCE_REVISION, profile_id="cisco_ios",
        profile_revision=2, stage="canary",
        window_started_at=recorded - timedelta(hours=2),
        observed_at=recorded - timedelta(minutes=1), recorded_at=recorded,
        device_count=2, job_count=100, error_count=3, partial_count=0,
        queue_lateness_p95_seconds=5, evidence_sha256="d" * 64,
    )
    with pytest.raises(ValueError, match="rollout_evidence_hash_mismatch"):
        save_rollout_observation(
            store, envelope(observation, private), trusted_keys=trusted,
            artifact_sha256="0" * 64, actor="test:release",
        )
    save_rollout_observation(
        store, envelope(observation, private), trusted_keys=trusted,
        artifact_sha256="d" * 64, actor="test:release",
    )
    state = release_states(
        store, trusted_keys=trusted, source_revision=SOURCE_REVISION,
    )[("cisco_ios", 2)]
    assert state["release_status"] == "experimental"
    assert state["release_decision"]["rollout_stage"] == "canary"
    assert state["release_decision"]["blocked_reasons"] == [
        "rollout_error_rate_exceeded"
    ]
    recovered = observation.model_copy(update={
        "observation_id": "rollout-s11-canary-retry",
        "recorded_at": recorded + timedelta(minutes=10),
        "observed_at": recorded + timedelta(minutes=9),
        "window_started_at": recorded - timedelta(hours=2),
        "error_count": 0,
    })
    save_rollout_observation(
        store, envelope(recovered, private), trusted_keys=trusted,
        artifact_sha256="d" * 64, actor="test:release",
    )
    assert release_states(
        store, trusted_keys=trusted, source_revision=SOURCE_REVISION,
    )[("cisco_ios", 2)]["release_status"] == "experimental"


def test_rollout_cannot_skip_or_regress_stages(system):
    _, store, _, _ = system
    private, trusted = key_pair()
    decision = publish(decision_id="decision-s11-stage-order")
    save_release_decision(
        store, envelope(decision, private), trusted_keys=trusted,
        artifact_sha256=ARTIFACT_HASH,
        benchmark_artifact_sha256=ARTIFACT_HASH, actor="test:release",
    )
    general = rollout(decision, "general", 1)
    with pytest.raises(ValueError, match="rollout_previous_stage_not_accepted"):
        save_rollout_observation(
            store, envelope(general, private), trusted_keys=trusted,
            artifact_sha256="d" * 64, actor="test:release",
        )
    for sequence, stage in enumerate(("canary", "pilot"), start=1):
        observation = rollout(decision, stage, sequence)
        save_rollout_observation(
            store, envelope(observation, private), trusted_keys=trusted,
            artifact_sha256="d" * 64, actor="test:release",
        )
    regression = rollout(decision, "canary", 3).model_copy(update={
        "observation_id": "rollout-s11-canary-regression",
    })
    with pytest.raises(ValueError, match="rollout_stage_regression"):
        save_rollout_observation(
            store, envelope(regression, private), trusted_keys=trusted,
            artifact_sha256="d" * 64, actor="test:release",
        )


def test_future_rollout_observation_is_rejected(system):
    _, store, _, _ = system
    private, trusted = key_pair()
    decision = publish(decision_id="decision-s11-future-rollout")
    save_release_decision(
        store, envelope(decision, private), trusted_keys=trusted,
        artifact_sha256=ARTIFACT_HASH,
        benchmark_artifact_sha256=ARTIFACT_HASH, actor="test:release",
    )
    future = now() + timedelta(minutes=10)
    observation = RolloutObservation(
        observation_id="rollout-s11-future", decision_id=decision.decision_id,
        source_revision=SOURCE_REVISION, profile_id="cisco_ios",
        profile_revision=2, stage="canary",
        window_started_at=future - timedelta(hours=2),
        observed_at=future - timedelta(minutes=1), recorded_at=future,
        device_count=1, job_count=1, error_count=0, partial_count=0,
        queue_lateness_p95_seconds=1, evidence_sha256="d" * 64,
    )
    with pytest.raises(ValueError, match="rollout_observation_recorded_in_future"):
        save_rollout_observation(
            store, envelope(observation, private), trusted_keys=trusted,
            artifact_sha256="d" * 64, actor="test:release",
        )


def test_latest_withdrawn_acceptance_row_no_longer_counts(system, monkeypatch):
    _, store, _, _ = system
    monkeypatch.setenv("NETSTUDIO_BUILD_REVISION", SOURCE_REVISION)
    at = now()
    common = dict(
        source_revision=SOURCE_REVISION, profile_id="cisco_ios",
        profile_revision=2, vendor="Cisco", model_family="WS-C2960X-*",
        exact_model="WS-C2960X-48FPD-L", hardware_revision="V02",
        os_family="IOS", os_version="15.2(7)E", management_mode="standalone",
        transport="ssh", security_profile="ssh2_host_key_pinned",
        capability_id="inventory", parser_version=DRIVER_VERSION,
        test_suite_revision="compat-physical-v1", evidence_ref="CONTROLLED",
        evidence_sha256="e" * 64, evidence_sanitized=True,
        observed_at=at - timedelta(minutes=10), expires_at=at + timedelta(days=30),
        reviewed_by="test:reviewer",
    )
    with store.engine.begin() as conn:
        save_acceptance_record(store, AcceptanceRecord(
            id="accept-pass", result="pass", validation_level="physical_validated",
            recorded_at=at - timedelta(minutes=2), **common,
        ), actor="test:release", conn=conn)
        save_acceptance_record(store, AcceptanceRecord(
            id="accept-withdrawn", result="withdrawn",
            validation_level="physical_validated", recorded_at=at - timedelta(minutes=1),
            **common,
        ), actor="test:release", conn=conn)
    assert acceptance_summary(store, "cisco_ios", 2) == {
        "highest_level": "not_tested",
        "matching_unexpired_records": 0,
        "production_accepted": False,
    }


def test_audit_reader_is_required_for_release_decision_listing(system):
    client, *_ = system
    login(client, "viewer")
    assert client.get("/api/v1/driver-release-decisions").status_code == 403
