import { describe, expect, it } from "vitest";
import type { PhysicalPort } from "../lib/contracts";
import { groupPanelPorts, panelPortBanks, RJ45_PORTS_PER_BANK } from "../lib/panel-layout";

const components = [
  { id: "chassis", kind: "chassis", label: "Chassis" },
  { id: "module", kind: "module", label: "Line card", slot: "2" },
];
const port = (id: string, connector: PhysicalPort["connector"], ordinal: number, component_id = "chassis"): PhysicalPort => ({
  id, connector, ordinal, component_id, label: id, group: "Mixed",
  verified_layout: false, parent_port_id: null, description: null,
});

describe("schematic front panel grouping", () => {
  it("places copper before SFP/QSFP even within a mixed inventory group", () => {
    const ports = [port("q1", "qsfp", 1), port("s1", "sfp", 2), port("r2", "rj45", 4), port("r1", "rj45", 3)];
    const before = structuredClone(ports);
    const groups = groupPanelPorts(ports, components);
    expect(groups.map((group) => group.connector)).toEqual(["rj45", "sfp", "qsfp"]);
    expect(groups.map((group) => group.optical)).toEqual([false, true, true]);
    expect(groups[0].ports.map((p) => p.id)).toEqual(["r1", "r2"]);
    expect(groups.flatMap((group) => group.ports)).toHaveLength(4);
    expect(ports).toEqual(before);
  });

  it("retains module/slot ownership and stable group/port identities", () => {
    const ports = [port("s1", "sfp", 1), port("s2", "sfp", 2, "module")];
    const groups = groupPanelPorts(ports, components);
    expect(groups).toHaveLength(2);
    expect(groups[1].title).toContain("Line card · Slot 2");
    expect(new Set(groups.map((group) => group.id)).size).toBe(2);
    expect(groupPanelPorts([...ports].reverse(), components)).toEqual(groups);
    expect(groups[0].ports[0]).toBe(ports[0]);
  });

  it("does not guess unknown connectors or create missing inventory", () => {
    const groups = groupPanelPorts([port("u1", "unknown", 1)], []);
    expect(groups[0].connector).toBe("unknown");
    expect(groups[0].title).toContain("Tür bilinmiyor");
    expect(groups[0].optical).toBe(false);
    expect(groupPanelPorts([], components)).toEqual([]);
  });

  it("creates a visual separator after six RJ45 columns in the two-row grid", () => {
    const ports = Array.from({ length: 26 }, (_, index) =>
      port(`r${index + 1}`, "rj45", index + 1),
    );
    const [group] = groupPanelPorts(ports, components);
    expect(RJ45_PORTS_PER_BANK).toBe(12);
    expect(panelPortBanks(group).map((bank) => bank.length)).toEqual([12, 12, 2]);
    expect(panelPortBanks(group).flat().map((item) => item.id)).toEqual(
      ports.map((item) => item.id),
    );
  });
});
