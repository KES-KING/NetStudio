"""ArubaOS-Switch/ProVision text CLI command and capability manifest."""

from .common import SNMP_FAST, SNMP_HEALTH, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "aoss.version", True),
    ("show interfaces", "fast", "aoss.interfaces", True),
    ("show vlans", "network", "aoss.vlan", False),
    ("show mac-address", "network", "aoss.fdb", False),
    ("show arp", "network", "aoss.arp", False),
    ("show lldp info remote-device", "network", "aoss.lldp", False),
    ("show system information", "inventory", "aoss.system", False),
    ("show modules", "inventory", "aoss.hardware", False),
)

CAPABILITIES = {
    "fast": {
        "ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets",
                "errors", "discards", "tx_errors", "tx_discards"),
        "snmp": SNMP_FAST,
    },
    "health": {"snmp": SNMP_HEALTH},
    "network": {
        "ssh": ("vlan", "fdb", "arp", "lldp"),
        "snmp": SNMP_NETWORK,
    },
    "inventory": {
        "ssh": ("model", "serial", "os_version", "chassis", "modules"),
        "snmp": SNMP_INVENTORY,
    },
}
