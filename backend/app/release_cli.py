"""Offline S11 acceptance/release tooling.

Examples are documented in ``docs/uyumluluk-uygulama/S11_OPERASYON_REHBERI.md``.
The CLI never prints private keys, raw device output or database secrets.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import sqlalchemy as sa

from .database import Store
from .release_acceptance import (
    RELEASE_PAYLOAD,
    RolloutObservation,
    Signature,
    SignedEnvelope,
    canonical_bytes,
    load_trust_roots,
    save_release_decision,
    save_rollout_observation,
    validate_trust_roots_file,
    verify_envelope,
    verify_rollout_envelope,
)


def _read_json(path: str) -> dict:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text())


def _artifact_sha256(path: str | None) -> str | None:
    if not path:
        return None
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_key(path: str):
    selected = Path(path)
    if selected.stat().st_mode & 0o077:
        raise SystemExit("Private key must not be group/world accessible (use chmod 600).")
    key = serialization.load_pem_private_key(selected.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("Only Ed25519 private keys are accepted.")
    return key


def _install_trust_roots(source: str, destination: str) -> None:
    roots = validate_trust_roots_file(source)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".release-trust-roots-", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(roots.model_dump(mode="json"), handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(json.dumps({"status": "installed", "key_count": len(roots.keys)}))


def _sign(payload_path: str, private_key_path: str, key_id: str, kind: str) -> None:
    raw = _read_json(payload_path)
    payload = (
        RELEASE_PAYLOAD.validate_python(raw)
        if kind == "decision" else RolloutObservation.model_validate(raw)
    )
    signature = _private_key(private_key_path).sign(canonical_bytes(payload))
    envelope = {
        "payload": payload.model_dump(mode="json"),
        "signature": Signature(
            algorithm="ed25519",
            key_id=key_id,
            value=base64.b64encode(signature).decode(),
        ).model_dump(mode="json"),
    }
    print(json.dumps(envelope, indent=2, ensure_ascii=False))


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = max(0, min(len(values) - 1, int((len(values) - 1) * quantile + .999999)))
    return round(values[index], 3)


def _benchmark_snapshot(store: Store, since: datetime, until: datetime) -> dict:
    if since.tzinfo is None or until.tzinfo is None or until <= since:
        raise SystemExit("--since/--until must be timezone-aware and form a positive window.")
    jobs = store.jobs_repository.jobs
    contexts = store.job_contexts
    with store.engine.connect() as conn:
        rows = list(conn.execute(sa.select(
            jobs.c.id, jobs.c.device_id, jobs.c.status, jobs.c.created_at,
            jobs.c.started_at, jobs.c.finished_at, jobs.c.error_code,
            contexts.c.groups,
        ).join(contexts, contexts.c.job_id == jobs.c.id).where(
            jobs.c.created_at >= since, jobs.c.created_at <= until,
        )).mappings())
        sample_count = conn.execute(sa.select(sa.func.count()).select_from(
            store.metric_samples
        ).where(
            store.metric_samples.c.observed_at >= since,
            store.metric_samples.c.observed_at <= until,
        )).scalar_one()
        history_count = conn.execute(sa.select(sa.func.count()).select_from(
            store.collection_history
        ).where(
            store.collection_history.c.observed_at >= since,
            store.collection_history.c.observed_at <= until,
        )).scalar_one()
    durations = [
        (row["finished_at"] - row["started_at"]).total_seconds()
        for row in rows if row["started_at"] and row["finished_at"]
    ]
    lateness = [
        max(0, (row["started_at"] - row["created_at"]).total_seconds())
        for row in rows if row["started_at"]
    ]
    failed = sum(row["status"] in {"failed", "cancelled"} for row in rows)
    return {
        "schema_version": 1,
        "window": {
            "started_at": since.isoformat(), "completed_at": until.isoformat(),
            "duration_hours": round((until - since).total_seconds() / 3600, 3),
        },
        "database_observations": {
            "device_count": len({row["device_id"] for row in rows}),
            "job_count": len(rows), "failed_job_count": failed,
            "error_rate_percent": round(failed / len(rows) * 100, 4) if rows else None,
            "collection_duration_seconds": {
                "p50": _percentile(durations, .50),
                "p95": _percentile(durations, .95),
                "p99": _percentile(durations, .99),
            },
            "queue_lateness_seconds": {
                "p50": _percentile(lateness, .50),
                "p95": _percentile(lateness, .95),
                "p99": _percentile(lateness, .99),
            },
            "metric_sample_rows": sample_count,
            "collection_history_rows": history_count,
        },
        "status": "REQUIRES BENCHMARK",
        "missing_external_measurements": [
            "api_db_worker_cpu_rss", "postgresql_io_and_storage_bytes",
            "device_cpu_impact", "latency_and_loss_distribution",
            "transport_distribution", "rate_limit_and_partial_rate",
            "worker_restart_and_db_maintenance_timestamps",
        ],
        "note": "This snapshot is input evidence only; it never promotes support by itself.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="NetStudio S11 release acceptance")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, kind in (("sign-decision", "decision"), ("sign-rollout", "rollout")):
        command = commands.add_parser(name)
        command.add_argument("--payload", required=True)
        command.add_argument("--private-key", required=True)
        command.add_argument("--key-id", required=True)
        command.set_defaults(kind=kind)
    for name, kind in (("verify-decision", "decision"), ("verify-rollout", "rollout")):
        command = commands.add_parser(name)
        command.add_argument("--bundle", required=True)
        command.add_argument("--trust-roots", required=True)
        command.set_defaults(kind=kind)
    command = commands.add_parser("import-decision")
    command.add_argument("--bundle", required=True)
    command.add_argument("--trust-roots", required=True)
    command.add_argument("--artifact")
    command.add_argument("--benchmark-artifact")
    command.add_argument("--actor", required=True)
    command = commands.add_parser("import-rollout")
    command.add_argument("--bundle", required=True)
    command.add_argument("--trust-roots", required=True)
    command.add_argument("--artifact", required=True)
    command.add_argument("--actor", required=True)
    command = commands.add_parser("benchmark-snapshot")
    command.add_argument("--since", required=True)
    command.add_argument("--until", default=datetime.now(timezone.utc).isoformat())
    command = commands.add_parser("install-trust-roots")
    command.add_argument("--source", required=True)
    command.add_argument(
        "--destination",
        default=os.getenv(
            "NETSTUDIO_RELEASE_TRUST_ROOTS_FILE",
            "/run/release-state/trust-roots.json",
        ),
    )
    args = parser.parse_args()

    if args.command.startswith("sign-"):
        _sign(args.payload, args.private_key, args.key_id, args.kind)
        return
    if args.command == "benchmark-snapshot":
        report = _benchmark_snapshot(
            Store(), datetime.fromisoformat(args.since), datetime.fromisoformat(args.until)
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    if args.command == "install-trust-roots":
        _install_trust_roots(args.source, args.destination)
        return

    envelope = SignedEnvelope.model_validate(_read_json(args.bundle))
    trusted = load_trust_roots(args.trust_roots)
    if args.command.startswith("verify-"):
        payload = (
            verify_envelope(envelope, trusted)
            if args.kind == "decision" else verify_rollout_envelope(envelope, trusted)
        )
        print(json.dumps({
            "status": "verified",
            "id": getattr(payload, "decision_id", None) or payload.observation_id,
        }))
        return

    store = Store()
    if args.command == "import-decision":
        payload = save_release_decision(
            store, envelope, trusted_keys=trusted,
            artifact_sha256=_artifact_sha256(args.artifact),
            benchmark_artifact_sha256=_artifact_sha256(args.benchmark_artifact),
            actor=args.actor,
        )
        print(json.dumps({"status": "imported", "decision_id": payload.decision_id}))
    else:
        payload = save_rollout_observation(
            store, envelope, trusted_keys=trusted,
            artifact_sha256=_artifact_sha256(args.artifact), actor=args.actor,
        )
        print(json.dumps({"status": "imported", "observation_id": payload.observation_id}))


if __name__ == "__main__":
    main()
