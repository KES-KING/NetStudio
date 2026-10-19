import type { Device, PhysicalPort } from "./contracts";

export type PanelGroup = {
  id: string;
  title: string;
  connector: PhysicalPort["connector"];
  optical: boolean;
  ports: PhysicalPort[];
};

export const RJ45_PORTS_PER_BANK = 12;

const connectorOrder = { rj45: 0, unknown: 1, management: 1, console: 1, sfp: 2, qsfp: 3 };

// Presentation only: keep inventory identities/module labels, without claiming a
// measured physical layout. A mixed inventory group must not stack optical ports.
export function groupPanelPorts(
  ports: readonly PhysicalPort[],
  components: Device["components"],
): PanelGroup[] {
  const componentById = new Map(components.map((component) => [component.id, component]));
  const groups = new Map<string, PanelGroup>();
  for (const port of [...ports].sort((a, b) => a.ordinal - b.ordinal)) {
    const id = JSON.stringify([port.component_id, port.group, port.connector]);
    let group = groups.get(id);
    if (!group) {
      const component = componentById.get(port.component_id);
      group = {
        id,
        title: [
          component?.kind !== "chassis" ? component?.label : null,
          component?.slot ? `Slot ${component.slot}` : null,
          port.group || "Portlar",
          port.connector === "unknown" ? "Tür bilinmiyor" : port.connector.toUpperCase(),
        ].filter(Boolean).join(" · "),
        connector: port.connector,
        optical: port.connector === "sfp" || port.connector === "qsfp",
        ports: [],
      };
      groups.set(id, group);
    }
    group.ports.push(port);
  }
  return [...groups.values()].sort(
    (a, b) => connectorOrder[a.connector] - connectorOrder[b.connector],
  );
}

// RJ45 ports are drawn in two rows. Twelve inventory entries therefore form a
// six-column bank before the small physical-style separator. This is explicitly
// schematic and does not claim measured vendor chassis coordinates.
export function panelPortBanks(group: PanelGroup): PhysicalPort[][] {
  const bankSize = group.connector === "rj45"
    ? RJ45_PORTS_PER_BANK
    : Math.max(1, group.ports.length);
  const banks: PhysicalPort[][] = [];
  for (let index = 0; index < group.ports.length; index += bankSize)
    banks.push(group.ports.slice(index, index + bankSize));
  return banks;
}
