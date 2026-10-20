import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { GRAPH_DEVICE_LIMIT } from "../../lib/topology";

test.describe.configure({ mode: "serial" });
test.skip(!process.env.NETSTUDIO_QA, "Only run against an isolated, explicitly seeded QA project.");
const origin = process.env.PLAYWRIGHT_BASE_URL!;
const evidence = join(tmpdir(), "netstudio-topology");
const username = `qa-topology-${Date.now()}`, password = "qa-topology-test-password-123";
let userId = "", csrf = "", coreId = "", edgeId = "", deviceCount = 0;

test.beforeAll(async ({ request }) => {
  expect(new URL(origin).hostname).toBe("127.0.0.1");
  await expect.poll(async () => (await request.get("/api/v1/session/me")).status(), { timeout: 15000 }).toBe(401);
  const login = await request.post("/api/v1/session/login", { headers: { origin }, data: { username: "qa-admin", password: "test-only-password-1234" } });
  expect(login.status()).toBe(200); csrf = (await login.json()).csrf_token;
  const devices = await (await request.get("/api/v1/devices")).json();
  coreId = devices.find((d: { name: string }) => d.name === "QA-Core-01")?.id;
  edgeId = devices.find((d: { name: string }) => d.name === "QA-Edge-02")?.id;
  deviceCount = devices.filter((d: { site: string }) => d.site === "TEST FIXTURE / isolated").length;
  expect(coreId).toBeTruthy(); expect(edgeId).toBeTruthy();
  const user = await request.post("/api/v1/users", { headers: { origin, "x-csrf-token": csrf }, data: {
    username, display_name: "QA Topology Viewer", password, role: "viewer", sites: ["TEST FIXTURE / isolated"],
  } });
  expect(user.status()).toBe(201); userId = (await user.json()).id;
  await mkdir(evidence, { recursive: true });
});
test.afterAll(async ({ request }) => {
  if (!userId) return;
  const login = await request.post("/api/v1/session/login", { headers: { origin }, data: { username: "qa-admin", password: "test-only-password-1234" } });
  const token = (await login.json()).csrf_token;
  const response = await request.delete(`/api/v1/users/${userId}`, { headers: { origin, "x-csrf-token": token }, data: { confirmation_username: username } });
  expect(response.status()).toBe(200);
});
async function enter(page: Page) {
  await page.goto("/topology");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill(username);
  await page.getByLabel("Parola", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Topoloji", exact: true })).toBeVisible();
  await expect(page.locator(".network-device")).toHaveCount(Math.min(deviceCount, GRAPH_DEVICE_LIMIT));
  await expect(page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).locator("option")).toHaveCount(deviceCount + 1);
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
}
function errors(page: Page) {
  const values: string[] = [];
  page.on("pageerror", (e) => values.push(e.message));
  page.on("console", (e) => { if (["error", "warning"].includes(e.type()) && !(e.location().url.endsWith("/session/me") && e.text().includes("401"))) values.push(e.text()); });
  return values;
}

test("viewer creates personal zones, assigns and moves devices, connects real ports and persists", async ({ page }) => {
  const failures = errors(page);
  await page.setViewportSize({ width: 1536, height: 1000 }); await enter(page);
  await expect(page.getByRole("link", { name: "Denetim kayıtları", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Zone ekle", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Zone adı", { exact: true }).fill("Merkez");
  await dialog.getByRole("combobox", { name: "Yüzey tonu", exact: true }).selectOption("blue");
  await dialog.getByRole("button", { name: "Zone oluştur", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).selectOption(coreId);
  const zoneId = await page.getByLabel("Cihazın zone’u").locator("option").filter({ hasText: "Merkez" }).getAttribute("value");
  await page.getByLabel("Cihazın zone’u").selectOption(zoneId!);
  const device = page.locator(`.network-device[data-id="${coreId}"]`);
  await device.focus(); await page.keyboard.press("ArrowRight");
  await expect(page.getByText("Kaydedilmemiş değişiklikler", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Zone ekle", exact: true }).click();
  await dialog.getByLabel("Zone adı", { exact: true }).fill("Ofis");
  await dialog.getByRole("combobox", { name: "Yüzey tonu", exact: true }).selectOption("sand");
  await dialog.getByRole("button", { name: "Zone oluştur", exact: true }).click();
  await page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).selectOption(edgeId);
  const office = await page.getByLabel("Cihazın zone’u").locator("option").filter({ hasText: "Ofis" }).getAttribute("value");
  await page.getByLabel("Cihazın zone’u").selectOption(office!);
  await page.getByRole("button", { name: "Bağlantı ekle", exact: true }).click();
  await dialog.getByRole("combobox", { name: "Kaynak cihaz", exact: true }).selectOption(coreId);
  await dialog.getByRole("combobox", { name: "Hedef cihaz", exact: true }).selectOption(edgeId);
  await dialog.getByRole("combobox", { name: "Kaynak port", exact: true }).selectOption("p1");
  await dialog.getByRole("combobox", { name: "Hedef port", exact: true }).selectOption("p2");
  await dialog.getByRole("button", { name: "Bağlantıyı çiz", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Elle çizilen bağlantı", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Kaydet", exact: true }).click();
  await expect(page.getByText("Yerleşim kaydedildi.", { exact: true })).toBeVisible();
  await page.reload(); await expect(page.locator(".network-zone")).toHaveCount(2);
  // Reused QA projects can exceed the canvas budget. Filter the two seeded
  // devices by their known fixture MAC prefix without deleting other devices.
  await page.getByLabel("Cihaz, MAC veya IP ara", { exact: true }).fill("02:00:00:");
  await expect(page.locator(".network-device")).toHaveCount(2);
  await expect(page.locator(".network-canvas .topology-edge.manual")).toHaveCount(1);
  await page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).selectOption(coreId);
  await expect(page.getByLabel("Cihazın zone’u")).toHaveValue(zoneId!);
  await page.getByRole("button", { name: /192\.0\.2\.101 · 02:00:00:00:00:01/ }).click();
  await expect(page.getByRole("heading", { name: "Uç gözlemi", exact: true })).toBeVisible();
  await expect(page.locator(".topology-facts")).toContainText("Ethernet1/1");
  await expect(page.locator(".topology-facts")).toContainText("FDB");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1536);
  await page.screenshot({ path: join(evidence, "topology-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.getByRole("button", { name: "Ortala", exact: true }).click();
  const canvas = await page.locator(".network-canvas").boundingBox();
  await page.mouse.move(canvas!.x + 500, canvas!.y + 10); await page.mouse.down();
  await page.mouse.move(canvas!.x + 150, canvas!.y + 10, { steps: 6 }); await page.mouse.up();
  await page.screenshot({ path: join(evidence, "topology-overview.png"), fullPage: true });
  expect(failures).toEqual([]);
});

test("drag, zoom, search and version conflicts preserve unsaved edits", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 1000 }); await enter(page);
  await page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).selectOption(coreId);
  const device = page.locator(`.network-device[data-id="${coreId}"]`);
  const before = await device.getAttribute("transform");
  const box = await device.boundingBox(); expect(box).toBeTruthy();
  await page.mouse.move(box!.x + 100, box!.y + 20); await page.mouse.down(); await page.mouse.move(box!.x + 140, box!.y + 40, { steps: 6 }); await page.mouse.up();
  await expect(device).not.toHaveAttribute("transform", before!);
  await page.getByRole("button", { name: "Topolojiyi yakınlaştır" }).click();
  await expect(page.getByLabel("Yakınlaştırma oranı")).toHaveText("115%");
  await page.getByRole("button", { name: "Ortala", exact: true }).click();
  await expect(page.getByLabel("Yakınlaştırma oranı")).toHaveText("100%");
  await page.getByLabel("Cihaz, MAC veya IP ara", { exact: true }).fill("192.0.2.101");
  await expect(page.locator(".network-device")).toHaveCount(1);
  await page.getByLabel("Cihaz, MAC veya IP ara", { exact: true }).fill("");
  // A different tab commits the same user's board while this tab has a draft.
  const response = await page.request.get("/api/v1/topology/board");
  const board = await response.json();
  const session = await (await page.request.get("/api/v1/session/me")).json();
  const put = await page.request.put("/api/v1/topology/board", { headers: { origin, "x-csrf-token": session.csrf_token }, data: { version: board.version, zones: board.zones, placements: board.placements, links: board.links } });
  expect(put.status()).toBe(200);
  await page.getByRole("button", { name: "Kaydet", exact: true }).click();
  await expect(page.locator(".topology-workspace").getByRole("alert")).toContainText("başka bir sekmede değişti");
  await expect(page.getByRole("button", { name: "Kaydet", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Yerleşimi yeniden yükle", exact: true }).click();
  await page.getByRole("button", { name: "Yüklemeyi onayla", exact: true }).click();
  await expect(page.getByRole("button", { name: "Kaydet", exact: true })).toBeDisabled();
});

test("mobile keeps the canvas readable and exposes details without horizontal page overflow", async ({ page }) => {
  const failures = errors(page);
  await page.setViewportSize({ width: 390, height: 844 }); await enter(page);
  await page.getByLabel("Cihaz, MAC veya IP ara", { exact: true }).fill("02:00:00:");
  const canvasBounds = await page.locator(".network-canvas").boundingBox();
  expect(canvasBounds!.y).toBeLessThan(560);
  await page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).selectOption(coreId);
  await expect(page.locator(".network-canvas")).toBeVisible();
  await page.getByRole("button", { name: /192\.0\.2\.101 · 02:00:00:00:00:01/ }).click();
  await expect(page.getByRole("heading", { name: "Uç gözlemi", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Taşıma modu", exact: true }).click();
  await expect(page.getByRole("button", { name: "Taşıma modu", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(evidence, "topology-mobile.png"), fullPage: true });
  await page.screenshot({ path: join(evidence, "topology-mobile-viewport.png"), fullPage: false });
  await page.setViewportSize({ width: 844, height: 390 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(844);
  await page.screenshot({ path: join(evidence, "topology-landscape.png"), fullPage: true });
  expect(failures).toEqual([]);
});

test("removing personal links and zones preserves the inventory", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 1000 }); await enter(page);
  await page.locator(".topology-accessible-list summary").click();
  await page.locator(".topology-accessible-list button").filter({ hasText: "Elle çizilen" }).click();
  await page.getByRole("button", { name: "Bağlantıyı kaldır", exact: true }).click();
  await expect(page.locator(".network-canvas .topology-edge.manual")).toHaveCount(0);
  const zone = page.getByRole("button", { name: "Zone: Merkez. Taşımak için ok tuşları.", exact: true });
  await zone.focus(); await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Zone’u kaldır", exact: true }).click();
  await page.getByRole("button", { name: "Kaldırmayı onayla", exact: true }).click();
  await expect(page.locator(".network-zone")).toHaveCount(1);
  await expect(page.locator(".network-device")).toHaveCount(Math.min(deviceCount, GRAPH_DEVICE_LIMIT));
  await expect(page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).locator("option")).toHaveCount(deviceCount + 1);
  await page.getByRole("button", { name: "Kaydet", exact: true }).click();
  await expect(page.getByText("Yerleşim kaydedildi.", { exact: true })).toBeVisible();
  await page.reload(); await expect(page.locator(".network-device")).toHaveCount(Math.min(deviceCount, GRAPH_DEVICE_LIMIT));
  await expect(page.getByRole("combobox", { name: "Cihaza odaklan", exact: true }).locator("option")).toHaveCount(deviceCount + 1);
  await expect(page.locator(".network-zone")).toHaveCount(1);
});
