import type {
  Device,
  DeviceCollector,
  DriverCatalogEntry,
  DriverCommand,
} from "./contracts";

export type CommandDriverMatch = {
  id: Exclude<DeviceCollector, "auto" | "external">;
  source: "resolved" | "configured" | "identity";
};

const supportedCollectors = new Set<DeviceCollector>([
  "linux_ssh",
  "huawei_vrp",
  "cisco_ios",
  "cisco_iosxe",
  "cisco_nxos",
  "juniper_junos",
]);

export function commandDriverFor(device: Device): CommandDriverMatch | null {
  if (
    device.resolved_collector &&
    supportedCollectors.has(device.resolved_collector)
  )
    return {
      id: device.resolved_collector as CommandDriverMatch["id"],
      source: "resolved",
    };
  if (supportedCollectors.has(device.collector))
    return {
      id: device.collector as CommandDriverMatch["id"],
      source: "configured",
    };

  const vendor = device.vendor.trim().toLocaleLowerCase("tr-TR");
  const platform = `${device.platform} ${device.model}`.toLocaleLowerCase("tr-TR");
  if (vendor.includes("cisco")) {
    if (
      platform.includes("nx-os") ||
      platform.includes("nxos") ||
      platform.includes("nexus")
    )
      return { id: "cisco_nxos", source: "identity" };
    if (platform.includes("ios-xe") || platform.includes("ios xe"))
      return { id: "cisco_iosxe", source: "identity" };
    return { id: "cisco_ios", source: "identity" };
  }
  if (vendor.includes("huawei") || platform.includes("vrp"))
    return { id: "huawei_vrp", source: "identity" };
  if (vendor.includes("juniper") || platform.includes("junos"))
    return { id: "juniper_junos", source: "identity" };
  if (vendor.includes("linux") || platform.includes("linux"))
    return { id: "linux_ssh", source: "identity" };
  return null;
}

export const commandGroupLabels: Record<DriverCommand["group"], string> = {
  fast: "Arayüzler",
  health: "Sağlık",
  network: "Ağ tabloları",
  inventory: "Envanter",
};

const commandGroupOrder: DriverCommand["group"][] = [
  "inventory",
  "fast",
  "health",
  "network",
];

export function groupedCommands(entry: DriverCatalogEntry) {
  return commandGroupOrder
    .map((group) => ({
      group,
      commands: entry.commands.filter((command) => command.group === group),
    }))
    .filter((section) => section.commands.length > 0);
}

export const validationLabels: Record<string, string> = {
  fixture_tested: "Fixture ile doğrulandı",
  lab_validated: "İzole laboratuvarda doğrulandı",
  experimental: "Deneysel",
};

export const matchSourceLabels: Record<CommandDriverMatch["source"], string> = {
  resolved: "Toplayıcı tarafından doğrulanan platform",
  configured: "Yapılandırılmış veri kaynağı",
  identity: "Cihaz üreticisi/platform kimliği",
};
