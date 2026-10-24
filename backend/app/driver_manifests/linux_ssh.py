"""Generic Linux infrastructure adapter manifest; not a NOS profile."""

CAPABILITIES = {
    "fast": {"ssh": ("admin_up", "oper_up", "in_octets", "out_octets", "rx_bps", "tx_bps")},
    "network": {"ssh": ("addresses", "arp", "ndp")},
}

