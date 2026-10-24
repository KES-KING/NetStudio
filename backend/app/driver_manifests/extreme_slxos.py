"""Extreme SLX-OS read-only CLI and standard-MIB contract."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "extreme_slxos.version", True),
    ("show interface", "fast", "extreme_slxos.interfaces", True),
    ("show vlan brief", "network", "extreme_slxos.vlan", False),
    ("show mac-address-table", "network", "extreme_slxos.fdb", False),
    ("show arp", "network", "extreme_slxos.arp", False),
    ("show lldp neighbors detail", "network", "extreme_slxos.lldp", False),
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
