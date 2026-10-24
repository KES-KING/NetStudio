"""HPE-branded Comware 7 CLI command and capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("display version", "inventory", "hpe_comware.version", True),
    ("display interface", "fast", "comware7.interfaces", True),
    ("display cpu-usage", "health", "comware7.cpu", False),
    ("display memory", "health", "comware7.memory", False),
    ("display environment", "health", "comware7.environment", False),
    ("display vlan all", "network", "comware7.vlan", False),
    ("display mac-address", "network", "comware7.fdb", False),
    ("display arp", "network", "comware7.arp", False),
    ("display lldp neighbor-information", "network", "comware7.lldp", False),
    ("display device manuinfo", "inventory", "comware7.hardware", False),
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
