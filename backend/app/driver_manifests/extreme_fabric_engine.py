"""Extreme Fabric Engine/VOSS read-only CLI and conditional SNMP contract."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show sys-info", "inventory", "extreme_fabric_engine.version", True),
    ("show interfaces", "fast", "extreme_fabric_engine.interfaces", True),
    ("show vlan members", "network", "extreme_fabric_engine.vlan", False),
    ("show mac-address-table", "network", "extreme_fabric_engine.fdb", False),
    ("show ip arp", "network", "extreme_fabric_engine.arp", False),
    ("show lldp neighbor", "network", "extreme_fabric_engine.lldp", False),
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
