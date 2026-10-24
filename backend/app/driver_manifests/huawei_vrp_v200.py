"""Huawei VRP V200 command and capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("display version", "inventory", "vrp_v200.version", True),
    ("display interface", "fast", "vrp_v200.interfaces", True),
    ("display cpu-usage", "health", "vrp_v200.cpu", False),
    ("display memory-usage", "health", "vrp_v200.memory", False),
    ("display ip interface brief", "network", "vrp_v200.ip", False),
    ("display mac-address", "network", "vrp_v200.fdb", False),
    ("display arp all", "network", "vrp_v200.arp", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "rx_bps", "tx_bps",
                "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {"ssh": ("cpu_percent", "memory_percent"), "snmp": SNMP_HEALTH},
    "network": {
        "ssh": ("addresses", "vlan", "fdb", "arp"),
        "snmp": SNMP_NETWORK,
    },
    "inventory": {
        "ssh": ("model", "os_version", "chassis"),
        "snmp": SNMP_INVENTORY,
    },
}

