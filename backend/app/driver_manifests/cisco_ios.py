"""Cisco IOS command and capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "ios.version", True),
    ("show interfaces", "fast", "ios.interfaces", True),
    ("show interfaces status", "fast", "ios.status", True),
    ("show processes cpu", "health", "ios.cpu", False),
    ("show memory statistics", "health", "ios.memory", False),
    ("show power inline", "health", "ntc.cisco_ios_show_power_inline", False),
    ("show environment all", "health", "ios.environment", False),
    ("show ip interface", "network", "ios.ip", False),
    ("show mac address-table", "network", "ios.fdb", False),
    ("show arp", "network", "ios.arp", False),
    ("show interfaces switchport", "network", "ntc.cisco_ios_show_interfaces_switchport", False),
    ("show etherchannel summary", "network", "ntc.cisco_ios_show_etherchannel_summary", False),
    ("show lldp neighbors detail", "network", "ntc.cisco_ios_show_lldp_neighbors_detail", False),
    ("show inventory", "inventory", "ntc.cisco_ios_show_inventory", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "rx_bps", "tx_bps",
                "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {
        "ssh": ("cpu_percent", "memory_percent", "temperature_c", "fan", "power_supply", "poe_watts"),
        "snmp": SNMP_HEALTH,
    },
    "network": {
        "ssh": ("addresses", "vlan", "lag", "fdb", "arp", "lldp"),
        "snmp": SNMP_NETWORK,
    },
    "inventory": {
        "ssh": ("model", "serial", "os_version", "chassis", "modules"),
        "snmp": SNMP_INVENTORY,
    },
}

