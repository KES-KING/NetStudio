"""Distribution-qualified community SONiC manifest with unknown vendor."""

COMMAND_ROWS = (
    ("show version", "inventory", "sonic.version", True),
    ("show interfaces status", "fast", "sonic.status", True),
    ("show interfaces counters", "fast", "sonic.counters", True),
    ("show vlan brief", "network", "sonic.vlan", False),
    ("show mac", "network", "sonic.fdb", False),
    ("show arp", "network", "sonic.arp", False),
    ("show lldp table", "network", "sonic.lldp", False),
)

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "capacity_bps", "duplex", "in_octets", "out_octets", "errors", "discards", "tx_errors", "tx_discards")},
    "network": {"ssh": ("vlan", "fdb", "arp", "lldp")},
    "inventory": {"ssh": ("model", "serial", "os_version", "chassis")},
}
