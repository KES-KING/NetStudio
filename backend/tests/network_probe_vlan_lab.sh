#!/usr/bin/env bash
# Privileged, opt-in VLAN isolation proof for the AF_PACKET ARP probe.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bu laboratuvar testi root yetkisi gerektirir." >&2
  exit 77
fi
for command in ip bridge; do
  command -v "$command" >/dev/null || { echo "$command bulunamadı." >&2; exit 77; }
done

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
PYTHON_BIN=${NETSTUDIO_LAB_PYTHON:-"$REPO_ROOT/.venv/bin/python"}
[[ -x "$PYTHON_BIN" ]] || { echo "Python bulunamadı: $PYTHON_BIN" >&2; exit 77; }

SUFFIX=$(printf '%05d' "$$")
PROBE_NS="netstudio-probe-$SUFFIX"
HOST10_NS="netstudio-v10-$SUFFIX"
HOST20_NS="netstudio-v20-$SUFFIX"
BRIDGE="npb$SUFFIX"
TRUNK="npt$SUFFIX"
ACCESS10="np10$SUFFIX"
ACCESS20="np20$SUFFIX"

cleanup() {
  ip netns del "$PROBE_NS" 2>/dev/null || true
  ip netns del "$HOST10_NS" 2>/dev/null || true
  ip netns del "$HOST20_NS" 2>/dev/null || true
  ip link del "$BRIDGE" 2>/dev/null || true
}
trap cleanup EXIT

ip netns add "$PROBE_NS"
ip netns add "$HOST10_NS"
ip netns add "$HOST20_NS"
ip link add "$BRIDGE" type bridge vlan_filtering 1
ip link set "$BRIDGE" up

ip link add "$TRUNK" type veth peer name eth0 netns "$PROBE_NS"
ip link add "$ACCESS10" type veth peer name eth0 netns "$HOST10_NS"
ip link add "$ACCESS20" type veth peer name eth0 netns "$HOST20_NS"
for interface in "$TRUNK" "$ACCESS10" "$ACCESS20"; do
  ip link set "$interface" master "$BRIDGE"
  ip link set "$interface" up
  bridge vlan del dev "$interface" vid 1
done
bridge vlan add dev "$TRUNK" vid 10
bridge vlan add dev "$TRUNK" vid 20
bridge vlan add dev "$ACCESS10" vid 10 pvid untagged
bridge vlan add dev "$ACCESS20" vid 20 pvid untagged

ip -n "$PROBE_NS" link set lo up
ip -n "$PROBE_NS" link set eth0 up
ip -n "$PROBE_NS" link add link eth0 name eth0.10 type vlan id 10
ip -n "$PROBE_NS" link add link eth0 name eth0.20 type vlan id 20
ip -n "$PROBE_NS" address add 192.0.2.254/24 dev eth0.10
ip -n "$PROBE_NS" address add 192.0.2.253/24 dev eth0.20
ip -n "$PROBE_NS" link set eth0.10 up
ip -n "$PROBE_NS" link set eth0.20 up

for namespace in "$HOST10_NS" "$HOST20_NS"; do
  ip -n "$namespace" link set lo up
  ip -n "$namespace" link set eth0 up
  ip -n "$namespace" address add 192.0.2.10/24 dev eth0
done
HOST10_MAC=$(ip -n "$HOST10_NS" -o link show eth0 | awk '{print $17}')
HOST20_MAC=$(ip -n "$HOST20_NS" -o link show eth0 | awk '{print $17}')

ip netns exec "$PROBE_NS" env PYTHONPATH="$REPO_ROOT/backend" "$PYTHON_BIN" - "$HOST10_MAC" "$HOST20_MAC" <<'PY'
import sys
from app.network_probe_agent import interface_state, scan

mac10, mac20 = sys.argv[1:]
states = [interface_state("eth0.10"), interface_state("eth0.20")]

def task(interface, source_ip, source_cidr, allowed):
    return {
        "interface_name": interface,
        "source_ip": source_ip,
        "source_cidr": source_cidr,
        "target_cidrs": ["192.0.2.10/32"],
        "excluded_addresses": [source_ip],
        "allowed_macs": allowed,
        "max_rate_pps": 64,
        "reply_wait_seconds": 2,
    }

vlan10 = scan(task("eth0.10", "192.0.2.254", "192.0.2.254/24", [mac10, mac20]), states)
vlan20 = scan(task("eth0.20", "192.0.2.253", "192.0.2.253/24", [mac10, mac20]), states)
assert vlan10["matches"] == [{"mac": mac10, "address": "192.0.2.10"}], vlan10
assert vlan20["matches"] == [{"mac": mac20, "address": "192.0.2.10"}], vlan20
print("PASS: VLAN 10 ve VLAN 20 gerçek ARP yanıtları ayrı kaldı.")
PY
