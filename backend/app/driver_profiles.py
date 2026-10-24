"""Typed, code-owned compatibility manifests.

The registry describes support boundaries; it does not turn catalog-only
profiles into runnable collectors or physical-device acceptance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .driver_manifests import (
    cisco_ios as ios_manifest,
    cisco_iosxe as iosxe_manifest,
    cisco_nxos as nxos_manifest,
    huawei_vrp_v200 as vrp_v200_manifest,
    juniper_junos as junos_manifest,
    linux_ssh as linux_manifest,
)


DRIVER_VERSION = "2026.10.23.4"
CATALOG_REVISION = "2026.10.23.3"
NTC_VERSION = "9.3.0"
GROUPS = ("fast", "health", "network", "inventory")
DATA_CONTRACT = {
    "fast": [
        "admin_up", "oper_up", "capacity_bps", "duplex", "rx_bps",
        "tx_bps", "in_octets", "out_octets", "errors", "discards",
        "tx_errors", "tx_discards",
    ],
    "health": [
        "cpu_percent", "memory_percent", "temperature_c", "fan",
        "power_supply", "poe_watts",
    ],
    "network": [
        "addresses", "vrf", "vlan", "lag", "fdb", "arp", "ndp",
        "lldp", "cdp", "dom",
    ],
    "inventory": [
        "model", "serial", "os_version", "system_identity", "chassis",
        "stack", "modules", "breakout",
    ],
}
REFERENCES = {
    "cisco": "https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst2960x/software/15-2_7_e/command_reference/b_1527_2960x_cr/interface_and_hardware_commands.html",
    "huawei": "https://info.support.huawei.com/enterprise/en/doc/EDOC1100333403/cdd85713/basic-interface-configuration-commands",
    "junos": "https://www.juniper.net/documentation/us/en/software/junos/netconf/junos-xml-protocol/topics/task/junos-xml-protocol-rpcs-and-xml-mapping.html",
    "nxos": "https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/103x/command-reference/show/b_n9k_show_commands_103x/m_show_xml.html",
}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

ImplementationStatus = Literal[
    "catalog_only", "implemented", "blocked", "unsupported_by_protocol",
    "unsupported_by_policy", "retired",
]
VerificationStatus = Literal[
    "not_tested", "unit_verified", "fixture_verified",
    "transport_lab_validated", "physical_validated",
]
ReleaseStatus = Literal["hidden", "experimental", "candidate", "supported"]
TransportKind = Literal["ssh", "snmp", "api"]
TransportState = Literal[
    "implemented", "planned", "blocked", "unsupported_by_protocol",
    "unsupported_by_policy",
]
ManagementMode = Literal[
    "standalone", "controller_managed", "cloud_managed", "local_managed",
    "unknown",
]
AliasPolicy = Literal[
    "read_compatibility_alias_with_identity_revalidation",
    "conditional_identity_match",
    "manual_resolution_required",
]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IdentitySummary(FrozenModel):
    vendors: tuple[str, ...]
    os_families: tuple[str, ...]
    management_modes: tuple[ManagementMode, ...]
    model_patterns: tuple[str, ...] = ()
    version_constraints: tuple[str, ...] = ()


class TransportSummary(FrozenModel):
    kind: TransportKind
    state: TransportState
    security: tuple[str, ...] = ()
    versions: tuple[str, ...] = ()
    decision_gate: str | None = None


class CapabilitySummary(FrozenModel):
    group: Literal["fast", "health", "network", "inventory"]
    fields: tuple[str, ...]
    sources: tuple[TransportKind, ...]
    source_fields: dict[TransportKind, tuple[str, ...]] = Field(default_factory=dict)
    verification_status: VerificationStatus


class AcceptanceSummary(FrozenModel):
    highest_level: VerificationStatus
    matching_unexpired_records: int = Field(default=0, ge=0)
    production_accepted: bool = False


@dataclass(frozen=True)
class Command:
    text: str
    group: str
    parser: str
    reference: str
    required: bool = False
    privilege: str = "read-only operational; device RBAC may restrict individual commands"
    timeout_seconds: int = 20
    max_bytes: int = 2_000_000
    parser_version: str = DRIVER_VERSION


class DriverProfile(FrozenModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    profile_revision: int = Field(default=1, ge=1)
    label: str = Field(min_length=1, max_length=120)
    wave: Literal["P0", "P1", "P2", "P3", "P4"]
    implementation_status: ImplementationStatus
    verification_status: VerificationStatus
    release_status: ReleaseStatus
    identity: IdentitySummary
    transports: tuple[TransportSummary, ...]
    capabilities: tuple[CapabilitySummary, ...] = ()
    acceptance: AcceptanceSummary
    runtime_driver_id: str | None = None
    adapter: str | None = None
    commands: tuple[Command, ...] = ()
    tested_versions: tuple[str, ...] = ()


class InfrastructureAdapter(FrozenModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    revision: int = Field(default=1, ge=1)
    label: str
    role: str
    runtime_driver_id: str
    adapter: str
    implementation_status: Literal["implemented"] = "implemented"
    verification_status: VerificationStatus
    release_status: ReleaseStatus
    transports: tuple[TransportSummary, ...]
    capabilities: tuple[CapabilitySummary, ...]
    tested_versions: tuple[str, ...] = ()
    not_equivalent_to: tuple[str, ...] = ()


class ProfileAlias(FrozenModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    target_profile_id: str | None = None
    policy: AliasPolicy
    automatic: bool = False


class LegacyCatalogBinding(FrozenModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str = Field(min_length=1, max_length=120)
    available: bool
    profile_id: str | None = None
    adapter_id: str | None = None


class ProfileResolution(FrozenModel):
    requested_id: str
    status: Literal["canonical", "alias", "manual_resolution_required", "unknown"]
    canonical_profile_id: str | None = None
    policy: AliasPolicy | None = None


def commands(reference: str, rows: Sequence[tuple[str, str, str, bool]]) -> tuple[Command, ...]:
    return tuple(
        Command(text, group, parser, REFERENCES[reference], required)
        for text, group, parser, required in rows
    )


IOS = commands("cisco", ios_manifest.COMMAND_ROWS)
IOSXE = commands("cisco", iosxe_manifest.COMMAND_ROWS)
VRP = commands("huawei", vrp_v200_manifest.COMMAND_ROWS)
JUNOS = commands("junos", junos_manifest.COMMAND_ROWS)
NXOS = commands("nxos", nxos_manifest.COMMAND_ROWS)

P0_CAPABILITIES = {
    "cisco_ios": ios_manifest.CAPABILITIES,
    "cisco_iosxe": iosxe_manifest.CAPABILITIES,
    "cisco_nxos": nxos_manifest.CAPABILITIES,
    "huawei_vrp_v200": vrp_v200_manifest.CAPABILITIES,
    "juniper_junos": junos_manifest.CAPABILITIES,
}


def _identity(
    vendor: str,
    os_family: str,
    modes: tuple[ManagementMode, ...] = ("standalone",),
    *,
    models: tuple[str, ...] = (),
    versions: tuple[str, ...] = (),
) -> IdentitySummary:
    return IdentitySummary(
        vendors=(vendor,), os_families=(os_family,), management_modes=modes,
        model_patterns=models, version_constraints=versions,
    )


def _transport(
    kind: TransportKind,
    state: TransportState,
    *,
    versions: tuple[str, ...] = (),
    decision_gate: str | None = None,
) -> TransportSummary:
    security = {
        "ssh": ("host_key_pinning", "read_only_allowlist"),
        "snmp": ("read_only", "bounded_oid_allowlist"),
        "api": ("tls_validation_required", "read_only_scope_required"),
    }[kind]
    return TransportSummary(
        kind=kind, state=state, security=security, versions=versions,
        decision_gate=decision_gate,
    )


SSH_IMPLEMENTED = _transport("ssh", "implemented", versions=("ssh2",))
SNMP_IMPLEMENTED = _transport("snmp", "implemented", versions=("v3_authpriv",))
SSH_PLANNED = _transport("ssh", "planned", versions=("ssh2",))
SNMP_PLANNED = _transport("snmp", "planned", versions=("v3_authpriv",))
API_BLOCKED = _transport("api", "blocked", decision_gate="ADR-COMPAT-004")
SSH_UNSUPPORTED = _transport("ssh", "unsupported_by_protocol")
SNMP_UNSUPPORTED = _transport("snmp", "unsupported_by_protocol")
API_UNSUPPORTED = _transport("api", "unsupported_by_protocol")
SNMP_V2C_BLOCKED = _transport(
    "snmp", "blocked", versions=("v2c",), decision_gate="ADR-COMPAT-003",
)


def _capabilities(
    groups: dict[str, dict[TransportKind, Sequence[str]]],
    verification: VerificationStatus,
) -> tuple[CapabilitySummary, ...]:
    def summary(group: str) -> CapabilitySummary:
        by_source = {
            source: tuple(fields) for source, fields in groups[group].items()
            if fields
        }
        union = tuple(
            field for field in DATA_CONTRACT[group]
            if any(field in fields for fields in by_source.values())
        )
        return CapabilitySummary(
            group=group, fields=union, sources=tuple(by_source),
            source_fields=by_source, verification_status=verification,
        )
    return tuple(
        summary(group)
        for group in GROUPS
        if groups.get(group)
    )


def _profile(
    identifier: str,
    label: str,
    wave: Literal["P0", "P1", "P2", "P3", "P4"],
    identity: IdentitySummary,
    transports: tuple[TransportSummary, ...],
    *,
    implementation: ImplementationStatus = "catalog_only",
    verification: VerificationStatus = "not_tested",
    release: ReleaseStatus = "hidden",
    runtime_driver_id: str | None = None,
    adapter: str | None = None,
    command_plan: tuple[Command, ...] = (),
    capability_groups: dict[str, dict[TransportKind, Sequence[str]]] | None = None,
    tested_versions: tuple[str, ...] = (),
    profile_revision: int = 1,
) -> DriverProfile:
    return DriverProfile(
        id=identifier,
        profile_revision=profile_revision,
        label=label,
        wave=wave,
        implementation_status=implementation,
        verification_status=verification,
        release_status=release,
        identity=identity,
        transports=transports,
        capabilities=_capabilities(capability_groups or {}, verification),
        acceptance=AcceptanceSummary(highest_level=verification),
        runtime_driver_id=runtime_driver_id,
        adapter=adapter,
        commands=command_plan,
        tested_versions=tested_versions,
    )


PROFILES = (
    _profile(
        "cisco_ios", "Cisco IOS", "P0",
        _identity("Cisco", "IOS", models=("WS-C2960X-*",), versions=("15.2(*)E*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED),
        implementation="implemented", verification="fixture_verified",
        release="experimental", runtime_driver_id="cisco_ios",
        adapter="ssh_cli", command_plan=IOS,
        capability_groups=P0_CAPABILITIES["cisco_ios"], profile_revision=2,
        tested_versions=("Catalyst 2960-X / IOS 15.2(7)E sanitized fixtures",),
    ),
    _profile(
        "cisco_iosxe", "Cisco IOS-XE", "P0",
        _identity("Cisco", "IOS-XE", models=("C9200*", "C9300*"), versions=("17.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="cisco_iosxe", adapter="ssh_cli", command_plan=IOSXE,
        capability_groups=P0_CAPABILITIES["cisco_iosxe"], profile_revision=2,
        tested_versions=(
            "C9200L-24P-4G / IOS-XE 17.12.3 synthetic sanitized fixture",
            "C9300-24T / IOS-XE 17.9.5 synthetic sanitized fixture",
        ),
    ),
    _profile(
        "cisco_nxos", "Cisco NX-OS", "P0", _identity("Cisco", "NX-OS"),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="unit_verified", release="experimental",
        runtime_driver_id="cisco_nxos", adapter="ssh_cli_json",
        command_plan=NXOS, capability_groups=P0_CAPABILITIES["cisco_nxos"],
        profile_revision=2,
        tested_versions=("NX-OS JSON synthetic parser corpus",),
    ),
    _profile(
        "huawei_vrp_v200", "Huawei VRP V200", "P0",
        _identity("Huawei", "VRP V200", models=("S5700*",), versions=("*V200*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="huawei_vrp", adapter="ssh_cli", command_plan=VRP,
        capability_groups=P0_CAPABILITIES["huawei_vrp_v200"], profile_revision=2,
        tested_versions=("S5700 / VRP V200 sanitized fixtures",),
    ),
    _profile(
        "juniper_junos", "Juniper Junos", "P0", _identity("Juniper", "Junos OS"),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="unit_verified", release="experimental",
        runtime_driver_id="juniper_junos", adapter="ssh_xml",
        command_plan=JUNOS, capability_groups=P0_CAPABILITIES["juniper_junos"],
        profile_revision=2,
        tested_versions=("Classic Junos XML synthetic parser corpus",),
    ),
    _profile("aruba_aoscx", "Aruba AOS-CX", "P1", _identity("HPE Aruba Networking", "AOS-CX"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("aruba_aoss", "Aruba AOS-Switch", "P1", _identity("HPE Aruba Networking", "AOS-Switch"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("arista_eos", "Arista EOS", "P1", _identity("Arista Networks", "EOS"), (SSH_PLANNED, SNMP_PLANNED, API_BLOCKED)),
    _profile("hpe_comware", "HPE Comware", "P1", _identity("HPE Aruba Networking", "Comware"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("h3c_comware7", "H3C Comware V7", "P1", _identity("H3C", "Comware V7"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("mikrotik_routeros", "MikroTik RouterOS", "P1", _identity("MikroTik", "RouterOS"), (SSH_PLANNED, SNMP_PLANNED, API_BLOCKED)),
    _profile("dell_os10", "Dell SmartFabric OS10", "P2", _identity("Dell Technologies", "SmartFabric OS10"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("dell_os9", "Dell Networking OS9", "P2", _identity("Dell Technologies", "OS9"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("dell_os6", "Dell Networking OS6", "P2", _identity("Dell Technologies", "OS6"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("extreme_exos", "Extreme Switch Engine", "P2", _identity("Extreme Networks", "ExtremeXOS"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("extreme_fabric_engine", "Extreme Fabric Engine", "P2", _identity("Extreme Networks", "Fabric Engine"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("extreme_slxos", "Extreme SLX-OS", "P2", _identity("Extreme Networks", "SLX-OS"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("fortinet_fortiswitchos", "Fortinet FortiSwitchOS", "P2", _identity("Fortinet", "FortiSwitchOS"), (SSH_PLANNED, SNMP_PLANNED, API_BLOCKED)),
    _profile("fortinet_fortiswitch_fortilink", "Fortinet FortiSwitchOS (FortiLink)", "P2", _identity("Fortinet", "FortiSwitchOS", ("controller_managed",)), (API_BLOCKED, SNMP_PLANNED)),
    _profile("tplink_omada_managed", "TP-Link Omada Managed", "P2", _identity("TP-Link", "Omada Managed"), (SSH_PLANNED, SNMP_PLANNED, API_BLOCKED)),
    _profile("tplink_omada_pro", "TP-Link Omada Pro", "P2", _identity("TP-Link", "Omada Pro"), (SSH_PLANNED, SNMP_PLANNED, API_BLOCKED)),
    _profile("ubiquiti_unifi_switch", "Ubiquiti UniFi Switch", "P2", _identity("Ubiquiti", "UniFi Switch", ("controller_managed",)), (API_BLOCKED, SNMP_PLANNED)),
    _profile("ubiquiti_unifi_no_snmp", "Ubiquiti UniFi Switch (SNMP yok)", "P2", _identity("Ubiquiti", "UniFi Switch", ("controller_managed",)), (API_BLOCKED, SNMP_UNSUPPORTED)),
    _profile("ubiquiti_edgeswitch", "Ubiquiti EdgeSwitch", "P2", _identity("Ubiquiti", "EdgeSwitch OS"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("h3c_comware5", "H3C Comware V5", "P3", _identity("H3C", "Comware V5"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("h3c_comware9", "H3C Comware V9", "P3", _identity("H3C", "Comware V9"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("huawei_vrp_v600", "Huawei VRP V600", "P3", _identity("Huawei", "VRP V600"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("juniper_junos_evolved", "Juniper Junos OS Evolved", "P3", _identity("Juniper", "Junos OS Evolved"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("dell_sonic", "Dell Enterprise SONiC", "P3", _identity("Dell Technologies", "Enterprise SONiC"), (SSH_PLANNED, SNMP_PLANNED, API_BLOCKED)),
    _profile("nvidia_cumulus_linux", "NVIDIA Cumulus Linux", "P3", _identity("NVIDIA Networking", "Cumulus Linux"), (SSH_PLANNED, SNMP_PLANNED, API_BLOCKED)),
    _profile("nvidia_onyx", "NVIDIA Onyx", "P3", _identity("NVIDIA Networking", "Onyx"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("sonic_nos", "SONiC NOS", "P3", _identity("Multiple", "SONiC"), (SSH_PLANNED, SNMP_PLANNED, API_BLOCKED)),
    _profile("cisco_business", "Cisco Business Switch", "P3", _identity("Cisco", "Cisco Business firmware"), (SSH_PLANNED, SNMP_PLANNED)),
    _profile("mikrotik_swos", "MikroTik SwOS", "P4", _identity("MikroTik", "SwOS"), (SSH_UNSUPPORTED, SNMP_V2C_BLOCKED), implementation="blocked"),
    _profile("cisco_meraki_ms", "Cisco Meraki MS", "P4", _identity("Cisco Meraki", "Meraki MS", ("cloud_managed",)), (API_BLOCKED, SNMP_PLANNED)),
    _profile("aruba_instant_on", "Aruba Instant On", "P4", _identity("HPE Aruba Networking", "Instant On", ("cloud_managed", "local_managed")), (API_BLOCKED, SNMP_PLANNED)),
    _profile("tplink_easy_smart", "TP-Link Easy Smart", "P4", _identity("TP-Link", "Easy Smart"), (SSH_UNSUPPORTED, SNMP_UNSUPPORTED, API_UNSUPPORTED), implementation="unsupported_by_protocol"),
    _profile("unmanaged_switch", "Yönetilemeyen switch", "P4", _identity("Multiple", "Unmanaged switch", ("unknown",)), (SSH_UNSUPPORTED, SNMP_UNSUPPORTED, API_UNSUPPORTED), implementation="unsupported_by_protocol"),
)

ALIASES = (
    ProfileAlias(
        id="huawei_vrp", target_profile_id="huawei_vrp_v200",
        policy="conditional_identity_match", automatic=False,
    ),
    ProfileAlias(
        id="hp_procurve", target_profile_id="aruba_aoss",
        policy="read_compatibility_alias_with_identity_revalidation", automatic=True,
    ),
    ProfileAlias(
        id="hp_comware", target_profile_id="hpe_comware",
        policy="read_compatibility_alias_with_identity_revalidation", automatic=True,
    ),
    ProfileAlias(
        id="dell_force10", target_profile_id="dell_os9",
        policy="conditional_identity_match", automatic=False,
    ),
    ProfileAlias(
        id="extreme_vsp", target_profile_id="extreme_fabric_engine",
        policy="conditional_identity_match", automatic=False,
    ),
    ProfileAlias(
        id="fortinet", target_profile_id=None,
        policy="manual_resolution_required", automatic=False,
    ),
)

LINUX_SSH = InfrastructureAdapter(
    id="linux_ssh",
    revision=2,
    label="Linux iproute2",
    role="generic_read_only_infrastructure_adapter",
    runtime_driver_id="linux_ssh",
    adapter="linux_iproute2",
    verification_status="transport_lab_validated",
    release_status="experimental",
    transports=(SSH_IMPLEMENTED,),
    capabilities=_capabilities(linux_manifest.CAPABILITIES, "transport_lab_validated"),
    tested_versions=("iproute2 JSON isolated SSH lab",),
    not_equivalent_to=("dell_sonic", "nvidia_cumulus_linux", "sonic_nos"),
)
ADAPTERS = (LINUX_SSH,)

LEGACY_CATALOG_BINDINGS = (
    LegacyCatalogBinding(
        id="cisco_ios", label="Cisco IOS", available=True,
        profile_id="cisco_ios",
    ),
    LegacyCatalogBinding(
        id="cisco_iosxe", label="Cisco IOS-XE", available=True,
        profile_id="cisco_iosxe",
    ),
    LegacyCatalogBinding(
        id="huawei_vrp", label="Huawei VRP", available=True,
        profile_id="huawei_vrp_v200",
    ),
    LegacyCatalogBinding(
        id="juniper_junos", label="Juniper Junos (ELS / legacy)", available=True,
        profile_id="juniper_junos",
    ),
    LegacyCatalogBinding(
        id="cisco_nxos", label="Cisco NX-OS", available=True,
        profile_id="cisco_nxos",
    ),
    LegacyCatalogBinding(
        id="linux_ssh", label="Linux iproute2", available=True,
        adapter_id="linux_ssh",
    ),
    LegacyCatalogBinding(
        id="aruba_aoscx", label="Aruba AOS-CX", available=False,
        profile_id="aruba_aoscx",
    ),
    LegacyCatalogBinding(
        id="hp_procurve", label="Aruba AOS-Switch", available=False,
        profile_id="aruba_aoss",
    ),
    LegacyCatalogBinding(
        id="hp_comware", label="HPE Comware", available=False,
        profile_id="hpe_comware",
    ),
    LegacyCatalogBinding(
        id="arista_eos", label="Arista EOS", available=False,
        profile_id="arista_eos",
    ),
    LegacyCatalogBinding(
        id="mikrotik_routeros", label="MikroTik RouterOS", available=False,
        profile_id="mikrotik_routeros",
    ),
    LegacyCatalogBinding(
        id="fortinet", label="FortiOS", available=False,
    ),
    LegacyCatalogBinding(
        id="dell_force10", label="Dell OS9", available=False,
        profile_id="dell_os9",
    ),
    LegacyCatalogBinding(
        id="dell_os10", label="Dell OS10", available=False,
        profile_id="dell_os10",
    ),
    LegacyCatalogBinding(
        id="extreme_exos", label="Extreme Switch Engine", available=False,
        profile_id="extreme_exos",
    ),
    LegacyCatalogBinding(
        id="extreme_vsp", label="Extreme Fabric Engine", available=False,
        profile_id="extreme_fabric_engine",
    ),
)


def validate_registry(
    profiles: Sequence[DriverProfile],
    aliases: Sequence[ProfileAlias],
    adapters: Sequence[InfrastructureAdapter] = (),
    legacy_bindings: Sequence[LegacyCatalogBinding] = (),
) -> None:
    profile_ids = [profile.id for profile in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise ValueError("duplicate_profile_id")
    adapter_ids = [adapter.id for adapter in adapters]
    if len(adapter_ids) != len(set(adapter_ids)) or set(adapter_ids) & set(profile_ids):
        raise ValueError("duplicate_adapter_id")

    runtime_ids = [profile.runtime_driver_id for profile in profiles if profile.runtime_driver_id]
    if len(runtime_ids) != len(set(runtime_ids)):
        raise ValueError("duplicate_runtime_driver_id")

    for profile in profiles:
        if not IDENTIFIER.fullmatch(profile.id) or not (
            profile.identity.vendors
            and profile.identity.os_families
            and profile.identity.management_modes
        ):
            raise ValueError(f"invalid_profile_identity:{profile.id}")
        if profile.runtime_driver_id and not IDENTIFIER.fullmatch(profile.runtime_driver_id):
            raise ValueError(f"invalid_runtime_driver_id:{profile.id}")
        transport_by_kind = {transport.kind: transport for transport in profile.transports}
        if len(transport_by_kind) != len(profile.transports):
            raise ValueError(f"duplicate_transport:{profile.id}")
        capability_groups = [capability.group for capability in profile.capabilities]
        if len(capability_groups) != len(set(capability_groups)):
            raise ValueError(f"duplicate_capability_group:{profile.id}")
        for capability in profile.capabilities:
            if not capability.fields:
                raise ValueError(f"empty_capability:{profile.id}:{capability.group}")
            if len(capability.fields) != len(set(capability.fields)) or not set(
                capability.fields
            ) <= set(DATA_CONTRACT[capability.group]):
                raise ValueError(f"invalid_capability_fields:{profile.id}:{capability.group}")
            if set(capability.source_fields) != set(capability.sources):
                raise ValueError(f"capability_source_fields_mismatch:{profile.id}:{capability.group}")
            declared = {
                field for fields in capability.source_fields.values() for field in fields
            }
            if declared != set(capability.fields):
                raise ValueError(f"capability_field_union_mismatch:{profile.id}:{capability.group}")
            for source, fields in capability.source_fields.items():
                if source not in transport_by_kind or transport_by_kind[source].state != "implemented":
                    raise ValueError(f"capability_transport_not_implemented:{profile.id}:{source}")
                if len(fields) != len(set(fields)) or not set(fields) <= set(
                    DATA_CONTRACT[capability.group]
                ):
                    raise ValueError(f"invalid_capability_source_fields:{profile.id}:{source}")
        if profile.implementation_status == "implemented" and (
            not profile.runtime_driver_id or not profile.adapter or not profile.commands
        ):
            raise ValueError(f"implemented_profile_requires_adapter_and_command_plan:{profile.id}")
        command_names = [command.text for command in profile.commands]
        if len(command_names) != len(set(command_names)):
            raise ValueError(f"duplicate_profile_command:{profile.id}")
        if any(command.group not in GROUPS for command in profile.commands):
            raise ValueError(f"invalid_profile_command_group:{profile.id}")
        if profile.implementation_status == "implemented" and not any(
            command.group == "inventory" and command.required
            for command in profile.commands
        ):
            raise ValueError(f"implemented_profile_requires_identity_command:{profile.id}")
        if profile.release_status == "supported" and not (
            profile.implementation_status == "implemented"
            and profile.verification_status == "physical_validated"
            and profile.acceptance.highest_level == "physical_validated"
            and profile.acceptance.matching_unexpired_records > 0
        ):
            raise ValueError(f"supported_profile_requires_physical_acceptance:{profile.id}")
        if profile.acceptance.production_accepted and profile.release_status != "supported":
            raise ValueError(f"production_acceptance_requires_supported_release:{profile.id}")

    alias_ids = [alias.id for alias in aliases]
    if len(alias_ids) != len(set(alias_ids)):
        raise ValueError("duplicate_alias_id")
    alias_by_id = {alias.id: alias for alias in aliases}
    for start in alias_by_id:
        seen: set[str] = set()
        current: str | None = start
        while current in alias_by_id:
            if current in seen:
                raise ValueError(f"alias_cycle:{current}")
            seen.add(current)
            current = alias_by_id[current].target_profile_id
    if set(alias_ids) & set(profile_ids):
        raise ValueError("alias_collides_with_canonical_profile")
    for alias in aliases:
        if not IDENTIFIER.fullmatch(alias.id) or (
            alias.target_profile_id is not None
            and not IDENTIFIER.fullmatch(alias.target_profile_id)
        ):
            raise ValueError(f"invalid_alias_id:{alias.id}")
        if alias.policy == "manual_resolution_required":
            if alias.target_profile_id is not None or alias.automatic:
                raise ValueError(f"unsafe_manual_alias:{alias.id}")
            continue
        if alias.target_profile_id not in profile_ids:
            raise ValueError(f"unknown_alias_target:{alias.id}")
        if alias.automatic != (
            alias.policy == "read_compatibility_alias_with_identity_revalidation"
        ):
            raise ValueError(f"invalid_alias_automation:{alias.id}")

    binding_ids = [binding.id for binding in legacy_bindings]
    if len(binding_ids) != len(set(binding_ids)):
        raise ValueError("duplicate_legacy_catalog_binding")
    profiles_by_id = {profile.id: profile for profile in profiles}
    adapters_by_id = {adapter.id: adapter for adapter in adapters}
    for binding in legacy_bindings:
        if bool(binding.profile_id) == bool(binding.adapter_id):
            alias = alias_by_id.get(binding.id)
            if not (
                binding.profile_id is None
                and binding.adapter_id is None
                and alias is not None
                and alias.policy == "manual_resolution_required"
            ):
                raise ValueError(f"invalid_legacy_catalog_binding:{binding.id}")
            continue
        target = (
            profiles_by_id.get(binding.profile_id)
            if binding.profile_id
            else adapters_by_id.get(binding.adapter_id)
        )
        if target is None:
            raise ValueError(f"unknown_legacy_catalog_target:{binding.id}")
        if binding.profile_id:
            alias = alias_by_id.get(binding.id)
            expected_profile_id = (
                alias.target_profile_id
                if alias is not None
                else binding.id if binding.id in profiles_by_id else None
            )
            if binding.profile_id != expected_profile_id:
                raise ValueError(f"legacy_catalog_profile_mismatch:{binding.id}")
        elif binding.adapter_id != binding.id:
            raise ValueError(f"legacy_catalog_adapter_mismatch:{binding.id}")
        if binding.available and target.implementation_status != "implemented":
            raise ValueError(f"available_legacy_catalog_target_not_implemented:{binding.id}")


class DriverProfileRegistry:
    def __init__(
        self,
        profiles: Sequence[DriverProfile],
        aliases: Sequence[ProfileAlias],
        adapters: Sequence[InfrastructureAdapter],
        legacy_bindings: Sequence[LegacyCatalogBinding] = (),
    ) -> None:
        validate_registry(profiles, aliases, adapters, legacy_bindings)
        self.profiles = tuple(profiles)
        self.aliases = tuple(aliases)
        self.adapters = tuple(adapters)
        self.legacy_bindings = tuple(legacy_bindings)
        self._profiles = {profile.id: profile for profile in profiles}
        self._aliases = {alias.id: alias for alias in aliases}
        self._adapters = {adapter.id: adapter for adapter in adapters}
        self._runtime = {
            profile.runtime_driver_id: profile
            for profile in profiles
            if profile.runtime_driver_id
        }

    def profile(self, identifier: str) -> DriverProfile | None:
        return self._profiles.get(identifier)

    def runtime_profile(self, runtime_driver_id: str) -> DriverProfile | None:
        return self._runtime.get(runtime_driver_id)

    def adapter(self, identifier: str) -> InfrastructureAdapter | None:
        return self._adapters.get(identifier)

    def resolve(self, identifier: str) -> ProfileResolution:
        if identifier in self._profiles:
            return ProfileResolution(
                requested_id=identifier, status="canonical",
                canonical_profile_id=identifier,
            )
        alias = self._aliases.get(identifier)
        if alias is None:
            return ProfileResolution(requested_id=identifier, status="unknown")
        if alias.target_profile_id is None:
            return ProfileResolution(
                requested_id=identifier, status="manual_resolution_required",
                policy=alias.policy,
            )
        return ProfileResolution(
            requested_id=identifier, status="alias",
            canonical_profile_id=alias.target_profile_id, policy=alias.policy,
        )

    def aliases_for(self, profile_id: str) -> tuple[ProfileAlias, ...]:
        return tuple(
            alias for alias in self.aliases
            if alias.target_profile_id == profile_id
        )


REGISTRY = DriverProfileRegistry(
    PROFILES, ALIASES, ADAPTERS, LEGACY_CATALOG_BINDINGS,
)
if len(REGISTRY.profiles) != 38:
    raise RuntimeError("driver_profile_scope_must_contain_38_profiles")


def _reason(status: ImplementationStatus) -> str | None:
    return {
        "catalog_only": "driver_not_implemented",
        "blocked": "decision_gate_required",
        "unsupported_by_protocol": "unsupported_by_protocol",
        "unsupported_by_policy": "unsupported_by_policy",
        "retired": "driver_retired",
    }.get(status)


def profile_catalog_entry(profile: DriverProfile) -> dict:
    aliases = REGISTRY.aliases_for(profile.id)
    capabilities = {
        capability.group: list(capability.fields)
        for capability in profile.capabilities
    }
    result = {
        "schema_version": profile.schema_version,
        "id": profile.id,
        "profile_revision": profile.profile_revision,
        "label": profile.label,
        "wave": profile.wave,
        "aliases": [alias.id for alias in aliases],
        "alias_policies": [alias.model_dump(mode="json") for alias in aliases],
        "implementation_status": profile.implementation_status,
        "verification_status": profile.verification_status,
        "release_status": profile.release_status,
        "available": profile.implementation_status == "implemented",
        "selectable": profile.implementation_status == "implemented",
        "runtime_selection_id": profile.runtime_driver_id,
        "identity": profile.identity.model_dump(mode="json"),
        "transports": {
            transport.kind: transport.model_dump(mode="json", exclude={"kind"})
            for transport in profile.transports
        },
        "capabilities": capabilities,
        "capability_summaries": [
            capability.model_dump(mode="json") for capability in profile.capabilities
        ],
        "acceptance": profile.acceptance.model_dump(mode="json"),
        "tested_versions": list(profile.tested_versions),
        "commands": [asdict(command) for command in profile.commands],
    }
    reason = _reason(profile.implementation_status)
    if reason:
        result["reason"] = reason
    return result


def adapter_catalog_entry(adapter: InfrastructureAdapter) -> dict:
    return {
        "schema_version": adapter.schema_version,
        "id": adapter.id,
        "revision": adapter.revision,
        "label": adapter.label,
        "profile_kind": "infrastructure_adapter",
        "role": adapter.role,
        "runtime_selection_id": adapter.runtime_driver_id,
        "implementation_status": adapter.implementation_status,
        "verification_status": adapter.verification_status,
        "release_status": adapter.release_status,
        "available": True,
        "selectable": True,
        "transports": {
            transport.kind: transport.model_dump(mode="json", exclude={"kind"})
            for transport in adapter.transports
        },
        "capabilities": {
            capability.group: list(capability.fields)
            for capability in adapter.capabilities
        },
        "acceptance": AcceptanceSummary(
            highest_level=adapter.verification_status,
        ).model_dump(mode="json"),
        "tested_versions": list(adapter.tested_versions),
        "not_equivalent_to": list(adapter.not_equivalent_to),
        "commands": [],
    }
