"""MikroTik RouterOS terminal command and capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("/system resource print without-paging", "inventory", "routeros.resource", True),
    ("/interface print stats-detail without-paging", "fast", "routeros.interfaces", True),
    ("/system health print detail without-paging", "health", "routeros.health", False),
    ("/interface bridge vlan print detail without-paging", "network", "routeros.vlan", False),
    ("/interface bridge host print detail without-paging", "network", "routeros.fdb", False),
    ("/ip arp print detail without-paging", "network", "routeros.arp", False),
    ("/ip neighbor print detail without-paging", "network", "routeros.lldp", False),
    ("/system routerboard print without-paging", "inventory", "routeros.hardware", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "in_octets", "out_octets",
                "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {
        "ssh": ("cpu_percent", "memory_percent", "temperature_c", "power_supply"),
        "snmp": SNMP_HEALTH,
    },
    "network": {
        "ssh": ("vlan", "fdb", "arp", "lldp"),
        "snmp": SNMP_NETWORK,
    },
    "inventory": {
        "ssh": ("model", "serial", "os_version", "system_identity", "chassis"),
        "snmp": SNMP_INVENTORY,
    },
}
