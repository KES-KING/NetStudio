"""NVIDIA Onyx CLI manifest; it must never fall back to Cumulus NVUE."""

from .common import SNMP_FAST, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "onyx.version", True),
    ("show interfaces ethernet", "fast", "onyx.interfaces", True),
    ("show vlan", "network", "onyx.vlan", False),
    ("show mac-address-table", "network", "onyx.fdb", False),
    ("show ip arp", "network", "onyx.arp", False),
    ("show lldp remote", "network", "onyx.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"), "snmp": SNMP_FAST},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
