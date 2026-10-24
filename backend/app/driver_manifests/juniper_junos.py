"""Classic Junos OS XML command and capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version | display xml", "inventory", "junos.version", True),
    ("show interfaces extensive | display xml", "fast", "junos.interfaces", True),
    ("show chassis routing-engine | display xml", "health", "junos.health", False),
    ("show chassis environment | display xml", "health", "junos.environment", False),
    ("show lldp neighbors | display xml", "network", "junos.lldp", False),
    ("show ethernet-switching table | display xml", "network", "junos.fdb", False),
    ("show arp no-resolve | display xml", "network", "junos.arp", False),
    ("show chassis hardware | display xml", "inventory", "junos.hardware", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "in_octets", "out_octets",
                "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {
        "ssh": ("cpu_percent", "memory_percent", "temperature_c", "fan", "power_supply"),
        "snmp": SNMP_HEALTH,
    },
    "network": {
        "ssh": ("addresses", "fdb", "arp", "lldp"),
        "snmp": SNMP_NETWORK,
    },
    "inventory": {
        "ssh": ("model", "serial", "os_version", "chassis", "modules"),
        "snmp": SNMP_INVENTORY,
    },
}

