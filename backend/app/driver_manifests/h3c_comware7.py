"""H3C Comware V7 CLI manifest, intentionally distinct from V5 and V9."""

from .hpe_comware import CAPABILITIES

COMMAND_ROWS = (
    ("display version", "inventory", "h3c_comware7.version", True),
    ("display interface", "fast", "comware7.interfaces", True),
    ("display cpu-usage", "health", "comware7.cpu", False),
    ("display memory", "health", "comware7.memory", False),
    ("display environment", "health", "comware7.environment", False),
    ("display vlan all", "network", "comware7.vlan", False),
    ("display mac-address", "network", "comware7.fdb", False),
    ("display arp", "network", "comware7.arp", False),
    ("display lldp neighbor-information", "network", "comware7.lldp", False),
    ("display device manuinfo", "inventory", "comware7.hardware", False),
)
