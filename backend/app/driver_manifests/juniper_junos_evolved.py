"""Junos OS Evolved operational manifest; no classic-Junos runtime alias."""

from .common import SNMP_FAST, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version | display xml | no-more", "inventory", "junos_evolved.version_xml", True),
    ("show interfaces extensive | display xml | no-more", "fast", "junos_evolved.interfaces_xml", True),
    ("show vlans terse | no-more", "network", "junos_evolved.vlan", False),
    ("show ethernet-switching table brief | no-more", "network", "junos_evolved.fdb", False),
    ("show arp no-resolve | no-more", "network", "junos_evolved.arp", False),
    ("show lldp neighbors | no-more", "network", "junos_evolved.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"), "snmp": SNMP_FAST},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
