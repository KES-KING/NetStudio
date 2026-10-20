import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

test.skip(!process.env.NETSTUDIO_QA, "Requires an isolated seeded QA project.");
const evidence = join(tmpdir(), "netstudio-panel");

async function login(page: Page) {
  await page.goto("/");
  await expect(page).toHaveTitle("NetStudio");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ağ cihazları", exact: true })).toBeVisible();
  await mkdir(evidence, { recursive: true });
}

async function expectPopupFits(page: Page, port: Locator) {
  const popup = page.locator(".port-popover");
  await expect(popup).toBeVisible();
  await expect.poll(async () => {
    const rect = await popup.boundingBox();
    const view = page.viewportSize()!;
    return !!rect && rect.x >= 11 && rect.y >= 11 &&
      rect.x + rect.width <= view.width - 11 && rect.y + rect.height <= view.height - 11;
  }).toBe(true);
  const controlId = await popup.getAttribute("id");
  await expect(port).toHaveAttribute("aria-controls", controlId!);
  await expect(port).toHaveAttribute("aria-expanded", "true");
}

for (const viewport of [
  { width: 1536, height: 1024 },
  { width: 390, height: 844 },
  { width: 844, height: 390 },
]) {
  test(`fullscreen panel and anchored port popup at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const errors: string[] = [];
    const preloadAdvisories: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (!["error", "warning"].includes(message.type())) return;
      if (message.text().includes("401") && message.location().url.endsWith("/session/me")) return;
      const preload = message.type() === "warning" && message.text().match(
        /The resource (https?:\/\/[^ ]+\/_next\/static\/css\/[^ ]+\.css) was preloaded using link preload but not used/,
      );
      if (preload) {
        preloadAdvisories.push(preload[1]);
        return;
      }
      errors.push(message.text());
    });
    await page.setViewportSize(viewport);
    await login(page);
    await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
    await expect(page).toHaveURL(/\/devices\/[^/]+$/);
    const inline = page.locator(".front-panel .device-panel");
    const originalPort = inline.locator('[data-port-id="p1"]');
    await originalPort.click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expectPopupFits(page, originalPort);
    await expect(page.getByRole("region", { name: "1 port detayları" })).toContainText("Ethernet1/1");
    await page.keyboard.press("Escape");
    await expect(page.locator(".port-popover")).toHaveCount(0);
    await expect(originalPort).toBeFocused();

    // The chassis itself is an opening target, without hijacking port clicks.
    await inline.locator(".chassis-name").click();
    const dialog = page.getByRole("dialog", { name: /QA-Core-01/ });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Tam ekranı kapat" })).toBeFocused();
    expect(await dialog.boundingBox()).toMatchObject({ x: 0, y: 0, ...viewport });
    expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");
    await expect(dialog.locator(".physical-port")).toHaveCount(28);
    await expect(dialog.getByLabel("Ön panel yakınlaştırma oranı")).toHaveText("125%");
    const port = dialog.locator('[data-port-id="p1"]');
    await port.focus();
    await page.keyboard.press("Enter");
    await expectPopupFits(page, port);
    const before = (await port.boundingBox())!.width;
    // Popup follows the selected port as zoom and the scroll position change.
    await dialog.getByRole("button", { name: "Ön paneli yakınlaştır", exact: true }).click();
    await expect(dialog.getByLabel("Ön panel yakınlaştırma oranı")).toHaveText("150%");
    expect((await port.boundingBox())!.width).toBeGreaterThan(before);
    await expectPopupFits(page, port);
    await page.keyboard.press("Escape");
    await expect(page.locator(".port-popover")).toHaveCount(0);
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Sıfırla", exact: true }).click();
    await expect(dialog.getByLabel("Ön panel yakınlaştırma oranı")).toHaveText("125%");
    const optical = dialog.locator('[data-port-id="p28"]');
    await optical.click();
    await expectPopupFits(page, optical);
    await expect(page.getByRole("region", { name: "28 port detayları" })).toContainText("Ethernet1/28");
    await page.screenshot({ path: join(evidence, `inspector-${viewport.width}x${viewport.height}.png`) });
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    expect(await page.evaluate(() => document.body.style.overflow)).toBe("");

    const expand = page.getByRole("button", { name: "Tam ekran", exact: true });
    await expand.focus();
    await page.keyboard.press("Enter");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Tam ekranı kapat" }).click();
    await expect(expand).toBeFocused();
    await page.emulateMedia({ reducedMotion: "reduce" });
    const scroll = inline.locator(".chassis-scroll");
    await scroll.focus();
    await page.keyboard.press("Space");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator(".inspector-panel")).toHaveCSS("animation-name", "none");
    // Browser resize and orientation change must not strand the inspector/popup.
    await port.click();
    await page.setViewportSize({ width: viewport.height, height: viewport.width });
    await expectPopupFits(page, port);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(scroll).toBeFocused();
    await expect(page.locator("nextjs-portal")).toHaveCount(0);
    // Existing navigation prefetches /topology while the modal hides the page.
    // Verify (rather than silently discarding) Chrome's unused-preload advisory:
    // the only permitted asset is successfully served, known topology CSS.
    for (const url of new Set(preloadAdvisories)) {
      expect(new URL(url).origin).toBe(process.env.PLAYWRIGHT_BASE_URL);
      const asset = await page.request.get(url);
      expect(asset.status()).toBe(200);
      expect(await asset.text()).toMatch(/^\.topology-workspace\{/);
      test.info().annotations.push({ type: "browser-advisory", description: "Existing /topology CSS prefetch unused while inspecting the panel; asset verified HTTP 200." });
    }
    expect(errors).toEqual([]);
  });
}

test("fullscreen inspection leaves a connected SSH session alive and handles empty inventory", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  await login(page);
  await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
  await page.getByRole("button", { name: "SSH", exact: true }).click();
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible({ timeout: 20000 });
  await page.getByRole("button", { name: "Tam ekran", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible();
  await page.locator(".xterm-helper-textarea").pressSequentially("inspector-qa");
  await page.locator(".xterm-helper-textarea").press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText("TEST ECHO: inspector-qa");
  await page.getByRole("button", { name: "Oturumu kapat", exact: true }).click();
  const session = await (await page.request.get("/api/v1/session/me")).json();
  const create = await page.request.post("/api/v1/devices", {
    headers: { origin: process.env.PLAYWRIGHT_BASE_URL!, "x-csrf-token": session.csrf_token },
    data: { name: `QA-Inspector-Empty-${Date.now()}`, management_address: "192.0.2.88", device_type: "switch", site: "TEST FIXTURE / inspector" },
  });
  expect(create.ok()).toBeTruthy();
  const device = await create.json();
  await page.goto(`/devices/${device.id}`);
  await page.getByRole("button", { name: "Tam ekran", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Fiziksel port envanteri alınmadı.");
  await expect(dialog.locator(".physical-port")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});
