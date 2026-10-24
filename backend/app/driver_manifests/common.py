"""Shared standard-MIB capability declarations for implemented P0 profiles."""

SNMP_FAST = (
    "admin_up", "oper_up", "capacity_bps", "rx_bps", "tx_bps",
    "in_octets", "out_octets", "errors", "discards", "tx_errors",
    "tx_discards",
)
SNMP_HEALTH = ("temperature_c",)
SNMP_NETWORK = ("vlan", "fdb", "lldp")
SNMP_INVENTORY = ("system_identity", "modules")

