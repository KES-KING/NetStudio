import { describe, expect, it } from "vitest";
import { commandDriverFor, groupedCommands } from "../lib/command-helper";
import type { Device, DriverCatalogEntry } from "../lib/contracts";

const baseDevice = {
  vendor: "",
  model: "",
  platform: "",
  collector: "external",
} as Device;

describe("device-specific command helper", () => {
  it("prefers the collector resolved from the device over configuration", () => {
    expect(
      commandDriverFor({
        ...baseDevice,
        collector: "cisco_ios",
        resolved_collector: "huawei_vrp",
      }),
    ).toEqual({ id: "huawei_vrp", source: "resolved" });
  });

  it("uses an explicitly configured supported collector", () => {
    expect(
      commandDriverFor({ ...baseDevice, collector: "juniper_junos" }),
    ).toEqual({ id: "juniper_junos", source: "configured" });
    expect(
      commandDriverFor({ ...baseDevice, collector: "dell_os6" }),
    ).toEqual({ id: "dell_os6", source: "configured" });
  });

  it("maps explicit vendor and platform identity when collection is external", () => {
    expect(commandDriverFor({ ...baseDevice, vendor: "Cisco" })).toEqual({
      id: "cisco_ios",
      source: "identity",
    });
    expect(
      commandDriverFor({ ...baseDevice, vendor: "Cisco", platform: "NX-OS" }),
    ).toEqual({ id: "cisco_nxos", source: "identity" });
    expect(commandDriverFor({ ...baseDevice, vendor: "Huawei" })).toEqual({
      id: "huawei_vrp",
      source: "identity",
    });
    expect(commandDriverFor(baseDevice)).toBeNull();
  });

  it("groups catalog commands in a stable help order", () => {
    const entry = {
      commands: [
        { text: "network", group: "network" },
        { text: "inventory", group: "inventory" },
        { text: "fast", group: "fast" },
      ],
    } as DriverCatalogEntry;
    expect(groupedCommands(entry).map(({ group }) => group)).toEqual([
      "inventory",
      "fast",
      "network",
    ]);
  });
});
