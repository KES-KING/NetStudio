"""Aruba AOS-CX structured CLI command and capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "aoscx.version", True),
    ("show interface | json", "fast", "aoscx.interfaces", True),
    ("show system resource-utilization | json", "health", "aoscx.health", False),
    ("show environment | json", "health", "aoscx.environment", False),
    ("show vlan | json", "network", "aoscx.vlan", False),
    ("show mac-address-table | json", "network", "aoscx.fdb", False),
    ("show arp | json", "network", "aoscx.arp", False),
    ("show lldp neighbor-info | json", "network", "aoscx.lldp", False),
    ("show inventory | json", "inventory", "aoscx.hardware", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets",
                "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {
        "ssh": ("cpu_percent", "memory_percent", "temperature_c", "fan", "power_supply"),
        "snmp": SNMP_HEALTH,
    },
    "network": {
        "ssh": ("addresses", "vlan", "fdb", "arp", "lldp"),
        "snmp": SNMP_NETWORK,
    },
    "inventory": {
        "ssh": ("model", "serial", "os_version", "chassis", "modules"),
        "snmp": SNMP_INVENTORY,
    },
}
