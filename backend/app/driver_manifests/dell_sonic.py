"""Dell Enterprise SONiC CLI manifest, distinct from community SONiC."""

from .common import SNMP_FAST, SNMP_INVENTORY, SNMP_NETWORK

COMMAND_ROWS = (
    ("show version", "inventory", "dell_sonic.version", True),
    ("show interfaces status", "fast", "dell_sonic.status", True),
    ("show interfaces counters", "fast", "dell_sonic.counters", True),
    ("show vlan brief", "network", "dell_sonic.vlan", False),
    ("show mac", "network", "dell_sonic.fdb", False),
    ("show arp", "network", "dell_sonic.arp", False),
    ("show lldp table", "network", "dell_sonic.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards")},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp")},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis")},
}
