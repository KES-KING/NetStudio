export type PortKind = "rj45" | "sfp";
export type PortStatus = "up" | "down" | "fault" | "stale";

export type Observation<T> = {
  value: T | null;
  observed_at: string | null;
  received_at: string;
  stale_after_seconds: number;
  source: "snmp" | "ssh" | "netconf" | "manual" | "fixture";
  quality: string;
};

export type PhysicalPort = {
  id: string;
  label: string;
  connector: PortKind;
  group: "access" | "uplink";
  ordinal: number;
};

export type NetworkInterface = {
  id: string;
  name: string;
  kind: "ethernet" | "svi" | "loopback" | "port_channel" | "subinterface" | "management";
  if_index: number | null;
  admin_up: Observation<boolean>;
  oper_up: Observation<boolean>;
  speed_mbps: Observation<number>;
  access_vlan?: Observation<number> | null;
};

export type PortBinding = {
  id: string;
  physical_port_id: string;
  interface_id: string;
  binding_quality: "explicit" | "inferred" | "conflict";
};

export type Device = {
  id: string;
  name: string;
  management_address: string;
  site: string;
  vendor: string;
  platform: string;
  model: string;
  os_version: string;
  serial: string;
  read_only: boolean;
  support_status: string;
  physical_ports: PhysicalPort[];
  interfaces: NetworkInterface[];
  bindings: PortBinding[];
};

export function portStatus(port: PhysicalPort, device: Device): PortStatus {
  const binding = device.bindings.find((item) => item.physical_port_id === port.id);
  const iface = device.interfaces.find((item) => item.id === binding?.interface_id);
  if (!iface || iface.admin_up.quality !== "ok" || iface.oper_up.quality !== "ok") return "stale";
  if (iface.admin_up.value === false) return "down";
  if (iface.oper_up.value === true) return "up";
  return "down";
}

export function boundInterface(port: PhysicalPort, device: Device): NetworkInterface | undefined {
  const binding = device.bindings.find((item) => item.physical_port_id === port.id);
  return device.interfaces.find((item) => item.id === binding?.interface_id);
}

