import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

test.skip(!process.env.STOCC_QA, "Requires an isolated seeded QA project.");
const evidence = join(tmpdir(), "stocc-netstudio-panel");

async function login(page: Page) {
  await page.goto("/");
  await expect(page).toHaveTitle("Stocc NetStudio");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ağ cihazları", exact: true })).toBeVisible();
  await mkdir(evidence, { recursive: true });
}

async function expectOpticsOnRight(panel: Locator) {
  const copper = await panel.locator('[data-connector="rj45"]').boundingBox();
  const optics = await panel.locator(".optical-group .physical-port").evaluateAll((ports) =>
    ports.map((port) => {
      const { x, y, width } = port.getBoundingClientRect();
      return { x, y, width };
    }),
  );
  expect(optics.length).toBeGreaterThan(0);
  for (const [index, port] of optics.entries()) {
    expect(port.x).toBeGreaterThan(copper!.x + copper!.width);
    expect(Math.abs(port.y - optics[0].y)).toBeLessThan(1);
    if (index > 0) expect(port.x).toBeGreaterThanOrEqual(optics[index - 1].x + optics[index - 1].width);
  }
}

async function expectCopperBanks(panel: Locator, count: number) {
  const banks = panel.locator('[data-connector="rj45"] [data-port-bank]');
  await expect(banks).toHaveCount(count);
  if (count < 2) return;
  const first = await banks.nth(0).boundingBox();
  const second = await banks.nth(1).boundingBox();
  expect(second!.x - (first!.x + first!.width)).toBeGreaterThanOrEqual(8);
}

async function expectTopologyFits(page: Page, width: number) {
  const stage = page.locator(".device-topology-stage");
  await expect(stage).toHaveAttribute("data-layout", width < 520 ? "compact" : "wide");
  const chart = stage.locator(".topology-chart");
  await expect(chart.locator("svg")).toBeVisible();
  const bounds = await chart.boundingBox();
  const nodes = await chart.locator(".node-hit").evaluateAll((paths) =>
    paths
      .map((path) => {
        const box = path.getBoundingClientRect();
        return { left: box.left, right: box.right, width: box.width, height: box.height };
      })
      .filter((box) => box.width > 80 && box.height > 20),
  );
  expect(nodes).toHaveLength(7);
  for (const node of nodes) {
    expect(node.left).toBeGreaterThanOrEqual(bounds!.x - 1);
    expect(node.right).toBeLessThanOrEqual(bounds!.x + bounds!.width + 1);
  }
  const before = nodes.map(({ width: nodeWidth, height }) => ({ width: nodeWidth, height }));
  await stage.getByRole("button", { name: "Topolojiyi yakınlaştır" }).click();
  await expect(stage.getByLabel("Yakınlaştırma oranı")).toHaveText("115%");
  const after = await chart.locator(".node-hit").evaluateAll((paths) =>
    paths
      .map((path) => {
        const box = path.getBoundingClientRect();
        return { width: box.width, height: box.height };
      })
      .filter((box) => box.width > 80 && box.height > 20),
  );
  expect(after).toHaveLength(before.length);
  after.forEach((box, index) => {
    expect(Math.abs(box.width - before[index].width * 1.15)).toBeLessThan(1);
    expect(Math.abs(box.height - before[index].height * 1.15)).toBeLessThan(1);
  });
  await stage.getByRole("button", { name: "Ortala ve sıfırla", exact: true }).click();
  await expect(stage.getByLabel("Yakınlaştırma oranı")).toHaveText("100%");
  const overflow = await stage.evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }));
  expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
}

for (const width of [1536, 390]) {
  test(`rack nameplate, horizontal optics and keyboard selection at ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (!["error", "warning"].includes(message.type())) return;
      if (message.text().includes("401") && message.location().url.endsWith("/session/me")) return;
      errors.push(message.text());
    });
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
    await login(page);
    await page.getByLabel("Cihaz ara", { exact: true }).fill("QA-Core-01");
    await expect(page.locator(".device-row")).toHaveCount(1);
    await expect(page.locator("[data-chart=echarts] svg")).toHaveCount(4);
    const compact = page.locator(".device-panel.compact");
    await expect(compact.locator(".chassis-name")).toHaveText("QA-Core-01");
    await expect(compact.locator(".chassis-model")).toHaveText("QA-24RJ45-4SFP");
    await expect(compact.locator(".rack-ear[aria-hidden=true]")).toHaveCount(2);
    await expectCopperBanks(compact, 2);
    await expectOpticsOnRight(compact);
    await page.screenshot({ path: join(evidence, `dashboard-${width}.png`), fullPage: true });

    await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
    await expect(page).toHaveURL(/\/devices\/[^/]+$/);
    const panel = page.locator(".front-panel .device-panel");
    await expect(panel.locator(".chassis-name")).toHaveText("QA-Core-01");
    await expect(panel.locator(".chassis-model")).toHaveText("QA-24RJ45-4SFP");
    await expect(panel.locator(".physical-port")).toHaveCount(28);
    await expectCopperBanks(panel, 2);
    for (const [state, text] of Object.entries({ up: "UP", down: "DOWN", disabled: "ADM", unknown: "?" })) {
      const button = panel.locator(`.physical-port.${state}`).first();
      await expect(button.locator(".port-link-label")).toHaveText(text);
      await expect(button.locator(".port-indicator")).toBeVisible();
    }
    await expect(panel.locator(".up .port-indicator").first()).toHaveCSS("background-color", "rgb(57, 132, 94)");
    await expect(panel.locator(".down .port-indicator").first()).toHaveCSS("background-color", "rgb(127, 137, 146)");
    await expect(panel.locator(".unknown .port-indicator").first()).toHaveCSS("border-top-style", "dashed");
    await expectOpticsOnRight(panel);
    await expectTopologyFits(page, width);
    const port = panel.locator('[data-port-id="p25"]');
    await port.focus();
    await page.keyboard.press("Enter");
    await expect(port).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("region", { name: "25 port detayları" })).toContainText("Ethernet1/25");
    await page.getByRole("button", { name: "Yenile", exact: true }).click();
    await expect(port).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Detayı kapat", exact: true }).click();
    await panel.locator(".chassis-scroll").evaluate((element) => { element.scrollLeft = 0; });
    await page.getByRole("heading", { name: "QA-Core-01", exact: true }).click();
    await page.screenshot({ path: join(evidence, `detail-${width}.png`), fullPage: true });

    await page.getByRole("button", { name: "SSH", exact: true }).click();
    await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible({ timeout: 20000 });
    await expectOpticsOnRight(panel);
    // xterm defers DOM painting while the stacked mobile terminal is offscreen.
    await page.locator(".terminal-container").scrollIntoViewIfNeeded();
    await expect(page.locator(".xterm-rows")).toContainText("lab>");
    await page.locator(".xterm-helper-textarea").pressSequentially("panel-layout-qa");
    await page.locator(".xterm-helper-textarea").press("Enter");
    await expect(page.locator(".xterm-rows")).toContainText("TEST ECHO: panel-layout-qa");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.locator("nextjs-portal")).toHaveCount(0);
    await page.screenshot({ path: join(evidence, `detail-ssh-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: "Oturumu kapat", exact: true }).click();
    await expect(page.locator(".ssh-workspace")).toHaveCount(0);
    // A new backend observation changes the LED/text on the same selected port.
    const deviceId = page.url().split("/").pop();
    const session = await (await page.request.get("/api/v1/session/me")).json();
    const headers = { origin: process.env.PLAYWRIGHT_BASE_URL!, "x-csrf-token": session.csrf_token };
    const url = `/api/v1/devices/${deviceId}/observations`;
    const previous = await (await page.request.get(url + "/latest")).json();
    delete previous.received_at;
    delete previous.physical_summary;
    previous.interfaces.forEach((sample: { rate_reason?: string }) => delete sample.rate_reason);
    const changed = structuredClone(previous);
    changed.observed_at = new Date().toISOString();
    changed.interfaces.find((sample: { interface_id: string }) => sample.interface_id === "if1").oper_up = false;
    const firstPort = panel.locator('[data-port-id="p1"]');
    await firstPort.click();
    try {
      expect((await page.request.post(url, { headers, data: changed })).ok()).toBeTruthy();
      await page.getByRole("button", { name: "Yenile", exact: true }).click();
      await expect(firstPort.locator(".port-link-label")).toHaveText("DOWN");
      await expect(firstPort).toHaveAttribute("aria-pressed", "true");
      await expect(firstPort.locator(".port-indicator")).toHaveCSS("background-color", "rgb(127, 137, 146)");
    } finally {
      previous.observed_at = new Date().toISOString();
      expect((await page.request.post(url, { headers, data: previous })).ok()).toBeTruthy();
    }
    expect(errors).toEqual([]);
  });
}

test("48 copper ports, mixed SFP/QSFP, unknown connectors and empty inventory", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  await login(page);
  const session = await (await page.request.get("/api/v1/session/me")).json();
  const headers = { origin: process.env.PLAYWRIGHT_BASE_URL!, "x-csrf-token": session.csrf_token };
  const created = await page.request.post("/api/v1/devices", { headers, data: {
    name: "QA-Panel-Mixed", model: "QA-48RJ45-2SFP-2QSFP", site: "TEST FIXTURE / panel",
    management_address: "192.0.2.240", device_type: "switch",
  } });
  expect(created.ok()).toBeTruthy();
  const device = await created.json();
  await page.goto(`/devices/${device.id}`);
  await expect(page.getByText("Fiziksel port envanteri alınmadı.")).toBeVisible();
  await expect(page.locator(".physical-port")).toHaveCount(0);
  const copper = Array.from({ length: 48 }, (_, i) => ({
    id: `r${i + 1}`, label: String(i + 1), ordinal: i + 5, connector: "rj45", component_id: "chassis", group: "Mixed",
  }));
  const optical = ["qsfp", "sfp", "qsfp", "sfp"].map((connector, i) => ({
    id: `o${i + 1}`, label: String(i + 49), ordinal: i + 1, connector, component_id: "chassis", group: "Mixed",
  }));
  const inventory = await page.request.put(`/api/v1/devices/${device.id}/inventory`, { headers, data: {
    source: "manual", observed_at: new Date().toISOString(),
    components: [{ id: "chassis", kind: "chassis", label: "QA" }], interfaces: [], bindings: [],
    physical_ports: [...optical, ...copper,
      { id: "unknown", label: "?", ordinal: 53, connector: "unknown", component_id: "chassis", group: "Mixed" },
      { id: "child", label: "49/1", ordinal: 54, connector: "qsfp", component_id: "chassis", group: "Mixed", parent_port_id: "o1" },
    ],
  } });
  expect(inventory.ok()).toBeTruthy();
  await page.getByRole("button", { name: "Yenile", exact: true }).click();
  const panel = page.locator(".device-panel");
  await expect(panel.locator(".physical-port")).toHaveCount(53);
  await expectCopperBanks(panel, 4);
  await expect(panel.locator('[data-port-id="child"]')).toHaveCount(0);
  await expect(panel.locator('[data-connector="unknown"]')).toContainText("Tür bilinmiyor");
  await expectOpticsOnRight(panel);
  await expect(panel.locator(".rack-ear")).toHaveCount(2);
  for (const width of [1536, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
    await panel.locator('[data-port-id="o3"]').focus();
    await page.keyboard.press("Space");
    await expect(page.getByRole("region", { name: "51 port detayları" })).toContainText("QSFP");
    await page.getByRole("button", { name: "Detayı kapat", exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expectOpticsOnRight(panel);
    await page.screenshot({ path: join(evidence, `mixed-${width}.png`), fullPage: true });
  }
});
