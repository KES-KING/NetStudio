import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test.skip(!process.env.STOCC_QA, "Only the isolated QA API; no real device/network scanning.");
test.describe.configure({ mode: "serial" });
const origin = process.env.PLAYWRIGHT_BASE_URL!;
const tag = Date.now(), site = `TEST FIXTURE / MAC-IP ${tag}`;
let switchId = "", gatewayId = "";

test.beforeAll(async ({ request }) => {
  expect(new URL(origin).hostname).toBe("127.0.0.1");
  const auth = await request.post("/api/v1/session/login", { headers: { origin },
    data: { username: "qa-admin", password: "test-only-password-1234" } });
  expect(auth.status()).toBe(200);
  const headers = { origin, "x-csrf-token": (await auth.json()).csrf_token };
  const at = new Date().toISOString();
  const unknown = { value: null, observed_at: at, stale_after_seconds: 3600, source: "manual", quality: "unknown" };
  for (const role of ["switch", "gateway"]) {
    const response = await request.post("/api/v1/devices", { headers, data: {
      name: `QA-MAC-${role}-${tag}`, site, management_address: role === "switch" ? "192.0.2.241" : "192.0.2.254",
      collector: "external", device_type: "switch",
    } });
    expect(response.status()).toBe(201);
    const id = (await response.json()).id;
    if (role === "switch") switchId = id; else gatewayId = id;
    const inventory = await request.put(`/api/v1/devices/${id}/inventory`, { headers, data: {
      source: "manual", observed_at: at, components: [{ id: "chassis", kind: "chassis", label: "QA fixture" }],
      physical_ports: [{ id: "p1", component_id: "chassis", label: "1", connector: "rj45", group: "QA", ordinal: 1 }],
      interfaces: [{ id: "if1", name: "Ethernet1", kind: "ethernet" }, { id: "if5", name: "Vlan10", kind: "svi" }]
        .map((i) => ({ ...i, admin_up: unknown, oper_up: unknown, speed_mbps: unknown })),
      bindings: [{ id: "binding", physical_port_id: "p1", interface_id: "if1", binding_quality: "explicit" }],
    } });
    expect(inventory.status()).toBe(200);
  }
  const common = { observed_at: at, source: "manual", reachability: "reachable", stale_after_seconds: 3600,
    interfaces: [{ interface_id: "if1", admin_up: true, oper_up: true }, { interface_id: "if5", addresses: ["192.0.2.254/24"] }] };
  const fdb = { id: "resolved", interface_id: "if1", mac: "02:ee:00:00:00:01", addresses: [], vlan: 10,
    discovery: "fdb", state: "unknown", evidence: "Isolated QA FDB fixture" };
  expect((await request.post(`/api/v1/devices/${switchId}/observations`, { headers, data: { ...common,
    endpoints: { status: "ok", entries: [fdb, { ...fdb, id: "unresolved", mac: "02:ee:00:00:00:02" }] },
    neighbors: [{ id: "lldp", interface_id: "if1", label: "02:ee:00:00:00:fe", relation: "l2",
      addresses: ["192.0.2.254"], evidence: "Isolated QA LLDP management address" }],
  } })).status()).toBe(201);
  expect((await request.post(`/api/v1/devices/${gatewayId}/observations`, { headers, data: { ...common,
    endpoints: { status: "ok", entries: [
      { ...fdb, id: "arp", interface_id: "if5", discovery: "arp", addresses: ["192.0.2.101"], vrf_known: true, evidence: "Isolated QA ARP fixture" },
      { ...fdb, id: "ndp", interface_id: "if5", discovery: "ndp", addresses: ["2001:db8::101"], vrf_known: true, evidence: "Isolated QA NDP fixture" },
    ] },
  } })).status()).toBe(201);
  await mkdir("/tmp/stocc-netstudio-mac-ip", { recursive: true });
});

for (const width of [1536, 390]) test(`MAC resolves consistently in port and both topologies at ${width}px`, async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (e) => {
    if (["error", "warning"].includes(e.type()) && !(e.location().url.endsWith("/session/me") && e.text().includes("401"))) errors.push(e.text());
  });
  await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
  await page.goto(`/devices/${switchId}`);
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page).toHaveTitle("Stocc NetStudio");
  await expect(page).toHaveURL(`${origin}/devices/${switchId}`);
  await expect(page.getByRole("heading", { name: `QA-MAC-switch-${tag}`, exact: true })).toBeVisible();
  await page.locator('.physical-port[data-port-id="p1"]').click();
  const port = page.getByRole("region", { name: "1 port detayları", exact: true });
  await expect(port).toContainText("192.0.2.101");
  await expect(port).toContainText("2001:db8::101");
  await expect(port).toContainText("IP eşleştirildi");
  await expect(port).toContainText("IP bulunamadı");
  await port.locator(".endpoint-details").first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: `/tmp/stocc-netstudio-mac-ip/port-${width}.png`, animations: "disabled" });
  await port.getByText("Adres kanıtı", { exact: true }).first().click();
  await expect(port).toContainText(`QA-MAC-gateway-${tag}`);
  await port.getByRole("button", { name: "Detayı kapat", exact: true }).click();

  const graph = page.getByRole("region", { name: "Cihaz IP topolojisi", exact: true });
  await graph.getByRole("combobox", { name: "Düğüm seç", exact: true }).selectOption("endpoint:resolved");
  const detail = graph.getByRole("complementary", { name: "Topoloji seçim ayrıntıları" });
  await expect(detail).toContainText("IP eşleştirildi");
  await expect(detail).toContainText("02:ee:00:00:00:01");
  await expect(detail).toContainText("2001:db8::101");
  await expect(detail.getByText("VLAN / VRF", { exact: true })).toHaveCount(1);
  await expect(detail.getByText("VRF", { exact: true })).toHaveCount(0);
  await graph.getByRole("combobox", { name: "Düğüm seç", exact: true }).selectOption("endpoint:unresolved");
  await expect(detail).toContainText("IP bulunamadı");
  await graph.getByRole("combobox", { name: "Düğüm seç", exact: true }).selectOption("endpoint:resolved");
  await graph.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `/tmp/stocc-netstudio-mac-ip/device-topology-${width}.png`, animations: "disabled" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.goto("/topology");
  await expect(page.getByRole("heading", { name: "Topoloji", exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).selectOption(switchId);
  const inspector = page.getByRole("complementary", { name: "Topoloji seçim ayrıntıları" });
  await inspector.locator(".endpoint-results button").filter({ hasText: "192.0.2.101" }).click();
  await expect(inspector).toContainText("IP eşleştirildi");
  await expect(inspector).toContainText("2001:db8::101");
  await inspector.getByText("Adres kanıtı", { exact: true }).click();
  await expect(inspector).toContainText(`QA-MAC-gateway-${tag}`);
  await inspector.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `/tmp/stocc-netstudio-mac-ip/network-topology-${width}.png`, animations: "disabled" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  expect(errors).toEqual([]);
});
