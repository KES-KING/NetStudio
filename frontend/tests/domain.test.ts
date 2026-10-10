import { describe, expect, it } from "vitest";
import { demoDevice } from "../lib/fixture";
import { boundInterface, portStatus } from "../lib/domain";

describe("physical port binding", () => {
  it("exposes 24 access and 4 uplink physical ports", () => {
    expect(demoDevice.physical_ports).toHaveLength(28);
    expect(demoDevice.physical_ports.filter((port) => port.group === "access")).toHaveLength(24);
    expect(demoDevice.physical_ports.filter((port) => port.group === "uplink")).toHaveLength(4);
  });

  it("does not render logical interfaces as sockets", () => {
    const boundNames = demoDevice.bindings.map((binding) => demoDevice.interfaces.find((item) => item.id === binding.interface_id)?.name);
    expect(boundNames).not.toContain("Vlan10");
    expect(boundNames).not.toContain("Loopback0");
    expect(boundNames).not.toContain("Port-channel1");
  });

  it("uses the explicit physical ID for a port detail", () => {
    const port = demoDevice.physical_ports[0];
    expect(port.id).toBe("dev-demo-01-physical-01");
    expect(boundInterface(port, demoDevice)?.name).toBe("GigabitEthernet0/1");
    expect(portStatus(port, demoDevice)).toBe("up");
  });
});

