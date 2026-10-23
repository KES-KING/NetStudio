import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

test.skip(!process.env.NETSTUDIO_QA, "Requires isolated QA, never production.");
const evidence = join(tmpdir(), "netstudio-navigation");

async function login(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (message.location().url.endsWith("/api/v1/session/me") && message.text().includes("401")) return;
    errors.push(message.text());
  });
  await page.goto("/");
  await expect(page).toHaveTitle("NetStudio");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("link", { name: "QA-Core-01", exact: true })).toBeVisible();
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  await mkdir(evidence, { recursive: true });
  return errors;
}

async function expectSidebarWidth(page: Page, width: number) {
  await expect.poll(async () => Math.round((await page.locator(".sidebar").boundingBox())!.width)).toBe(width);
  await expect.poll(async () => Math.round((await page.locator(".topbar-brand").boundingBox())!.width)).toBe(width);
}

async function noOverflow(page: Page, width: number) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

test("animated rail preserves charts, persists across routes and reload, remains keyboard usable", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  const errors = await login(page);
  await expectSidebarWidth(page, 232);
  await expect(page.locator(".console-layout")).toHaveCSS("transition-duration", "0.22s");
  const chart = page.locator("[data-chart=echarts]").first();
  await expect(chart.locator("svg")).toBeVisible();
  const instance = await chart.getAttribute("_echarts_instance_");
  const originalWidth = (await chart.boundingBox())!.width;
  await page.screenshot({ path: join(evidence, "expanded-desktop.png"), animations: "disabled" });
  // A full-page capture resizes the viewport internally. Header geometry must
  // remain aligned, not start an unintended grid-track transition.
  await page.screenshot({ path: join(evidence, "expanded-fullpage.png"), fullPage: true, animations: "disabled" });
  expect((await page.locator(".topbar-brand").boundingBox())!.width).toBe(232);
  const collapse = page.getByRole("button", { name: "Yan menüyü daralt", exact: true });
  await collapse.focus();
  await page.keyboard.press("Enter");
  const expand = page.getByRole("button", { name: "Yan menüyü genişlet", exact: true });
  await expect(expand).toBeFocused();
  await expect(expand).toHaveAttribute("aria-expanded", "false");
  await expectSidebarWidth(page, 76);
  await expect(chart).toHaveAttribute("_echarts_instance_", instance!);
  await expect.poll(async () => (await chart.boundingBox())!.width).toBeGreaterThan(originalWidth);
  await expect.poll(async () => Number(await chart.locator("svg").getAttribute("width")))
    .toBeGreaterThan(originalWidth - 2);
  await noOverflow(page, 1536);
  const nav = page.getByRole("navigation", { name: "Ana navigasyon" });
  await expect(nav.getByRole("link")).toHaveCount(5);
  const jobs = nav.getByRole("link", { name: "İş geçmişi", exact: true });
  await jobs.focus();
  await expect(jobs).toBeFocused();
  await expect(jobs).toHaveCSS("outline-style", "solid");
  await page.screenshot({ path: join(evidence, "collapsed-desktop.png"), animations: "disabled" });
  await page.screenshot({ path: join(evidence, "collapsed-fullpage.png"), fullPage: true, animations: "disabled" });
  expect((await page.locator(".topbar-brand").boundingBox())!.width).toBe(76);
  // Capture is a separate evidence step. Dispatch the keyboard interaction to
  // its actual target instead of assuming global focus after both captures.
  await jobs.press("Enter");
  await expect(page.locator(".topbar-page strong")).toHaveText("İş geçmişi");
  await expect(jobs).toHaveAttribute("aria-current", "page");
  await expectSidebarWidth(page, 76);
  await page.reload();
  await expectSidebarWidth(page, 76);
  const storage = await page.evaluate(() => Object.entries(localStorage));
  expect(storage).toHaveLength(1);
  expect(storage[0][0]).toMatch(/^netstudio:sidebar:v1:/);
  expect(storage[0][1]).toBe("collapsed");
  await expand.click();
  await expectSidebarWidth(page, 232);
  for (const width of [701, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page, width);
    await expect(expand).toBeHidden();
    await expect(collapse).toBeVisible();
  }
  await page.setViewportSize({ width: 2560, height: 900 });
  await noOverflow(page, 2560);
  await expect(page.locator(".sidebar-footer")).toBeInViewport();
  expect(errors).toEqual([]);
});

test("mobile drawer contains focus, closes by escape, backdrop and navigation, and restores desktop rail", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  const errors = await login(page);
  await page.getByRole("button", { name: "Yan menüyü daralt", exact: true }).click();
  await expectSidebarWidth(page, 76);
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    const menu = page.getByRole("button", { name: "Menü", exact: true });
    await expect(page.locator(".sidebar")).toBeHidden();
    await menu.click();
    const drawer = page.getByRole("dialog", { name: "Navigasyon menüsü", exact: true });
    const close = drawer.getByRole("button", { name: "Menüyü kapat", exact: true });
    await expect(close).toBeFocused();
    await expect(page.locator("main")).toHaveAttribute("inert", "");
    await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
    await expect(page.locator(".sidebar-backdrop")).toHaveCSS("top", "0px");
    await expect(drawer.getByText("Envanter ve portlar", { exact: true })).toBeVisible();
    await page.keyboard.press("Shift+Tab");
    await expect(drawer.locator(".sidebar-account-link")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(close).toBeFocused();
    await noOverflow(page, width);
    await page.screenshot({ path: join(evidence, `drawer-${width}.png`), animations: "disabled" });
    await page.keyboard.press("Escape");
    await expect(page.locator(".sidebar")).toBeHidden();
    await expect(menu).toBeFocused();
    await expect(page.locator("main")).not.toHaveAttribute("inert");
    await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
    await menu.click();
    const backdrop = page.locator(".sidebar-backdrop");
    const backdropBox = await backdrop.boundingBox();
    const drawerBox = await drawer.boundingBox();
    await backdrop.click({ position: { x: (backdropBox!.width + drawerBox!.width) / 2, y: 40 } });
    await expect(page.locator(".sidebar")).toBeHidden();
    await menu.click();
    await drawer.getByRole("link", { name: "İş geçmişi", exact: true }).click();
    await expect(page.getByRole("heading", { name: "İş geçmişi", exact: true })).toBeVisible();
    await expect(page.locator(".sidebar")).toBeHidden();
    await menu.click();
    await drawer.getByRole("link", { name: "Ağ cihazları", exact: true }).click();
  }
  await page.getByRole("button", { name: "Menü", exact: true }).click();
  await page.setViewportSize({ width: 1536, height: 1024 });
  await expectSidebarWidth(page, 76);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
  await expect(page.getByRole("button", { name: "Yan menüyü genişlet" })).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".sidebar")).toBeHidden();
  expect(errors).toEqual([]);
});

test("sidebar resize does not reconnect a real SSH session", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  const errors = await login(page);
  const sockets: string[] = [];
  page.on("websocket", (socket) => sockets.push(socket.url()));
  await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
  await page.getByRole("button", { name: "SSH", exact: true }).click();
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible({ timeout: 20000 });
  const socketCount = sockets.length;
  expect(socketCount).toBeGreaterThan(0);
  const terminal = page.locator(".xterm-helper-textarea");
  await terminal.pressSequentially("before-collapse");
  await terminal.press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText("TEST ECHO: before-collapse");
  await page.getByRole("button", { name: "Yan menüyü daralt" }).click();
  await expectSidebarWidth(page, 76);
  await terminal.pressSequentially("after-collapse");
  await terminal.press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText("TEST ECHO: after-collapse");
  await page.getByRole("button", { name: "Yan menüyü genişlet" }).click();
  await expectSidebarWidth(page, 232);
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible();
  expect(sockets).toHaveLength(socketCount);
  await page.getByRole("button", { name: "Oturumu kapat" }).click();
  expect(errors).toEqual([]);
});

test("reduced motion and unavailable local storage do not block navigation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new DOMException("Blocked", "SecurityError"); };
    Storage.prototype.setItem = () => { throw new DOMException("Blocked", "SecurityError"); };
  });
  await page.setViewportSize({ width: 1024, height: 768 });
  const errors = await login(page);
  await expect(page.locator(".console-layout")).toHaveCSS("transition-duration", "0s");
  await page.getByRole("button", { name: "Yan menüyü daralt" }).click();
  await expectSidebarWidth(page, 76);
  await page.getByRole("button", { name: "Yan menüyü genişlet" }).click();
  await expectSidebarWidth(page, 232);
  await noOverflow(page, 1024);
  await page.setViewportSize({ width: 844, height: 390 });
  const bounds = await page.locator(".sidebar").evaluate((element) => ({
    client: element.clientHeight, scroll: element.scrollHeight,
  }));
  expect(bounds.scroll).toBeGreaterThan(bounds.client);
  await page.locator(".sidebar-account-link").scrollIntoViewIfNeeded();
  await expect(page.locator(".sidebar-account-link")).toBeInViewport();
  const footer = (await page.locator(".sidebar-footer").boundingBox())!;
  expect(footer.y + footer.height).toBeLessThanOrEqual(390);
  await page.screenshot({ path: join(evidence, "short-screen.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Menü", exact: true }).click();
  await expect(page.locator(".sidebar")).toHaveCSS("transition-duration", "0s");
  await page.getByRole("button", { name: "Menüyü kapat", exact: true }).click();
  await expect(page.locator(".sidebar")).toBeHidden();
  expect(errors).toEqual([]);
});
