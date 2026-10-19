import type { Device, PhysicalPort } from "./contracts";

export type PanelGroup = {
  id: string;
  title: string;
  connector: PhysicalPort["connector"];
  optical: boolean;
  ports: PhysicalPort[];
};

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
