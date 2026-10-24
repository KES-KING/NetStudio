"""Standalone FortiSwitchOS read-only CLI and standard-MIB contract."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("get system status", "inventory", "fortinet_fortiswitchos.version", True),
    ("diagnose switch physical-ports list", "fast", "fortinet_fortiswitchos.interfaces", True),
    ("get switch vlan", "network", "fortinet_fortiswitchos.vlan", False),
    ("diagnose switch mac-address list", "network", "fortinet_fortiswitchos.fdb", False),
    ("get system arp", "network", "fortinet_fortiswitchos.arp", False),
    ("diagnose lldprx neighbor summary", "network", "fortinet_fortiswitchos.lldp", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {"snmp": SNMP_HEALTH},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
