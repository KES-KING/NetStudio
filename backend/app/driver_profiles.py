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
    arista_eos as eos_manifest,
    aruba_aoscx as aoscx_manifest,
    aruba_aoss as aoss_manifest,
    cisco_business as cisco_business_manifest,
    cisco_ios as ios_manifest,
    cisco_iosxe as iosxe_manifest,
    cisco_nxos as nxos_manifest,
    dell_os10 as dell_os10_manifest,
    dell_os6 as dell_os6_manifest,
    dell_os9 as dell_os9_manifest,
    dell_sonic as dell_sonic_manifest,
    extreme_exos as extreme_exos_manifest,
    extreme_fabric_engine as extreme_fabric_engine_manifest,
    extreme_slxos as extreme_slxos_manifest,
    fortinet_fortiswitchos as fortiswitchos_manifest,
    h3c_comware7 as h3c_comware7_manifest,
    h3c_comware5 as h3c_comware5_manifest,
    h3c_comware9 as h3c_comware9_manifest,
    hpe_comware as hpe_comware_manifest,
    huawei_vrp_v200 as vrp_v200_manifest,
    huawei_vrp_v600 as vrp_v600_manifest,
    juniper_junos as junos_manifest,
    juniper_junos_evolved as junos_evolved_manifest,
    linux_ssh as linux_manifest,
    mikrotik_routeros as routeros_manifest,
    mikrotik_swos as swos_manifest,
    nvidia_cumulus_linux as cumulus_manifest,
    nvidia_onyx as onyx_manifest,
    sonic_nos as sonic_manifest,
    ubiquiti_edgeswitch as edgeswitch_manifest,
)


DRIVER_VERSION = "2026.10.24.5"
CATALOG_REVISION = "2026.10.24.5"
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
    "aoscx": "https://arubanetworking.hpe.com/techdocs/AOS-CX/10.16/HTML/cli_6300-6400/index.html",
    "aoss": "https://arubanetworking.hpe.com/techdocs/AOS-S/16.11/MCG/YC/content/index.htm",
    "eos": "https://www.arista.com/en/um-eos/eos-section-1-3-command-api-overview",
    "comware": "https://www.h3c.com/en/Support/Resource_Center/EN/Switches/Catalog/S5560X/S5560X-EI/Technical_Documents/Reference_Guides/Command_References/H3C_S5560X-EI_CR_R65xx-18865/",
    "routeros": "https://help.mikrotik.com/docs/spaces/ROS/pages/328134/Command+Line+Interface",
    "dell_os10": "https://www.dell.com/support/manuals/en-us/dell-emc-smartfabric-os10/smartfabric-os-user-guide-10-5-2-6/show-lldp-neighbors?guid=guid-cf4a7765-02fd-4278-9bcb-c49088ba61e5&lang=en-us",
    "dell_os9": "https://www.dell.com/support/manuals/en-us/dell-emc-os-9/s6000-on-9.14.2.5-cli-pub/show-version?guid=guid-c13e3d17-f476-4c42-9c42-f69571ad31ad&lang=en-us",
    "dell_os6": "https://dl.dell.com/manuals/common/n-series-v663_cli_en-us.pdf",
    "extreme_exos": "https://documentation.extremenetworks.com/Switch%20Engine%20v33.5.1%20User%20Guide/repositories/master/content/documents/Switch_Operating_Systems/Switch_Engine/User_Guide/show_ports_configuration.shtml",
    "extreme_fabric_engine": "https://documentation.extremenetworks.com/Fabric%20Engine%20v9.3%20User%20Guide/content/documents/Switch_Operating_Systems/VOSS_and_Fabric_Engine/fabric_engine_user_guide/ssh_version_2.shtml",
    "extreme_slxos": "https://documentation.extremenetworks.com/Extreme%20SLX-OS%2020.7.2%20Troubleshooting%20Guide/DatacenterNetworking/SLX-OS/Master-Source/extreme_slx_os_troubleshooting_guide/using_show_commands_slxc.shtml",
    "fortiswitchos": "https://docs.fortinet.com/document/fortiswitch/7.6.2/fortiswitchos-cli-reference/896953/get",
    "edgeswitch": "https://dl.ui.com/guides/edgemax/EdgeSwitch_CLI_Command_Reference_UG.pdf",
    "meraki_api": "https://developer.cisco.com/meraki/api-v1/get-organization-devices/",
    "unifi_api": "https://developer.ui.com/network/v9.4.17",
    "fortilink_api": "https://docs.fortinet.com/document/fortigate/7.6.2/cli-reference/308952696/config-switch-controller-managed-switch",
    "omada_api": "https://www.tp-link.com/us/support/download/omada-software-controller/",
    "comware5": "https://www.h3c.com/en/Support/Resource_Center/EN/Switches/Catalog/S5500/S5500-EI/Technical_Documents/Reference_Guides/Command_References/H3C_S5500-EI_CR-Release_2208/",
    "comware9": "https://www.h3c.com/en/Support/Resource_Center/EN/Home/Public/00-Public/Technical_Documents/Reference_Guides/Command_References/H3C_CR-24948/03/202502/2364078_294551_0.htm",
    "vrp_v600": "https://info.support.huawei.com/info-finder/vue/en/enterprise/openSearch?keyword=CloudEngine%20V600R023",
    "junos_evolved": "https://www.juniper.net/documentation/us/en/software/junos/overview-evo/topics/concept/evo-how-it-differs-from-junos.html",
    "dell_sonic": "https://infohub.delltechnologies.com/en-us/l/enterprise-sonic-distribution-by-dell-technologies-lifecycle-management/management-framework-cli/",
    "cumulus": "https://docs.nvidia.com/networking-ethernet-software/nvue-reference/Show-Commands/Interface/",
    "onyx": "https://docs.nvidia.com/networking/display/onyxv3104006/commands",
    "sonic": "https://github.com/sonic-net/SONiC/blob/master/doc/user-manual/SONiC-User-Manual.md",
    "cisco_business": "https://www.cisco.com/c/en/us/td/docs/switches/lan/csbms/CBS_250_350/CLI/cbs-350-cli-/ethernet-configuration-commands.html",
    "swos": "https://help.mikrotik.com/docs/spaces/SWOS/pages/76939305/CSS610+series+Manual",
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
    operator_guidance: str | None = None


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
AOSCX = commands("aoscx", aoscx_manifest.COMMAND_ROWS)
AOSS = commands("aoss", aoss_manifest.COMMAND_ROWS)
EOS = commands("eos", eos_manifest.COMMAND_ROWS)
HPE_COMWARE = commands("comware", hpe_comware_manifest.COMMAND_ROWS)
H3C_COMWARE7 = commands("comware", h3c_comware7_manifest.COMMAND_ROWS)
ROUTEROS = commands("routeros", routeros_manifest.COMMAND_ROWS)
DELL_OS10 = commands("dell_os10", dell_os10_manifest.COMMAND_ROWS)
DELL_OS9 = commands("dell_os9", dell_os9_manifest.COMMAND_ROWS)
DELL_OS6 = commands("dell_os6", dell_os6_manifest.COMMAND_ROWS)
EXTREME_EXOS = commands("extreme_exos", extreme_exos_manifest.COMMAND_ROWS)
EXTREME_FABRIC_ENGINE = commands(
    "extreme_fabric_engine", extreme_fabric_engine_manifest.COMMAND_ROWS
)
EXTREME_SLXOS = commands("extreme_slxos", extreme_slxos_manifest.COMMAND_ROWS)
FORTISWITCHOS = commands("fortiswitchos", fortiswitchos_manifest.COMMAND_ROWS)
EDGESWITCH = commands("edgeswitch", edgeswitch_manifest.COMMAND_ROWS)
H3C_COMWARE5 = commands("comware5", h3c_comware5_manifest.COMMAND_ROWS)
H3C_COMWARE9 = commands("comware9", h3c_comware9_manifest.COMMAND_ROWS)
VRP_V600 = commands("vrp_v600", vrp_v600_manifest.COMMAND_ROWS)
JUNOS_EVOLVED = commands("junos_evolved", junos_evolved_manifest.COMMAND_ROWS)
DELL_SONIC = commands("dell_sonic", dell_sonic_manifest.COMMAND_ROWS)
CUMULUS = commands("cumulus", cumulus_manifest.COMMAND_ROWS)
ONYX = commands("onyx", onyx_manifest.COMMAND_ROWS)
SONIC = commands("sonic", sonic_manifest.COMMAND_ROWS)
CISCO_BUSINESS = commands("cisco_business", cisco_business_manifest.COMMAND_ROWS)
SWOS = commands("swos", swos_manifest.COMMAND_ROWS)

P0_CAPABILITIES = {
    "cisco_ios": ios_manifest.CAPABILITIES,
    "cisco_iosxe": iosxe_manifest.CAPABILITIES,
    "cisco_nxos": nxos_manifest.CAPABILITIES,
    "huawei_vrp_v200": vrp_v200_manifest.CAPABILITIES,
    "juniper_junos": junos_manifest.CAPABILITIES,
}

P1_CAPABILITIES = {
    "aruba_aoscx": aoscx_manifest.CAPABILITIES,
    "aruba_aoss": aoss_manifest.CAPABILITIES,
    "arista_eos": eos_manifest.CAPABILITIES,
    "hpe_comware": hpe_comware_manifest.CAPABILITIES,
    "h3c_comware7": h3c_comware7_manifest.CAPABILITIES,
    "mikrotik_routeros": routeros_manifest.CAPABILITIES,
}

P2_CLI_CAPABILITIES = {
    "dell_os10": dell_os10_manifest.CAPABILITIES,
    "dell_os9": dell_os9_manifest.CAPABILITIES,
    "dell_os6": dell_os6_manifest.CAPABILITIES,
    "extreme_exos": extreme_exos_manifest.CAPABILITIES,
    "extreme_fabric_engine": extreme_fabric_engine_manifest.CAPABILITIES,
    "extreme_slxos": extreme_slxos_manifest.CAPABILITIES,
    "fortinet_fortiswitchos": fortiswitchos_manifest.CAPABILITIES,
    "ubiquiti_edgeswitch": edgeswitch_manifest.CAPABILITIES,
}

P3_CAPABILITIES = {
    "h3c_comware5": h3c_comware5_manifest.CAPABILITIES,
    "h3c_comware9": h3c_comware9_manifest.CAPABILITIES,
    "huawei_vrp_v600": vrp_v600_manifest.CAPABILITIES,
    "juniper_junos_evolved": junos_evolved_manifest.CAPABILITIES,
    "dell_sonic": dell_sonic_manifest.CAPABILITIES,
    "nvidia_cumulus_linux": cumulus_manifest.CAPABILITIES,
    "nvidia_onyx": onyx_manifest.CAPABILITIES,
    "sonic_nos": sonic_manifest.CAPABILITIES,
    "cisco_business": cisco_business_manifest.CAPABILITIES,
}

P4_CAPABILITIES = {
    "mikrotik_swos": swos_manifest.CAPABILITIES,
}


def _identity(
    vendor: str,
    os_family: str,
    modes: tuple[ManagementMode, ...] = ("standalone",),
    *,
    os_aliases: tuple[str, ...] = (),
    models: tuple[str, ...] = (),
    versions: tuple[str, ...] = (),
) -> IdentitySummary:
    return IdentitySummary(
        vendors=(vendor,), os_families=(os_family, *os_aliases), management_modes=modes,
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
SSH_LEGACY_DEVICE_OPT_IN = _transport(
    "ssh", "implemented", versions=("ssh2",),
    decision_gate="legacy_ssh_device_opt_in_required",
)
SNMP_IMPLEMENTED = _transport("snmp", "implemented", versions=("v3_authpriv",))
SNMP_IMPLEMENTED_MODEL_CONDITIONAL = _transport(
    "snmp", "implemented", versions=("v3_authpriv",),
    decision_gate="exact_model_firmware_snmpv3_evidence_required",
)
SNMP_IMPLEMENTED_FABRIC_CONDITIONAL = _transport(
    "snmp", "implemented", versions=("v3_authpriv",),
    decision_gate="fabric_engine_ssh_secure_mode_block_snmp",
)
SSH_PLANNED = _transport("ssh", "planned", versions=("ssh2",))
SNMP_PLANNED = _transport("snmp", "planned", versions=("v3_authpriv",))
SNMP_DISTRIBUTION_PLANNED = _transport(
    "snmp", "planned", versions=("v3_authpriv",),
    decision_gate="distribution_snmpv3_evidence_required",
)
API_PLANNED = _transport("api", "planned", decision_gate="vendor_api_adapter_not_implemented")
API_IMPLEMENTED = _transport("api", "implemented", versions=("https_json",))
API_VENDOR_BLOCKED = _transport(
    "api", "unsupported_by_policy", decision_gate="vendor_public_api_unavailable"
)
SSH_CONTROLLER_UNSUPPORTED = _transport(
    "ssh", "unsupported_by_policy", decision_gate="controller_api_is_management_plane"
)
SSH_UNSUPPORTED = _transport("ssh", "unsupported_by_protocol")
SNMP_UNSUPPORTED = _transport("snmp", "unsupported_by_protocol")
API_UNSUPPORTED = _transport("api", "unsupported_by_protocol")
SNMP_V2C_DEVICE_OPT_IN = TransportSummary(
    kind="snmp", state="implemented",
    security=(
        "read_only", "bounded_oid_allowlist", "installation_opt_in",
        "superadmin_device_opt_in", "unencrypted_transport",
    ),
    versions=("v2c",),
    decision_gate="installation_and_device_risk_approval_required",
)

MERAKI_API = commands("meraki_api", (
    ("GET /api/v1/organizations/{organizationId}/devices", "inventory", "meraki.devices", True),
    ("GET /api/v1/devices/{serial}/switch/ports/statuses?timespan=300", "fast", "meraki.port_status", True),
    ("GET /api/v1/devices/{serial}/switch/ports", "network", "meraki.ports", False),
))
UNIFI_API = commands("unifi_api", (
    ("GET /proxy/network/integration/v1/sites/{siteId}/devices", "inventory", "unifi.devices", True),
    ("GET /proxy/network/integration/v1/sites/{siteId}/devices/{deviceId}", "inventory", "unifi.device_details", True),
    ("GET /proxy/network/integration/v1/sites/{siteId}/devices/{deviceId}/statistics/latest", "health", "unifi.device_statistics", False),
))
FORTILINK_API = commands("fortilink_api", (
    ("GET /api/v2/monitor/switch-controller/managed-switch", "inventory", "fortilink.devices", True),
    ("GET managed FortiSwitch port state", "fast", "fortilink.port_status", True),
))
OMADA_API = commands("omada_api", (
    ("GET /openapi/v1/{controllerId}/sites/{siteId}/switches", "inventory", "omada.switches", True),
    ("GET managed switch port state", "fast", "omada.port_status", True),
))

API_CAPABILITIES = {
    "fast": {"api": (
        "admin_up", "oper_up", "capacity_bps", "in_octets", "out_octets",
        "errors", "discards", "tx_errors", "tx_discards",
    )},
    "health": {"api": ("cpu_percent", "memory_percent", "temperature_c")},
    "network": {"api": ("vlan",)},
    "inventory": {"api": ("model", "serial", "os_version", "system_identity", "chassis")},
}
MERAKI_API_CAPABILITIES = {
    "fast": {"api": ("admin_up", "oper_up", "capacity_bps", "rx_bps", "tx_bps")},
    "network": {"api": ("vlan",)},
    "inventory": {"api": ("model", "serial", "os_version", "system_identity", "chassis")},
}
UNIFI_API_CAPABILITIES = {
    "fast": {"api": ("oper_up", "capacity_bps")},
    "health": {"api": ("cpu_percent", "memory_percent")},
    "inventory": {"api": ("model", "os_version", "system_identity", "chassis")},
}


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
    operator_guidance: str | None = None,
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
        operator_guidance=operator_guidance,
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
    _profile(
        "aruba_aoscx", "Aruba AOS-CX", "P1",
        _identity("HPE Aruba Networking", "AOS-CX", models=("JL658A", "6300M*"), versions=("FL.10.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED, API_PLANNED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="aruba_aoscx", adapter="ssh_cli_json",
        command_plan=AOSCX, capability_groups=P1_CAPABILITIES["aruba_aoscx"],
        tested_versions=("JL658A 6300M / AOS-CX FL.10.13.1030 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "aruba_aoss", "Aruba AOS-Switch", "P1",
        _identity("HPE Aruba Networking", "AOS-Switch", models=("JL253A", "2930F*"), versions=("WC.16.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="hp_procurve", adapter="ssh_cli",
        command_plan=AOSS, capability_groups=P1_CAPABILITIES["aruba_aoss"],
        tested_versions=("JL253A 2930F-24G / ArubaOS-Switch WC.16.11.0016 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "arista_eos", "Arista EOS", "P1",
        _identity("Arista Networks", "EOS", models=("DCS-7050SX3-*",), versions=("4.31.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED, API_PLANNED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="arista_eos", adapter="ssh_cli_json",
        command_plan=EOS, capability_groups=P1_CAPABILITIES["arista_eos"],
        tested_versions=("DCS-7050SX3-48YC8 / EOS 4.31.2F project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "hpe_comware", "HPE Comware", "P1",
        _identity("HPE Aruba Networking", "Comware", models=("JH390A", "5940*"), versions=("7.1.070*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="hp_comware", adapter="ssh_cli",
        command_plan=HPE_COMWARE, capability_groups=P1_CAPABILITIES["hpe_comware"],
        tested_versions=("JH390A 5940 / Comware 7.1.070 R6715P06 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "h3c_comware7", "H3C Comware V7", "P1",
        _identity("H3C", "Comware V7", models=("S5560X-30C-EI",), versions=("7.1.070*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="h3c_comware7", adapter="ssh_cli",
        command_plan=H3C_COMWARE7, capability_groups=P1_CAPABILITIES["h3c_comware7"],
        tested_versions=("S5560X-30C-EI / Comware 7.1.070 R6526P01 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "mikrotik_routeros", "MikroTik RouterOS", "P1",
        _identity("MikroTik", "RouterOS", models=("CRS326-24G-2S+",), versions=("7.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED, API_PLANNED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="mikrotik_routeros", adapter="ssh_cli_routeros",
        command_plan=ROUTEROS, capability_groups=P1_CAPABILITIES["mikrotik_routeros"],
        tested_versions=("CRS326-24G-2S+ / RouterOS 7.15.3 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "dell_os10", "Dell SmartFabric OS10", "P2",
        _identity("Dell Technologies", "SmartFabric OS10", models=("S5248F-ON",), versions=("10.5.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="dell_os10", adapter="ssh_cli",
        command_plan=DELL_OS10, capability_groups=P2_CLI_CAPABILITIES["dell_os10"],
        tested_versions=("S5248F-ON / SmartFabric OS10 10.5.6.1 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "dell_os9", "Dell Networking OS9", "P2",
        _identity("Dell Technologies", "OS9", os_aliases=("FTOS",), models=("S4048-ON",), versions=("9.14*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="dell_force10", adapter="ssh_cli",
        command_plan=DELL_OS9, capability_groups=P2_CLI_CAPABILITIES["dell_os9"],
        tested_versions=("S4048-ON / Dell Networking OS9 9.14(2.20) project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "dell_os6", "Dell Networking OS6", "P2",
        _identity("Dell Technologies", "OS6", models=("N3248X-ON",), versions=("6.8.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="dell_os6", adapter="ssh_cli",
        command_plan=DELL_OS6, capability_groups=P2_CLI_CAPABILITIES["dell_os6"],
        tested_versions=("N3248X-ON / Dell Networking OS6 6.8.1.0 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "extreme_exos", "Extreme Switch Engine", "P2",
        _identity("Extreme Networks", "ExtremeXOS", os_aliases=("Switch Engine",), models=("X465-48T",), versions=("33.3.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="extreme_exos", adapter="ssh_cli",
        command_plan=EXTREME_EXOS, capability_groups=P2_CLI_CAPABILITIES["extreme_exos"],
        tested_versions=("X465-48T / Switch Engine 33.3.1.4 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "extreme_fabric_engine", "Extreme Fabric Engine", "P2",
        _identity("Extreme Networks", "Fabric Engine", os_aliases=("VOSS",), models=("5520-48T",), versions=("9.3.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED_FABRIC_CONDITIONAL),
        implementation="implemented", verification="fixture_verified",
        release="experimental", runtime_driver_id="extreme_vsp",
        adapter="ssh_cli", command_plan=EXTREME_FABRIC_ENGINE,
        capability_groups=P2_CLI_CAPABILITIES["extreme_fabric_engine"],
        tested_versions=("5520-48T / Fabric Engine 9.3.2.0 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "extreme_slxos", "Extreme SLX-OS", "P2",
        _identity("Extreme Networks", "SLX-OS", models=("SLX 9150-48Y",), versions=("20.6.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="extreme_slxos", adapter="ssh_cli",
        command_plan=EXTREME_SLXOS, capability_groups=P2_CLI_CAPABILITIES["extreme_slxos"],
        tested_versions=("SLX 9150-48Y / SLX-OS 20.6.3b project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "fortinet_fortiswitchos", "Fortinet FortiSwitchOS", "P2",
        _identity("Fortinet", "FortiSwitchOS", models=("FortiSwitch-124F",), versions=("7.6.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED, API_PLANNED),
        implementation="implemented", verification="fixture_verified",
        release="experimental", runtime_driver_id="fortinet_fortiswitchos",
        adapter="ssh_cli", command_plan=FORTISWITCHOS,
        capability_groups=P2_CLI_CAPABILITIES["fortinet_fortiswitchos"],
        tested_versions=("FortiSwitch-124F / FortiSwitchOS 7.6.2 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "fortinet_fortiswitch_fortilink", "Fortinet FortiSwitchOS (FortiLink)", "P2",
        _identity("Fortinet", "FortiSwitchOS", ("controller_managed",)),
        (API_IMPLEMENTED, SNMP_PLANNED, SSH_CONTROLLER_UNSUPPORTED),
        implementation="implemented", verification="fixture_verified", release="experimental",
        runtime_driver_id="fortinet_fortilink_api", adapter="controller_https",
        command_plan=FORTILINK_API, capability_groups=API_CAPABILITIES,
        tested_versions=("FortiGate managed FortiSwitch project-synthetic API fixture",), profile_revision=2,
    ),
    _profile(
        "tplink_omada_managed", "TP-Link Omada Managed", "P2",
        _identity("TP-Link", "Omada Managed", ("controller_managed",)),
        (API_IMPLEMENTED, SNMP_PLANNED, SSH_CONTROLLER_UNSUPPORTED),
        implementation="implemented", verification="fixture_verified", release="experimental",
        runtime_driver_id="tplink_omada_api", adapter="controller_https",
        command_plan=OMADA_API, capability_groups=API_CAPABILITIES,
        tested_versions=("Omada SDN project-synthetic Open API fixture",), profile_revision=2,
    ),
    _profile(
        "tplink_omada_pro", "TP-Link Omada Pro", "P2",
        _identity("TP-Link", "Omada Pro", ("controller_managed",)),
        (API_IMPLEMENTED, SNMP_PLANNED, SSH_CONTROLLER_UNSUPPORTED),
        implementation="implemented", verification="fixture_verified", release="experimental",
        runtime_driver_id="tplink_omada_pro_api", adapter="controller_https",
        command_plan=OMADA_API, capability_groups=API_CAPABILITIES,
        tested_versions=("Omada Pro project-synthetic Open API fixture",), profile_revision=2,
    ),
    _profile(
        "ubiquiti_unifi_switch", "Ubiquiti UniFi Switch", "P2",
        _identity("Ubiquiti", "UniFi Switch", ("controller_managed",)),
        (API_IMPLEMENTED, SNMP_PLANNED, SSH_CONTROLLER_UNSUPPORTED),
        implementation="implemented", verification="fixture_verified", release="experimental",
        runtime_driver_id="unifi_api", adapter="controller_https",
        command_plan=UNIFI_API, capability_groups=UNIFI_API_CAPABILITIES,
        tested_versions=("UniFi Network 9.4 project-synthetic integration API fixture",), profile_revision=2,
    ),
    _profile(
        "ubiquiti_unifi_no_snmp", "Ubiquiti UniFi Flex/Ultra (SNMP yok)", "P2",
        _identity("Ubiquiti", "UniFi Switch", ("controller_managed",), models=("USW-Flex*", "USW-Ultra*")),
        (API_IMPLEMENTED, SNMP_UNSUPPORTED, SSH_CONTROLLER_UNSUPPORTED),
        implementation="implemented", verification="fixture_verified", release="experimental",
        runtime_driver_id="unifi_no_snmp_api", adapter="controller_https",
        command_plan=UNIFI_API, capability_groups=UNIFI_API_CAPABILITIES,
        tested_versions=("UniFi Flex/Ultra project-synthetic API fixture",), profile_revision=2,
    ),
    _profile(
        "ubiquiti_edgeswitch", "Ubiquiti EdgeSwitch", "P2",
        _identity("Ubiquiti", "EdgeSwitch OS", models=("ES-*",), versions=("1.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="ubiquiti_edgeswitch", adapter="ssh_cli",
        command_plan=EDGESWITCH,
        capability_groups=P2_CLI_CAPABILITIES["ubiquiti_edgeswitch"],
        tested_versions=("ES-48-500W / EdgeSwitch 1.10.4 project-synthetic fixture",),
        profile_revision=2,
    ),
    _profile(
        "h3c_comware5", "H3C Comware V5", "P3",
        _identity("H3C", "Comware V5", versions=("5.*",)),
        (SSH_LEGACY_DEVICE_OPT_IN, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="h3c_comware5", adapter="ssh_cli_legacy_opt_in",
        command_plan=H3C_COMWARE5, capability_groups=P3_CAPABILITIES["h3c_comware5"],
        tested_versions=("S5500-28C-EI / Comware 5.20 R2222P02 project-synthetic fixture",), profile_revision=2,
    ),
    _profile(
        "h3c_comware9", "H3C Comware V9", "P3",
        _identity("H3C", "Comware V9", versions=("9.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="h3c_comware9", adapter="ssh_cli",
        command_plan=H3C_COMWARE9, capability_groups=P3_CAPABILITIES["h3c_comware9"],
        tested_versions=("S6520X-30HC-HI / Comware 9.1 R9126P01 project-synthetic fixture",), profile_revision=2,
    ),
    _profile(
        "huawei_vrp_v600", "Huawei VRP V600", "P3",
        _identity("Huawei", "VRP V600", models=("S57*-V2",), versions=("V600R*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="huawei_vrp_v600", adapter="ssh_cli",
        command_plan=VRP_V600, capability_groups=P3_CAPABILITIES["huawei_vrp_v600"],
        tested_versions=("S5735-L24P4XE-A-V2 / V600R023C10 project-synthetic fixture",), profile_revision=2,
    ),
    _profile(
        "juniper_junos_evolved", "Juniper Junos OS Evolved", "P3",
        _identity("Juniper", "Junos OS Evolved", versions=("23.*-EVO",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="juniper_junos_evolved", adapter="ssh_xml_evolved",
        command_plan=JUNOS_EVOLVED, capability_groups=P3_CAPABILITIES["juniper_junos_evolved"],
        tested_versions=("QFX5130-48C / 23.4R2-EVO project-synthetic XML fixture",), profile_revision=2,
    ),
    _profile(
        "dell_sonic", "Dell Enterprise SONiC", "P3",
        _identity("Dell Technologies", "Enterprise SONiC", versions=("4.*",)),
        (SSH_IMPLEMENTED, SNMP_DISTRIBUTION_PLANNED, API_PLANNED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="dell_sonic", adapter="ssh_cli_sonic_dell",
        command_plan=DELL_SONIC, capability_groups=P3_CAPABILITIES["dell_sonic"],
        tested_versions=("S5248F-ON / Dell Enterprise SONiC 4.4.0 project-synthetic fixture",), profile_revision=2,
    ),
    _profile(
        "nvidia_cumulus_linux", "NVIDIA Cumulus Linux", "P3",
        _identity("NVIDIA Networking", "Cumulus Linux", versions=("5.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED, API_PLANNED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="nvidia_cumulus_linux", adapter="ssh_nvue_json",
        command_plan=CUMULUS, capability_groups=P3_CAPABILITIES["nvidia_cumulus_linux"],
        tested_versions=("SN3700C / Cumulus Linux 5.14.0 project-synthetic NVUE fixture",), profile_revision=2,
    ),
    _profile(
        "nvidia_onyx", "NVIDIA Onyx", "P3",
        _identity("NVIDIA Networking", "Onyx", versions=("3.10.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="nvidia_onyx", adapter="ssh_cli",
        command_plan=ONYX, capability_groups=P3_CAPABILITIES["nvidia_onyx"],
        tested_versions=("SN2700 / Onyx 3.10.4404 project-synthetic fixture",), profile_revision=2,
    ),
    _profile(
        "sonic_nos", "SONiC NOS", "P3",
        _identity("Unknown", "SONiC", versions=("distribution+image required",)),
        (SSH_IMPLEMENTED, SNMP_DISTRIBUTION_PLANNED, API_PLANNED), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="sonic_nos", adapter="ssh_cli_sonic_distribution_qualified",
        command_plan=SONIC, capability_groups=P3_CAPABILITIES["sonic_nos"],
        tested_versions=("community SONiC 202405 / image tuple project-synthetic fixture",), profile_revision=2,
    ),
    _profile(
        "cisco_business", "Cisco Business Switch", "P3",
        _identity("Cisco", "Cisco Business firmware", models=("CBS*",), versions=("3.*",)),
        (SSH_IMPLEMENTED, SNMP_IMPLEMENTED_MODEL_CONDITIONAL), implementation="implemented",
        verification="fixture_verified", release="experimental",
        runtime_driver_id="cisco_business", adapter="ssh_cli_cisco_business",
        command_plan=CISCO_BUSINESS, capability_groups=P3_CAPABILITIES["cisco_business"],
        tested_versions=("CBS350-24T-4G / 3.4.0.17 project-synthetic fixture",), profile_revision=2,
    ),
    _profile(
        "mikrotik_swos", "MikroTik SwOS", "P4",
        _identity("MikroTik", "SwOS", models=("CSS610-8G-2S+",), versions=("2.19",)),
        (SSH_UNSUPPORTED, SNMP_V2C_DEVICE_OPT_IN),
        implementation="implemented", verification="transport_lab_validated",
        release="experimental", runtime_driver_id="mikrotik_swos",
        adapter="snmp_v2c_standard_mib", command_plan=SWOS,
        capability_groups=P4_CAPABILITIES["mikrotik_swos"],
        tested_versions=("CSS610-8G-2S+ / SwOS 2.19 project-synthetic fixture and loopback v2c transport",),
        profile_revision=2,
        operator_guidance="SNMPv2c şifreleme sağlamaz; kurulum bayrağı, superadmin cihaz onayı, kaynak ACL'si ve yönetim VLAN/VRF izolasyonu zorunludur.",
    ),
    _profile(
        "cisco_meraki_ms", "Cisco Meraki MS", "P4",
        _identity("Cisco Meraki", "Meraki MS", ("cloud_managed",), models=("MS*",)),
        (API_IMPLEMENTED, SNMP_PLANNED, SSH_UNSUPPORTED),
        implementation="implemented", verification="fixture_verified", release="experimental",
        runtime_driver_id="meraki_dashboard", adapter="controller_https",
        command_plan=MERAKI_API, capability_groups=MERAKI_API_CAPABILITIES,
        tested_versions=("Meraki Dashboard API v1 project-synthetic fixture",), profile_revision=2,
    ),
    _profile(
        "aruba_instant_on", "Aruba Instant On", "P4",
        _identity("HPE Aruba Networking", "Instant On", ("cloud_managed", "local_managed")),
        (API_VENDOR_BLOCKED, SNMP_PLANNED, SSH_UNSUPPORTED),
        implementation="blocked", verification="not_tested", release="hidden", profile_revision=2,
    ),
    _profile(
        "tplink_easy_smart", "TP-Link Easy Smart", "P4",
        _identity("TP-Link", "Easy Smart"),
        (SSH_UNSUPPORTED, SNMP_UNSUPPORTED, API_UNSUPPORTED),
        implementation="unsupported_by_protocol",
        operator_guidance="Exact model ve firmware istisnası kanıtlanmadıkça yerel SSH, SNMP veya API kimlik bilgisi istenmez.",
    ),
    _profile(
        "unmanaged_switch", "Yönetilemeyen switch", "P4",
        _identity("Multiple", "Unmanaged switch", ("unknown",)),
        (SSH_UNSUPPORTED, SNMP_UNSUPPORTED, API_UNSUPPORTED),
        implementation="unsupported_by_protocol",
        operator_guidance="Komşu cihazlardan gelen LLDP/FDB gözlemi dolaylı görünürlüktür; cihaz yönetimi veya doğrudan toplama değildir.",
    ),
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
        id="aruba_aoscx", label="Aruba AOS-CX", available=True,
        profile_id="aruba_aoscx",
    ),
    LegacyCatalogBinding(
        id="hp_procurve", label="Aruba AOS-Switch", available=True,
        profile_id="aruba_aoss",
    ),
    LegacyCatalogBinding(
        id="hp_comware", label="HPE Comware", available=True,
        profile_id="hpe_comware",
    ),
    LegacyCatalogBinding(
        id="arista_eos", label="Arista EOS", available=True,
        profile_id="arista_eos",
    ),
    LegacyCatalogBinding(
        id="mikrotik_routeros", label="MikroTik RouterOS", available=True,
        profile_id="mikrotik_routeros",
    ),
    LegacyCatalogBinding(
        id="fortinet", label="FortiOS", available=False,
    ),
    LegacyCatalogBinding(
        id="dell_force10", label="Dell OS9", available=True,
        profile_id="dell_os9",
    ),
    LegacyCatalogBinding(
        id="dell_os10", label="Dell OS10", available=True,
        profile_id="dell_os10",
    ),
    LegacyCatalogBinding(
        id="extreme_exos", label="Extreme Switch Engine", available=True,
        profile_id="extreme_exos",
    ),
    LegacyCatalogBinding(
        id="extreme_vsp", label="Extreme Fabric Engine", available=True,
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
        command_transport = any(
            transport.state == "implemented" and transport.kind in {"ssh", "api"}
            for transport in profile.transports
        )
        if profile.implementation_status == "implemented" and (
            not profile.runtime_driver_id or not profile.adapter
            or (command_transport and not profile.commands)
        ):
            raise ValueError(f"implemented_profile_requires_adapter_and_command_plan:{profile.id}")
        command_names = [command.text for command in profile.commands]
        if len(command_names) != len(set(command_names)):
            raise ValueError(f"duplicate_profile_command:{profile.id}")
        if any(command.group not in GROUPS for command in profile.commands):
            raise ValueError(f"invalid_profile_command_group:{profile.id}")
        if command_transport and not any(
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
        "operator_guidance": profile.operator_guidance,
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
