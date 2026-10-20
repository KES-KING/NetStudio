import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import type { Projection } from "../../lib/contracts";

test.skip(!process.env.NETSTUDIO_QA, "Requires the isolated QA fixtures.");
const evidence = "/tmp/netstudio-detail";
async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ağ cihazları", exact: true })).toBeVisible();
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
}
for (const width of [1536, 390, 320]) {
  test(`detail facts, bounded graph and evidence inspection at ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
    await login(page);
    await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
    const diagram = page.getByRole("region", { name: "Cihaz IP topolojisi", exact: true });
    // The shared endpoint projection adds three MAC/IP nodes plus if3.
    await expect(diagram.locator(".node-hit")).toHaveCount(11);
    await expect(diagram.locator('[data-node-id^="endpoint:"]')).toHaveCount(3);
    // Small, filtered graphs still fit wholly; the full graph is intentionally pannable.
    await diagram.getByLabel("Topolojide ara").fill("QA upstream");
    await expect(diagram.locator(".node-hit")).toHaveCount(2);
    const canvas = diagram.locator(".device-ip-canvas");
    const bounds = (await canvas.boundingBox())!;
    expect(bounds.height).toBe(340);
    const boxes = await diagram.locator(".node-hit").evaluateAll((nodes) => nodes.map((n) => {
      const r = n.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height };
    }));
    for (const box of boxes) {
      expect(box.width).toBeLessThanOrEqual(176);
      expect(box.x).toBeGreaterThanOrEqual(bounds.x);
      expect(box.x + box.width).toBeLessThanOrEqual(bounds.x + bounds.width);
      expect(box.y).toBeGreaterThanOrEqual(bounds.y);
      expect(box.y + box.height).toBeLessThanOrEqual(bounds.y + bounds.height);
    }
    const node = diagram.locator('[data-node-id="interface:if25"]');
    await node.focus(); await page.keyboard.press("Enter");
    const inspector = page.getByRole("complementary", { name: "Topoloji seçim ayrıntıları" });
    await expect(inspector).toContainText("Ethernet1/25");
    await inspector.getByRole("button", { name: "L2 komşuluk · QA upstream" }).click();
    await expect(inspector).toContainText("Isolated test fixture LLDP relation");
    await inspector.getByRole("button", { name: "Kaynak düğüme odaklan" }).click();
    await expect(diagram.getByLabel("Düğüm seç")).toHaveValue("interface:if25");
    await diagram.getByRole("button", { name: "Ortala ve sıfırla" }).click();
    await diagram.getByLabel("Topolojide ara").fill("10.10.1.0/24");
    const edge = diagram.locator(".device-ip-edge").first();
    await edge.focus(); await page.keyboard.press("Enter");
    await expect(inspector).toContainText("Bağlantı kanıtı");
    await expect(inspector).toContainText("10.10.1.1/24");
    const camera = canvas.locator("[data-camera]"), before = await camera.getAttribute("transform");
    await canvas.focus(); await page.keyboard.press("ArrowRight");
    expect(await camera.getAttribute("transform")).not.toBe(before);
    await diagram.getByRole("button", { name: "Ortala ve sıfırla" }).click();
    await expect(camera).toHaveAttribute("transform", before!);
    await diagram.getByRole("button", { name: "Taşıma modu" }).click();
    await expect(canvas).toHaveCSS("touch-action", "none");
    await diagram.getByRole("button", { name: "Taşıma modu" }).click();
    await expect(canvas).toHaveCSS("touch-action", "pan-y");
    await diagram.getByLabel("Topolojide ara").fill("10.10.2.0/24");
    await expect(diagram.locator(".node-hit")).toHaveCount(2);
    await diagram.getByLabel("Topolojide ara").fill("no-such-network");
    await expect(diagram).toContainText("Aramanızla eşleşen düğüm yok");
    await diagram.getByLabel("Topolojide ara").fill("");
    await expect(diagram.locator(".node-hit")).toHaveCount(11);
    await diagram.getByLabel("Düğüm seç").selectOption("endpoint:qa-endpoint-3");
    await expect.poll(async () => {
      const area = (await canvas.boundingBox())!, selected = (await diagram.locator('[data-node-id="endpoint:qa-endpoint-3"] .node-hit').boundingBox())!;
      return selected.y >= area.y && selected.y + selected.height <= area.y + area.height;
    }).toBe(true);
    const restoredBounds = (await canvas.boundingBox())!;
    const selectedBounds = (await diagram.locator('[data-node-id="endpoint:qa-endpoint-3"] .node-hit').boundingBox())!;
    expect(restoredBounds.height).toBe(340);
    expect(selectedBounds.y).toBeGreaterThanOrEqual(restoredBounds.y);
    expect(selectedBounds.y + selectedBounds.height).toBeLessThanOrEqual(restoredBounds.y + restoredBounds.height);
    const facts = page.getByRole("region", { name: "Teknik bilgiler ve sağlık" });
    await expect(facts).toContainText("QA-24RJ45-4SFP");
    await facts.getByText("Chassis / stack / modül envanteri", { exact: false }).click();
    await expect(facts.locator(".device-components")).toHaveAttribute("open", "");
    const interfaces = page.getByRole("region", { name: "Arayüz ayrıntıları", exact: true });
    await expect(interfaces.locator("tbody tr")).toHaveCount(12);
    await interfaces.getByRole("button", { name: "Sonraki arayüzler" }).click();
    await expect(interfaces).toContainText("Sayfa 2 / 3");
    await interfaces.getByLabel("Arayüz ara").fill("Ethernet1/25");
    await expect(interfaces.locator("tbody tr")).toHaveCount(1);
    await expect(interfaces).toContainText("10.10.25.1/24");
    await noOverflow(page);
    await mkdir(evidence, { recursive: true });
    // On phones the complete section is taller than the viewport. Capture the
    // bounded canvas separately so the sticky app header cannot obscure it.
    await (width < 540 ? diagram.locator(".device-topology-stage") : diagram).screenshot({ path: `${evidence}/topology-${width}.png` });
    await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: `${evidence}/details-${width}.png`, fullPage: true });
    expect(errors).toEqual([]);
  });
}

test("large and stale data remains searchable, bounded and explicitly unknown", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  let noData = false;
  await page.route("**/api/v1/devices/*/overview", async (route) => {
    const response = await route.fetch();
    const row: Projection = await response.json();
    row.data_state = "stale";
    row.device.model = "QA-long-model-".repeat(20);
    row.topology.nodes = Array.from({ length: 250 }, (_, i) => ({
      id: `dense-${i}`, name: `Interface-${i}`, kind: i % 2 ? "subnet" : "interface", detail: `192.0.${i}.0/24`,
    }));
    row.topology.links = Array.from({ length: 125 }, (_, i) => ({
      source: `dense-${i * 2}`, target: `dense-${i * 2 + 1}`, relation: "l3", evidence: "Synthetic dense graph",
    }));
    if (row.telemetry) {
      row.telemetry.observed_at = "2020-01-01T00:00:00Z";
      row.telemetry.health.cpu_percent = null;
      row.telemetry.health.memory_percent = null;
      row.telemetry.health.temperature_c = null;
      row.telemetry.interfaces[0] = { ...row.telemetry.interfaces[0], rx_bps: 0, tx_bps: null, errors: 0, discards: null };
    }
    if (noData) {
      row.data_state = "no_data"; row.telemetry = null; row.last_success_at = null;
      row.health_status = "unknown"; row.reachability = "unknown";
      row.topology = { nodes: [], links: [], observed_at: null, source: null };
      row.ports = { ...row.ports, rx_bps: null, tx_bps: null, measured_interfaces: 0,
        counts: { up: 0, down: 0, disabled: 0, unknown: row.ports.total } };
    }
    await route.fulfill({ response, json: row });
  });
  await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
  const diagram = page.getByRole("region", { name: "Cihaz IP topolojisi", exact: true });
  await expect(diagram.locator(".node-hit")).toHaveCount(80);
  await expect(diagram).toContainText("80 / 250 düğüm");
  await diagram.getByLabel("Düğüm seç").selectOption("dense-248");
  await expect(diagram.locator('[data-node-id="dense-248"]')).toHaveAttribute("aria-pressed", "true");
  await diagram.getByLabel("Topolojide ara").fill("192.0.248.0");
  await expect(diagram.locator(".node-hit")).toHaveCount(2);
  await expect(diagram).toContainText("güncellik doğrulanmıyor");
  const facts = page.getByRole("region", { name: "Teknik bilgiler ve sağlık" });
  await expect(facts).toContainText("Son bilinen sağlık değerleri");
  await expect(facts.getByText("CPU / RAM", { exact: true }).locator("..")).toContainText("Veri yok / Veri yok");
  const interfaces = page.getByRole("region", { name: "Arayüz ayrıntıları", exact: true });
  await expect(interfaces).toContainText("Son veri güncel değil");
  await expect(interfaces.locator("tbody tr").first()).toContainText("0 bit/s");
  await expect(interfaces.locator("tbody tr").first()).toContainText("Veri yok");
  await noOverflow(page);
  noData = true;
  await page.reload();
  await expect(diagram).toContainText("doğrulanmış IP veya komşuluk ilişkisi yok");
  await expect(diagram.locator(".node-hit")).toHaveCount(0);
  await expect(interfaces.locator("tbody tr").first()).toContainText("Ölçüm yok");
  await expect(page.getByLabel("Cihaz ölçüm özeti")).toContainText("Veri yok");
  await noOverflow(page);
});
