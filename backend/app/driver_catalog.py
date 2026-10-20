"""Versioned read-only command contracts, not a claim of universal model support."""
from dataclasses import asdict, dataclass

VERSION = "2026.10.20.2"
NTC_VERSION = "9.3.0"
GROUPS = ("fast", "health", "network", "inventory")
REFERENCES = {
    "cisco": "https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst2960x/software/15-2_7_e/command_reference/b_1527_2960x_cr/interface_and_hardware_commands.html",
    "huawei": "https://info.support.huawei.com/enterprise/en/doc/EDOC1100333403/cdd85713/basic-interface-configuration-commands",
    "junos": "https://www.juniper.net/documentation/us/en/software/junos/netconf/junos-xml-protocol/topics/task/junos-xml-protocol-rpcs-and-xml-mapping.html",
    "nxos": "https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/103x/command-reference/show/b_n9k_show_commands_103x/m_show_xml.html",
}


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
    parser_version: str = VERSION


def commands(reference, rows):
    return tuple(Command(text, group, parser, REFERENCES[reference], required)
                 for text, group, parser, required in rows)


IOS = commands("cisco", [
    ("show interfaces", "fast", "ios.interfaces", True),
    ("show interfaces status", "fast", "ios.status", True),
    ("show processes cpu", "health", "ios.cpu", False),
    ("show memory statistics", "health", "ios.memory", False),
    ("show power inline", "health", "ntc.cisco_ios_show_power_inline", False),
    ("show environment all", "health", "ios.environment", False),
    ("show ip interface", "network", "ios.ip", False),
    ("show mac address-table", "network", "ios.fdb", False),
    ("show arp", "network", "ios.arp", False),
    ("show interfaces switchport", "network", "ntc.cisco_ios_show_interfaces_switchport", False),
    ("show etherchannel summary", "network", "ntc.cisco_ios_show_etherchannel_summary", False),
    ("show lldp neighbors detail", "network", "ntc.cisco_ios_show_lldp_neighbors_detail", False),
    ("show version", "inventory", "ios.version", True),
    ("show inventory", "inventory", "ntc.cisco_ios_show_inventory", False),
])
VRP = commands("huawei", [
    ("display interface", "fast", "vrp.interfaces", True),
    ("display cpu-usage", "health", "vrp.cpu", False),
    ("display memory-usage", "health", "vrp.memory", False),
    ("display ip interface brief", "network", "vrp.ip", False),
    ("display mac-address", "network", "vrp.fdb", False),
    ("display arp all", "network", "vrp.arp", False),
    ("display version", "inventory", "vrp.version", True),
])
JUNOS = commands("junos", [
    ("show interfaces extensive | display xml", "fast", "junos.interfaces", True),
    ("show chassis routing-engine | display xml", "health", "junos.health", False),
    ("show chassis environment | display xml", "health", "junos.environment", False),
    ("show lldp neighbors | display xml", "network", "junos.lldp", False),
    ("show ethernet-switching table | display xml", "network", "junos.fdb", False),
    ("show arp no-resolve | display xml", "network", "junos.arp", False),
    ("show version | display xml", "inventory", "junos.version", True),
    ("show chassis hardware | display xml", "inventory", "junos.hardware", False),
])
NXOS = commands("nxos", [
    ("show interface | json", "fast", "nxos.interfaces", True),
    ("show system resources | json", "health", "nxos.health", False),
    ("show lldp neighbors detail | json", "network", "nxos.lldp", False),
    ("show mac address-table | json", "network", "nxos.fdb", False),
    ("show version | json", "inventory", "nxos.version", True),
    ("show inventory | json", "inventory", "nxos.hardware", False),
])
DRIVERS = {
    "cisco_ios": ("Cisco IOS", IOS, ["Catalyst 2960-X / IOS 15.2(7)E sanitized fixtures"], "fixture_tested"),
    "cisco_iosxe": ("Cisco IOS-XE", IOS, [], "experimental"),
    "huawei_vrp": ("Huawei VRP", VRP, ["S5700 / VRP V200 sanitized fixtures"], "fixture_tested"),
    "juniper_junos": ("Juniper Junos (ELS / legacy)", JUNOS, [], "experimental"),
    "cisco_nxos": ("Cisco NX-OS", NXOS, [], "experimental"),
    "linux_ssh": ("Linux iproute2", (), ["iproute2 JSON isolated SSH lab"], "lab_validated"),
}
PLANNED = {
    "aruba_aoscx": "Aruba AOS-CX", "hp_procurve": "Aruba AOS-Switch",
    "hp_comware": "HPE Comware", "arista_eos": "Arista EOS", "mikrotik_routeros": "MikroTik RouterOS",
    "fortinet": "FortiOS", "dell_force10": "Dell OS9", "dell_os10": "Dell OS10",
    "extreme_exos": "Extreme Switch Engine", "extreme_vsp": "Extreme Fabric Engine",
}
# Explicit missing-field reasons accompany observations. A command existing in a
# vendor's manual does not mean its output has a validated NetStudio parser.
CAPABILITIES = {
    "fast": ["admin_up", "oper_up", "capacity_bps", "duplex", "rx_bps", "tx_bps",
             "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"],
    "health": ["cpu_percent", "memory_percent", "temperature_c", "fan", "power_supply", "poe_watts"],
    "network": ["addresses", "vrf", "vlan", "lag", "fdb", "arp", "ndp", "lldp", "cdp", "dom"],
    "inventory": ["model", "serial", "os_version", "chassis", "stack", "modules", "breakout"],
}
SUPPORTED = {
    "cisco_ios": {"fast": CAPABILITIES["fast"], "health": CAPABILITIES["health"],
        "network": ["addresses", "vlan", "lag", "fdb", "arp", "lldp"],
        "inventory": ["model", "serial", "os_version", "chassis", "modules"]},
    "huawei_vrp": {"fast": CAPABILITIES["fast"], "health": ["cpu_percent", "memory_percent"],
        "network": ["addresses", "vlan", "fdb", "arp"], "inventory": ["model", "os_version", "chassis"]},
    "juniper_junos": {"fast": [key for key in CAPABILITIES["fast"] if key not in {"rx_bps", "tx_bps", "duplex"}],
        "health": ["cpu_percent", "memory_percent"], "network": ["addresses", "lldp"],
        "inventory": ["model", "serial", "os_version", "chassis", "modules"]},
    "cisco_nxos": {"fast": CAPABILITIES["fast"], "health": ["cpu_percent", "memory_percent"],
        "network": [], "inventory": ["model", "serial", "os_version", "chassis"]},
    "linux_ssh": {"fast": ["admin_up", "oper_up", "in_octets", "out_octets", "rx_bps", "tx_bps"],
        "health": [], "network": ["addresses", "arp", "ndp"], "inventory": []},
}
SUPPORTED["cisco_iosxe"] = SUPPORTED["cisco_ios"]


def catalog():
    return {"version": VERSION, "template_version": NTC_VERSION, "data_contract": CAPABILITIES, "drivers": [
        {"id": key, "label": name, "available": True, "validation_level": level,
         "tested_versions": tested, "capabilities": SUPPORTED[key],
         "commands": [asdict(c) for c in plan]}
        for key, (name, plan, tested, level) in DRIVERS.items()
    ] + [
        {"id": key, "label": name, "available": False, "validation_level": "experimental",
         "tested_versions": [], "capabilities": {}, "commands": [], "reason": "driver_not_implemented"}
        for key, name in PLANNED.items()
    ]}
