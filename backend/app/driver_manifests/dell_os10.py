"""Dell SmartFabric OS10 read-only CLI and standard-MIB contract."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "dell_os10.version", True),
    ("show interface", "fast", "dell_os10.interfaces", True),
    ("show vlan", "network", "dell_os10.vlan", False),
    ("show mac address-table", "network", "dell_os10.fdb", False),
    ("show ip arp", "network", "dell_os10.arp", False),
    ("show lldp neighbors", "network", "dell_os10.lldp", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {"snmp": SNMP_HEALTH},
    "network": {
        "ssh": ("vlan", "fdb", "arp", "lldp"),
        "snmp": SNMP_NETWORK,
    },
    "inventory": {
        "ssh": ("model", "serial", "os_version", "chassis"),
        "snmp": SNMP_INVENTORY,
    },
}
