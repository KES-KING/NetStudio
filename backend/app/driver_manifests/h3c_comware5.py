"""H3C Comware V5 manifest; legacy SSH algorithms remain device opt-in."""

from .common import SNMP_FAST, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("display version", "inventory", "comware5.version", True),
    ("display interface", "fast", "comware5.interfaces", True),
    ("display vlan all", "network", "comware5.vlan", False),
    ("display mac-address", "network", "comware5.fdb", False),
    ("display arp", "network", "comware5.arp", False),
    ("display lldp neighbor-information", "network", "comware5.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"), "snmp": SNMP_FAST},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
