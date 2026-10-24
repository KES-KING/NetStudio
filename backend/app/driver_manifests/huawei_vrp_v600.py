"""Huawei campus CloudEngine VRP V600 manifest, separate from VRP V200."""

from .common import SNMP_FAST, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("display version", "inventory", "vrp_v600.version", True),
    ("display interface", "fast", "vrp_v600.interfaces", True),
    ("display vlan", "network", "vrp_v600.vlan", False),
    ("display mac-address", "network", "vrp_v600.fdb", False),
    ("display arp all", "network", "vrp_v600.arp", False),
    ("display lldp neighbor brief", "network", "vrp_v600.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"), "snmp": SNMP_FAST},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
