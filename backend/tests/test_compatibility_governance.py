"""S00 compatibility-governance decisions; not runtime driver support tests."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "uyumluluk-uygulama"
SCOPE = json.loads((DOCS / "S00_KAPSAM_KARARLARI.json").read_text())


def _matrix_profile_ids() -> set[str]:
    matrix = (ROOT / "docs" / "NetStudio_Switch_OS_SSH_SNMP_Uyumluluk_Matrisi.md").read_text()
    values = set(re.findall(r"`([a-z][a-z0-9_]+)`", matrix))
    return values - set(SCOPE["non_profile_matrix_tokens"])


def _trace_profile_ids() -> list[str]:
    trace = (DOCS / "SURUCU_IZLENEBILIRLIK_MATRISI.md").read_text()
    profile_sections = trace.split("## 2. P0", 1)[1].split("## 7. Eski", 1)[0]
    return re.findall(r"^\|\s*`([a-z][a-z0-9_]+)`\s*\|", profile_sections, re.MULTILINE)


def test_s00_profile_scope_matches_matrix_and_traceability_document():
    profiles = SCOPE["profiles"]
    ids = [profile["id"] for profile in profiles]
    assert len(ids) == len(set(ids)) == 38
    assert set(ids) == _matrix_profile_ids()
    trace_ids = _trace_profile_ids()
    assert len(trace_ids) == len(set(trace_ids)) == 38
    assert set(trace_ids) == set(ids)


def test_s00_statuses_and_supported_release_gate_are_closed():
    taxonomies = SCOPE["taxonomies"]
    for profile in SCOPE["profiles"]:
        assert profile["implementation_status"] in taxonomies["implementation"]
        assert profile["verification_status"] in taxonomies["verification"]
        assert profile["release_status"] in taxonomies["release"]
        assert profile["release_status"] != "supported"
    gate = SCOPE["release_invariants"]
    assert set(gate["supported_requires"]) == {
        "implemented",
        "physical_validated",
        "matching_unexpired_acceptance_record",
        "trusted_signed_release_decision",
        "rollback_without_data_loss",
        "current_24h_benchmark",
        "healthy_general_rollout",
    }
    assert set(gate["candidate_requires"]) == {
        "implemented", "physical_validated", "migration_upgrade",
        "browser_e2e", "lab_owner_review", "release_owner_review",
    }
    assert gate["physical_evidence_max_age_days"] == 180
    assert gate["benchmark_max_age_days"] == 90
    assert gate["rollout_error_budget_breach_removes_supported"] is True
    assert gate["production_accepted_default"] is False
    assert gate["fixture_or_lab_may_not_assert_physical"] is True


def test_s00_legacy_aliases_have_one_safe_target_and_no_cycles():
    canonical = {profile["id"] for profile in SCOPE["profiles"]}
    decisions = SCOPE["legacy_id_decisions"]
    legacy_ids = [decision["legacy_id"] for decision in decisions]
    assert len(legacy_ids) == len(set(legacy_ids))
    graph = {
        decision["legacy_id"]: decision["target_profile_id"]
        for decision in decisions
        if decision["target_profile_id"] is not None
    }
    assert all(target in canonical for target in graph.values())
    for start in graph:
        seen = set()
        node = start
        while node in graph:
            assert node not in seen, f"alias cycle at {node}"
            seen.add(node)
            node = graph[node]
    fortinet = next(item for item in decisions if item["legacy_id"] == "fortinet")
    assert fortinet == {
        "legacy_id": "fortinet",
        "target_profile_id": None,
        "resolution": "manual_resolution_required",
        "automatic": False,
    }


def test_s00_accepted_and_pending_adrs_have_owners_and_milestone_deadlines():
    accepted = set(SCOPE["accepted_adrs"])
    assert accepted == {
        "ADR-COMPAT-001",
        "ADR-COMPAT-002",
        "ADR-COMPAT-003",
        "ADR-COMPAT-004",
        "ADR-COMPAT-005",
        "ADR-COMPAT-006",
    }
    for identifier in accepted:
        path = next((DOCS / "adr").glob(f"{identifier}-*.md"))
        text = path.read_text()
        assert "| Durum | Kabul edildi" in text
    pending = SCOPE["pending_decision_gates"]
    assert pending == []
    assert "ADR-COMPAT-004" in SCOPE["accepted_adrs"]


def test_linux_ssh_remains_infrastructure_not_a_nos_profile():
    canonical = {profile["id"] for profile in SCOPE["profiles"]}
    adapters = {adapter["id"]: adapter for adapter in SCOPE["infrastructure_adapters"]}
    assert "linux_ssh" not in canonical
    assert adapters["linux_ssh"]["role"] == "generic_read_only_infrastructure_adapter"
    assert set(adapters["linux_ssh"]["not_equivalent_to"]) == {
        "dell_sonic",
        "nvidia_cumulus_linux",
        "sonic_nos",
    }


def test_compatibility_document_relative_links_resolve():
    missing = []
    for source in DOCS.rglob("*.md"):
        for raw_target in re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", source.read_text()):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (source.parent / target).resolve().exists():
                missing.append(f"{source.relative_to(ROOT)} -> {raw_target}")
    assert not missing, "missing Markdown targets:\n" + "\n".join(missing)
