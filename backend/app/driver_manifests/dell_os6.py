"""Dell Networking OS6/N-series read-only CLI and standard-MIB contract."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "dell_os6.version", True),
    ("show interfaces", "fast", "dell_os6.interfaces", True),
    ("show vlan", "network", "dell_os6.vlan", False),
    ("show mac address-table", "network", "dell_os6.fdb", False),
    ("show arp", "network", "dell_os6.arp", False),
    ("show lldp remote-device all", "network", "dell_os6.lldp", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {"snmp": SNMP_HEALTH},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp"), "snmp": SNMP_NETWORK},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis"), "snmp": SNMP_INVENTORY},
}
