"""NVIDIA Cumulus Linux NVUE manifest; not the generic Linux adapter."""

from .common import SNMP_FAST, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("nv show system --output json", "inventory", "cumulus.nvue_system", True),
    ("nv show interface --output json", "fast", "cumulus.nvue_interfaces", True),
    ("bridge -j vlan show", "network", "cumulus.vlan", False),
    ("bridge -j fdb show", "network", "cumulus.fdb", False),
    ("ip -j neigh show", "network", "cumulus.arp", False),
    ("nv show interface --view=lldp --output json", "network", "cumulus.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"), "snmp": SNMP_FAST},
    "network": {"ssh": ("addresses", "vrf", "vlan", "lag", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis", "breakout"), "snmp": SNMP_INVENTORY},
}
