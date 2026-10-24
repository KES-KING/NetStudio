"""Cisco NX-OS JSON command and capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version | json", "inventory", "nxos.version", True),
    ("show interface | json", "fast", "nxos.interfaces", True),
    ("show system resources | json", "health", "nxos.health", False),
    ("show lldp neighbors detail | json", "network", "nxos.lldp", False),
    ("show mac address-table | json", "network", "nxos.fdb", False),
    ("show inventory | json", "inventory", "nxos.hardware", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "rx_bps", "tx_bps",
                "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {"ssh": ("cpu_percent", "memory_percent"), "snmp": SNMP_HEALTH},
    "network": {"ssh": ("fdb", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {
        "ssh": ("model", "serial", "os_version", "chassis", "modules"),
        "snmp": SNMP_INVENTORY,
    },
}

