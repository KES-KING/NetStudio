"""MikroTik SwOS standard-MIB manifest; no SSH, v1, SET or trap path."""

from .common import SNMP_FAST, SNMP_INVENTORY

COMMAND_ROWS = ()

CAPABILITIES = {
    "fast": {"snmp": SNMP_FAST},
    "network": {"snmp": ("vlan", "fdb")},
    "inventory": {"snmp": SNMP_INVENTORY},
}
