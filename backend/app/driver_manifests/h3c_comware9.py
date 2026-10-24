"""H3C Comware V9 manifest; deliberately independent from V7."""

from .common import SNMP_FAST, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("display version", "inventory", "comware9.version", True),
    ("display interface", "fast", "comware9.interfaces", True),
    ("display vlan", "network", "comware9.vlan", False),
    ("display mac-address", "network", "comware9.fdb", False),
    ("display arp", "network", "comware9.arp", False),
    ("display lldp neighbor-information verbose", "network", "comware9.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"), "snmp": SNMP_FAST},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
