"""Cisco Business Switch manifest; not IOS and not Meraki Dashboard."""

from .common import SNMP_FAST, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "cisco_business.version", True),
    ("show interfaces status", "fast", "cisco_business.status", True),
    ("show interfaces counters", "fast", "cisco_business.counters", True),
    ("show vlan", "network", "cisco_business.vlan", False),
    ("show mac address-table", "network", "cisco_business.fdb", False),
    ("show arp", "network", "cisco_business.arp", False),
    ("show lldp neighbors", "network", "cisco_business.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"), "snmp": SNMP_FAST},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
