import type { Device, NetworkInterface, Observation, PhysicalPort, PortBinding } from "./domain";

// Stable fixture time keeps server rendering and client hydration deterministic.
const now = "2026-10-10T14:32:08Z";
const observation = <T,>(value: T, source: Observation<T>["source"] = "fixture"): Observation<T> => ({
  value,
  observed_at: now,
  received_at: now,
  stale_after_seconds: 90,
  source,
  quality: "ok",
});

function createFixture(): Device {
  const physicalPorts: PhysicalPort[] = Array.from({ length: 24 }, (_, index) => ({
    id: `dev-demo-01-physical-${String(index + 1).padStart(2, "0")}`,
    label: `Gi0/${index + 1}`,
    connector: "rj45",
    group: "access",
    ordinal: index + 1,
  }));
  const uplinks: PhysicalPort[] = Array.from({ length: 4 }, (_, index) => ({
    id: `dev-demo-01-physical-u${index + 1}`,
    label: `Te0/${index + 1}`,
    connector: "sfp",
    group: "uplink",
    ordinal: 25 + index,
  }));
  const allPorts = [...physicalPorts, ...uplinks];
  const interfaces: NetworkInterface[] = allPorts.map((port, index) => ({
    id: `dev-demo-01-if-${port.group === "access" ? String(index + 1).padStart(2, "0") : `u${index - 23}`}`,
    name: port.connector === "rj45" ? `GigabitEthernet0/${index + 1}` : `TenGigabitEthernet0/${index - 23}`,
    kind: "ethernet",
    if_index: index + 1,
    admin_up: observation(true),
    oper_up: observation(index !== 6 && index !== 18 && (port.group === "access" || index < 26)),
    speed_mbps: observation(port.group === "access" ? 1000 : 10000),
    access_vlan: port.group === "access" ? observation(index % 3 === 0 ? 30 : 20) : null,
  }));
  const bindings: PortBinding[] = allPorts.map((port, index) => ({
    id: `binding-${port.id}`,
    physical_port_id: port.id,
    interface_id: interfaces[index].id,
    binding_quality: "explicit",
  }));
  interfaces.push(
    { id: "dev-demo-01-svi-10", name: "Vlan10", kind: "svi", if_index: 1010, admin_up: observation(true), oper_up: observation(true), speed_mbps: observation(0) },
    { id: "dev-demo-01-loopback-0", name: "Loopback0", kind: "loopback", if_index: 2000, admin_up: observation(true), oper_up: observation(true), speed_mbps: observation(0) },
    { id: "dev-demo-01-port-channel-1", name: "Port-channel1", kind: "port_channel", if_index: 3001, admin_up: observation(true), oper_up: observation(true), speed_mbps: observation(20000) },
  );
  return {
    id: "dev-demo-01",
    name: "SW-DEMO-01",
    management_address: "192.0.2.10",
    site: "LAB / Demo",
    vendor: "Example Networks",
    platform: "generic-lab",
    model: "generic-lab-24rj45-4sfp",
    os_version: "fixture-0",
    serial: "DEMO-READONLY",
    read_only: true,
    support_status: "demo_fixture",
    physical_ports: allPorts,
    interfaces,
    bindings,
  };
}

export const demoDevice = createFixture();
