"""ExtremeXOS/Switch Engine read-only CLI and standard-MIB contract."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "extreme_exos.version", True),
    ("show ports statistics no-refresh", "fast", "extreme_exos.interfaces", True),
    ("show vlan", "network", "extreme_exos.vlan", False),
    ("show fdb", "network", "extreme_exos.fdb", False),
    ("show iparp", "network", "extreme_exos.arp", False),
    ("show lldp neighbors", "network", "extreme_exos.lldp", False),
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
