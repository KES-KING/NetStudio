"""Arista EOS JSON CLI command and capability manifest; eAPI is not enabled."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version | json", "inventory", "eos.version", True),
    ("show interfaces | json", "fast", "eos.interfaces", True),
    ("show processes top once | json", "health", "eos.health", False),
    ("show environment all | json", "health", "eos.environment", False),
    ("show vlans | json", "network", "eos.vlan", False),
    ("show mac address-table | json", "network", "eos.fdb", False),
    ("show arp | json", "network", "eos.arp", False),
    ("show lldp neighbors detail | json", "network", "eos.lldp", False),
    ("show inventory | json", "inventory", "eos.hardware", False),
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
