import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const evidenceDir = join(tmpdir(), "netstudio-qa");

function observeClientErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (message) => {
    if (!["error", "warning"].includes(message.type())) return;
    // The unauthenticated session probe intentionally returns HTTP 401.
    if (
      message.location().url.endsWith("/api/v1/session/me") &&
      message.text().includes("401")
    )
      return;
    errors.push(
      `${message.type()}: ${message.text()} (${message.location().url})`,
    );
  });
  return errors;
}

test.describe.configure({ mode: "serial" });
test.skip(
  !process.env.NETSTUDIO_QA,
  "Requires isolated seeded QA Docker project, never production.",
);
test.beforeAll(async ({ request }) => {
  mkdirSync(evidenceDir, { recursive: true });
  // Refresh only the explicitly seeded QA fixture, through the real API.
  const origin = process.env.PLAYWRIGHT_BASE_URL!;
  const auth = await request.post("/api/v1/session/login", {
    headers: { origin },
    data: { username: "qa-admin", password: "test-only-password-1234" },
  });
  expect(auth.ok()).toBeTruthy();
  const csrf = (await auth.json()).csrf_token;
  const devices = await (await request.get("/api/v1/devices")).json();
  const core = devices.find((d: { name: string }) => d.name === "QA-Core-01");
  const latest = await (
    await request.get(`/api/v1/devices/${core.id}/observations/latest`)
  ).json();
  delete latest.received_at;
  delete latest.physical_summary;
  latest.interfaces.forEach(
    (sample: { rate_reason?: string }) => delete sample.rate_reason,
  );
  latest.observed_at = new Date().toISOString();
  const response = await request.post(
    `/api/v1/devices/${core.id}/observations`,
    { headers: { origin, "x-csrf-token": csrf }, data: latest },
  );
  expect(response.ok()).toBeTruthy();
  await request.post("/api/v1/session/logout", {
    headers: { origin, "x-csrf-token": csrf },
  });
});
async function login(page: Page) {
  await page.goto("/");
  await expect(page).toHaveTitle("NetStudio");
  await expect(page).toHaveURL(
    new URL("/", process.env.PLAYWRIGHT_BASE_URL!).toString(),
  );
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page
    .getByLabel("Parola", { exact: true })
    .fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await expect(
    page.getByRole("heading", { name: "Ağ cihazları", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "QA-Core-01", exact: true }),
  ).toBeVisible();
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  const cookie = (await page.context().cookies()).find(
    (c) => c.name === "netstudio_session",
  );
  expect({
    httpOnly: cookie?.httpOnly,
    secure: cookie?.secure,
    sameSite: cookie?.sameSite,
  }).toEqual({
    httpOnly: true,
    secure: process.env.NETSTUDIO_QA_TLS === "1",
    sameSite: "Strict",
  });
}

async function useCiscoIdentityForCommandHelp(page: Page) {
  await page.route(
    /\/api\/v1\/devices\/[^/]+\/overview(?:\?.*)?$/,
    async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.device.vendor = "Cisco";
      body.device.platform = "IOS";
      body.device.collector = "cisco_ios";
      await route.fulfill({ response, json: body });
    },
  );
}

test("real API dashboard, shared filters, square design and keyboard ports", async ({
  page,
}) => {
  const errors = observeClientErrors(page);
  await page.setViewportSize({ width: 1536, height: 1024 });
  await login(page);
  await expect(page.locator("[data-chart=echarts] svg")).toHaveCount(4);
  const chart = await page
    .getByRole("region", { name: "Operasyon özeti" })
    .boundingBox();
  const list = await page
    .getByRole("region", { name: "Cihaz envanteri" })
    .boundingBox();
  expect(chart!.y + chart!.height).toBeLessThan(list!.y);
  expect(
    await page
      .locator("main")
      .evaluate((e) => getComputedStyle(e).backgroundColor),
  ).toBe("rgba(0, 0, 0, 0)");
  expect(
    await page
      .getByRole("button", { name: "Cihaz Ekle", exact: true })
      .evaluate((e) => getComputedStyle(e).borderRadius),
  ).toBe("0px");
  await page.getByLabel("Cihaz ara", { exact: true }).fill("QA-Core-01");
  await expect(page.locator(".device-row")).toHaveCount(1);
  await expect(page.locator(".refresh-info")).toContainText("1 cihaz");
  await page.screenshot({
    path: join(evidenceDir, "dashboard-desktop.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "1, Aktif", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("region", { name: "1 port detayları" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/q=QA-Core-01/);
  await page.getByRole("button", { name: "Detayı kapat" }).click();
  await page.getByLabel("Cihaz ara", { exact: true }).fill("nothing-matches");
  await expect(
    page.getByText("Filtrelere uyan cihaz bulunamadı."),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("detail, topology, inline SSH input, resize, close and logout", async ({
  page,
}) => {
  const errors = observeClientErrors(page);
  const sockets: string[] = [];
  page.on("websocket", (socket) => sockets.push(socket.url()));
  await page.setViewportSize({ width: 1536, height: 1024 });
  await login(page);
  await useCiscoIdentityForCommandHelp(page);
  const dashboardMotionId = await page.locator(".device-miniature").first().getAttribute("data-motion-id");
  await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "IP topolojisi", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".front-panel")).toHaveAttribute("data-motion-id", dashboardMotionId!);
  await page.getByRole("button", { name: "1, Aktif", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "1 port detayları" }),
  ).toContainText("Ethernet1/1");
  await page.getByRole("button", { name: "Detayı kapat" }).click();
  // Capture a real, filtered MAC/IP relation at readable size; the complete
  // eleven-node graph and its pan/focus behavior are covered in device-detail.
  const graph = page.getByRole("region", { name: "Cihaz IP topolojisi", exact: true });
  await graph.getByLabel("Topolojide ara").fill("192.0.2.101");
  await expect(graph.locator(".node-hit")).toHaveCount(2);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: join(evidenceDir, "detail-desktop.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "SSH", exact: true }).click();
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  const connectedSocketCount = sockets.length;
  expect(connectedSocketCount).toBeGreaterThan(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const panel = await page.locator(".front-panel").boundingBox(),
    terminal = await page.locator(".ssh-workspace").boundingBox();
  expect(panel!.x + panel!.width).toBeLessThan(terminal!.x);
  expect(Math.abs(panel!.y - terminal!.y)).toBeLessThan(2);
  await page
    .locator(".xterm-helper-textarea")
    .pressSequentially("hello-browser");
  await page.locator(".xterm-helper-textarea").press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText(
    "TEST ECHO: hello-browser",
  );
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.locator(".xterm-screen").dblclick({ position: { x: 20, y: 8 } });
  await page
    .getByRole("button", { name: "Seçimi kopyala", exact: true })
    .click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "NetStudio",
  );
  await page.evaluate(() => navigator.clipboard.writeText("clipboard-browser"));
  await page.getByRole("button", { name: "Yapıştır", exact: true }).hover();
  await expect(
    page.getByRole("button", { name: "Yapıştır", exact: true }),
  ).toHaveCSS("background-color", "rgb(66, 71, 77)");
  await expect(
    page.getByRole("button", { name: "Yapıştır", exact: true }),
  ).toHaveCSS("color", "rgb(255, 255, 255)");
  await page.getByRole("button", { name: "Yapıştır", exact: true }).click();
  await page.locator(".xterm-helper-textarea").press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText(
    "TEST ECHO: clipboard-browser",
  );
  await page
    .getByRole("button", { name: "SSH görünümünü büyüt", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-ssh-transition", "expand");
  const expandedWorkspace = page.locator(
    ".device-workspace.ssh-view-expanded",
  );
  await expect(expandedWorkspace).toBeVisible();
  const expandedPanel = await expandedWorkspace.locator(".front-panel").boundingBox(),
    expandedTerminal = await expandedWorkspace.locator(".ssh-workspace").boundingBox(),
    expandedHelper = await expandedWorkspace.locator(".command-helper").boundingBox();
  expect(expandedPanel!.y + expandedPanel!.height).toBeLessThan(
    expandedTerminal!.y,
  );
  expect(expandedTerminal!.y + expandedTerminal!.height).toBeLessThan(
    expandedHelper!.y,
  );
  await expect(page.locator(".xterm-rows")).toContainText(
    "TEST ECHO: clipboard-browser",
  );
  await page
    .getByRole("button", { name: "SSH terminalini tam ekran yap", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-ssh-transition", "fullscreen");
  const fullscreenWorkspace = page.locator(
    ".device-workspace.ssh-view-fullscreen",
  );
  await expect(fullscreenWorkspace).toHaveCSS("position", "fixed");
  await expect(page.locator("html")).toHaveClass(/ssh-fullscreen-open/);
  const topbar = await page.locator(".topbar").boundingBox(),
    sidebar = await page.locator(".sidebar").boundingBox(),
    fullscreenBounds = await fullscreenWorkspace.boundingBox(),
    fullscreenTerminal = await fullscreenWorkspace
      .locator(".ssh-workspace")
      .boundingBox(),
    commandDrawer = fullscreenWorkspace.locator(".ssh-command-drawer"),
    fullscreenHelper = await commandDrawer
      .boundingBox();
  expect(fullscreenBounds).toEqual({
    x: sidebar!.width,
    y: topbar!.height,
    width: 1536 - sidebar!.width,
    height: 1024 - topbar!.height,
  });
  expect(fullscreenHelper!.x).toBe(fullscreenBounds!.x);
  expect(fullscreenHelper!.y).toBe(fullscreenBounds!.y);
  expect(fullscreenTerminal).toEqual({
    x: fullscreenBounds!.x + fullscreenHelper!.width,
    y: fullscreenBounds!.y,
    width: fullscreenBounds!.width - fullscreenHelper!.width,
    height: fullscreenBounds!.height,
  });
  await expect(page.locator(".topbar")).toBeVisible();
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(commandDrawer).toHaveCSS("transition-duration", "0.22s, 0s");
  await page
    .getByRole("region", { name: "Komut yardımcısı" })
    .getByRole("button", { name: "Kapat", exact: true })
    .click();
  await expect(commandDrawer).toHaveAttribute("aria-hidden", "true");
  await expect.poll(async () => (await commandDrawer.boundingBox())?.width).toBeLessThanOrEqual(1);
  await expect
    .poll(async () => (await fullscreenWorkspace.locator(".ssh-workspace").boundingBox())?.width)
    .toBeGreaterThanOrEqual(fullscreenBounds!.width - 1);
  await page
    .getByRole("button", { name: "Komut yardımcısını aç", exact: true })
    .click();
  await expect(commandDrawer).toHaveAttribute("aria-hidden", "false");
  await expect(commandDrawer).toHaveCSS("width", `${fullscreenHelper!.width}px`);
  await page.locator(".xterm-helper-textarea").pressSequentially("fullscreen-session");
  await page.locator(".xterm-helper-textarea").press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText(
    "TEST ECHO: fullscreen-session",
  );
  await page.screenshot({
    path: join(evidenceDir, "detail-ssh-fullscreen-desktop.png"),
    animations: "disabled",
  });
  await page.keyboard.press("Escape");
  await expect(page.locator("html")).toHaveAttribute("data-ssh-transition", "exit-fullscreen");
  await expect(expandedWorkspace).toBeVisible();
  await expect(page.locator("html")).not.toHaveClass(/ssh-fullscreen-open/);
  await page
    .getByRole("button", { name: "Standart SSH görünümüne dön", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-ssh-transition", "collapse");
  await page
    .getByRole("button", { name: "Komut yardımcısını kapat", exact: true })
    .click();
  await expect(page.locator(".front-panel")).toBeVisible();
  await page
    .getByRole("button", { name: "Komut yardımcısını aç", exact: true })
    .click();
  const helper = page.getByRole("region", { name: "Komut yardımcısı" });
  await expect(helper).toBeVisible();
  await expect(page.locator(".front-panel")).toHaveCount(0);
  await expect(helper).toContainText("Cisco IOS");
  await expect(helper).toContainText("show interfaces status");
  await helper
    .getByRole("button", {
      name: "show interfaces status komutunu kopyala",
      exact: true,
    })
    .click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    "show interfaces status",
  );
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: join(evidenceDir, "command-helper-desktop.png"),
    fullPage: true,
    animations: "disabled",
  });
  await helper.getByRole("button", { name: "Kapat", exact: true }).click();
  await expect(page.locator(".front-panel")).toBeVisible();
  await expect(page.locator(".xterm-rows")).toContainText(
    "TEST ECHO: fullscreen-session",
  );
  expect(sockets).toHaveLength(connectedSocketCount);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: join(evidenceDir, "detail-ssh-desktop.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 1200, height: 950 });
  await expect(page.locator(".xterm-rows")).toContainText("PTY");
  const terminalClosed = page.waitForResponse((response) =>
    response.url().includes("/api/v1/ssh-sessions/") && response.request().method() === "DELETE");
  await page.getByRole("button", { name: "Oturumu kapat" }).click();
  await expect(page.locator(".ssh-workspace")).toHaveCount(0);
  expect((await terminalClosed).ok()).toBe(true);
  await page.getByRole("button", { name: "SSH", exact: true }).click();
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  await page.getByRole("button", { name: "Çıkış", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Yönetim oturumu" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
    })),
  ).toEqual({ local: 0, session: 0 });
  expect(errors).toEqual([]);
});

test("mobile navigation, device and SSH stack without page overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(page.locator("[data-chart=echarts] svg")).toHaveCount(4);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: join(evidenceDir, "dashboard-mobile.png"),
    fullPage: true,
  });
  await useCiscoIdentityForCommandHelp(page);
  await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
  await page.getByRole("button", { name: "SSH", exact: true }).click();
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  const panel = await page.locator(".front-panel").boundingBox(),
    terminal = await page.locator(".ssh-workspace").boundingBox();
  expect(terminal!.y).toBeGreaterThan(panel!.y + panel!.height);
  await page
    .getByRole("button", { name: "SSH görünümünü büyüt", exact: true })
    .click();
  const expandedPanel = await page.locator(".front-panel").boundingBox(),
    expandedTerminal = await page.locator(".ssh-workspace").boundingBox();
  const helper = page.getByRole("region", { name: "Komut yardımcısı" });
  const expandedHelper = await helper.boundingBox();
  expect(expandedTerminal!.y).toBeGreaterThan(
    expandedPanel!.y + expandedPanel!.height,
  );
  expect(expandedHelper!.y).toBeGreaterThan(
    expandedTerminal!.y + expandedTerminal!.height,
  );
  await page
    .getByRole("button", { name: "SSH terminalini tam ekran yap", exact: true })
    .click();
  await expect(page.locator(".device-workspace.ssh-view-fullscreen")).toHaveCSS(
    "position",
    "fixed",
  );
  const mobilePopup = await page.locator(".ssh-command-drawer").boundingBox(),
    mobileTopbar = await page.locator(".topbar").boundingBox();
  expect(mobilePopup!.x).toBeGreaterThanOrEqual(0);
  expect(mobilePopup!.x + mobilePopup!.width).toBeLessThanOrEqual(390);
  await helper.getByRole("button", { name: "Kapat", exact: true }).click();
  await expect
    .poll(async () => (await page.locator(".ssh-command-drawer").boundingBox())?.width)
    .toBeLessThanOrEqual(1);
  const mobileFullscreen = await page.locator(".ssh-workspace").boundingBox();
  expect(mobileFullscreen!.width).toBeGreaterThanOrEqual(389);
  expect(mobileFullscreen!.x + mobileFullscreen!.width).toBe(390);
  expect(mobileFullscreen!.y).toBe(mobileTopbar!.height);
  expect(mobileFullscreen!.height).toBe(844 - mobileTopbar!.height);
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Standart SSH görünümüne dön", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Komut yardımcısını aç", exact: true })
    .click();
  await expect(helper).toContainText("Cisco IOS");
  const helperBox = await helper.boundingBox(),
    stackedTerminal = await page.locator(".ssh-workspace").boundingBox();
  expect(stackedTerminal!.y).toBeGreaterThan(helperBox!.y + helperBox!.height);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: join(evidenceDir, "command-helper-mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
  await helper.getByRole("button", { name: "Kapat", exact: true }).click();
  await page.screenshot({
    path: join(evidenceDir, "detail-ssh-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Oturumu kapat" }).click();
  await page.getByRole("button", { name: "Menü", exact: true }).click();
  await page.getByRole("link", { name: "İş geçmişi", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "İş geçmişi", exact: true }),
  ).toBeVisible();
});

test("device create and credential completion preserve secrets", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("button", { name: "Cihaz Ekle", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const name = `QA-created-${Date.now()}`;
  await dialog.getByLabel("Cihaz adı", { exact: true }).fill(name);
  await dialog
    .getByLabel("Yönetim IP adresi", { exact: true })
    // Inside the isolated QA CIDR; the missing key must block before network IO.
    .fill("172.31.255.200");
  await dialog
    .getByLabel("Site", { exact: true })
    .fill("TEST FIXTURE / isolated");
  await dialog.getByRole("button", { name: "Cihazı kaydet" }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await expect(
    page.getByText("Fiziksel port envanteri alınmadı."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Bağlantı bilgileri", exact: true })
    .click();
  await dialog.getByLabel("SSH kullanıcı adı", { exact: true }).fill("lab");
  await dialog.getByLabel("Cihaz parolası", { exact: true }).fill("lab-secret");
  await dialog
    .getByRole("button", { name: "Kimlik bilgilerini kaydet", exact: true })
    .click();
  await expect(
    dialog.getByText("Kimlik bilgileri şifrelenerek kaydedildi."),
  ).toBeVisible();
  await expect(
    dialog.getByLabel("Cihaz parolası", { exact: true }),
  ).toHaveValue("");
  await dialog.getByRole("button", { name: "Kapat", exact: true }).click();
  await page.getByRole("button", { name: "SSH", exact: true }).click();
  await expect(page.locator("p[role=alert]")).toContainText(
    "SSH host anahtarı henüz doğrulanmamış",
  );
});
