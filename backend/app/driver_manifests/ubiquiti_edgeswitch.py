"""Ubiquiti EdgeSwitch standalone read-only CLI capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "edgeswitch.version", True),
    ("show interfaces", "fast", "edgeswitch.interfaces", True),
    ("show vlan", "network", "edgeswitch.vlan", False),
    ("show mac-addr-table", "network", "edgeswitch.fdb", False),
    ("show arp", "network", "edgeswitch.arp", False),
    ("show lldp remote-device all", "network", "edgeswitch.lldp", False),
    ("show system", "health", "edgeswitch.health", False),
)

CAPABILITIES = {
    "fast": {"ssh": (
        "admin_up", "oper_up", "capacity_bps", "duplex", "in_octets",
        "out_octets", "errors", "discards", "tx_errors", "tx_discards",
    ), "snmp": SNMP_FAST},
    "health": {"snmp": SNMP_HEALTH},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
