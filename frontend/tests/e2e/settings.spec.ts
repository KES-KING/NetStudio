import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

test.skip(!process.env.STOCC_QA, "Only the isolated QA installation.");
const evidence = join(tmpdir(), "stocc-netstudio-settings");

async function login(page: Page) {
  expect(new URL(process.env.PLAYWRIGHT_BASE_URL!).hostname).toBe("127.0.0.1");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (message.location().url.endsWith("/api/v1/session/me") && message.text().includes("401")) return;
    errors.push(message.text());
  });
  await page.goto("/");
  await expect(page).toHaveTitle("Stocc NetStudio");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ağ cihazları", exact: true })).toBeVisible();
  await mkdir(evidence, { recursive: true });
  return errors;
}

async function healthy(page: Page, width: number) {
  await expect(page).toHaveTitle("Stocc NetStudio");
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  expect((await page.locator("main").innerText()).length).toBeGreaterThan(40);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

test("settings account and live server notifications persist read state", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  const errors = await login(page);
  await page.getByRole("navigation", { name: "Ana navigasyon" }).getByRole("link", { name: "Ayarlar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ayarlar", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Profilim", exact: true })).toBeVisible();
  await page.screenshot({ path: join(evidence, "settings-desktop.png"), fullPage: true, animations: "disabled" });
  const bell = page.getByRole("button", { name: /^Bildirimler(?: \(|$)/ });
  await bell.click();
  const panel = page.getByRole("region", { name: "Canlı bildirimler" });
  await expect(panel.getByText("Canlı · sunucu olayları", { exact: true })).toBeVisible();
  const oldId = (await page.request.get("/api/v1/notifications").then((r) => r.json())).latest_id;
  await page.keyboard.press("Escape");
  await expect(bell).toBeFocused();
  // Save the same profile: a real authenticated server event, no fixture SSE.
  await page.getByRole("button", { name: "Profili kaydet", exact: true }).click();
  await expect(page.getByText("Profiliniz güncellendi.", { exact: true })).toBeVisible();
  await bell.click();
  await expect.poll(async () => (await page.request.get("/api/v1/notifications").then((r) => r.json())).latest_id).not.toBe(oldId);
  await expect(panel.locator(".notification-item").first()).toContainText("Profil güncellendi", { timeout: 10000 });
  await panel.getByRole("button", { name: "Okundu olarak işaretle" }).click();
  await expect(bell).toHaveAccessibleName("Bildirimler", { timeout: 10000 });
  await page.screenshot({ path: join(evidence, "notifications-desktop.png"), animations: "disabled" });
  await page.keyboard.press("Escape");
  await page.reload();
  await bell.click();
  await expect(panel.locator(".notification-item").first()).toContainText("Profil güncellendi");
  await expect(panel.locator(".notification-item.unread")).toHaveCount(0);
  await page.getByRole("heading", { name: "Ayarlar", exact: true }).click();
  await expect(panel).toBeHidden();
  await page.getByRole("navigation", { name: "Ayarlar bölümleri" }).getByRole("link", { name: /Kullanıcılar/ }).click();
  await expect(page.getByRole("button", { name: "Kullanıcı oluştur", exact: true })).toBeVisible();
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Hesabım", exact: true })).toBeVisible();
  await healthy(page, 1536);
  expect(errors).toEqual([]);
});

for (const width of [390, 320]) test(`updates and live notification accordion fit ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const errors = await login(page);
  await page.getByRole("button", { name: "Menü", exact: true }).click();
  await page.getByRole("navigation", { name: "Ana navigasyon" }).getByRole("link", { name: "Ayarlar", exact: true }).click();
  await page.getByRole("navigation", { name: "Ayarlar bölümleri" }).getByRole("link", { name: /Güncellemeler/ }).click();
  await expect(page.getByRole("heading", { name: "Güncelleme sistemi", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Güncellemeyi kur", exact: true })).toBeDisabled();
  await healthy(page, width);
  await page.screenshot({ path: join(evidence, `updates-${width}.png`), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: /^Bildirimler(?: \(|$)/ }).click();
  const panel = page.getByRole("region", { name: "Canlı bildirimler" });
  await expect(panel.getByText("Canlı · sunucu olayları", { exact: true })).toBeVisible();
  await expect(page.locator(".notification-dropdown")).toHaveCSS("transition-duration", "0s");
  const bounds = (await panel.boundingBox())!;
  expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
  await page.screenshot({ path: join(evidence, `notifications-${width}.png`), animations: "disabled" });
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  expect(errors).toEqual([]);
});

test("commit UI fixture exposes safe GitHub links, descriptions and left update alert", async ({ page }) => {
  // UI contract fixture only: no host update is requested or deployed.
  const sha = "b".repeat(40), url = `https://github.com/KES-KING/NetStudio/commit/${sha}`;
  await page.route("**/api/v1/system/updates", (route) => route.fulfill({ json: {
    repository: "KES-KING/NetStudio", repository_url: "https://github.com/KES-KING/NetStudio", branch: "main",
    installed_revision: "a".repeat(40), latest_revision: sha, available: true, automatic: false,
    agent_online: false, can_manage: true, maintenance: false, recovery_required: false,
    checked_at: new Date().toISOString(), next_check_at: null, error_code: null, runs: [],
    commits: [{ sha, title: "QA: ayarlar ve bildirimler", description: "Detaylı açıklama <script>invalid()</script>",
      author: "QA fixture", committed_at: new Date().toISOString(), url }],
  } }));
  await page.route("**/api/v1/notifications/stream", (route) => route.fulfill({ contentType: "text/event-stream", body:
    `event: notifications\ndata: ${JSON.stringify({ items: [], unread_count: 0, latest_id: null, update_available: true, maintenance: false })}\n\n` }));
  await page.setViewportSize({ width: 1536, height: 1024 });
  const errors = await login(page);
  const update = page.locator(".topbar-context .topbar-update");
  await expect(update).toHaveAttribute("href", "/settings/updates");
  await update.click();
  await expect(page).toHaveURL(/\/settings\/updates$/);
  const commit = page.getByRole("link", { name: "QA: ayarlar ve bildirimler ↗", exact: true });
  await expect(commit).toHaveAttribute("href", url);
  await expect(commit).toHaveAttribute("rel", "noopener noreferrer");
  await page.getByText("Commit açıklaması", { exact: true }).click();
  await expect(page.locator(".commit-description")).toHaveText("Detaylı açıklama <script>invalid()</script>");
  await expect(page.locator(".commit-description script")).toHaveCount(0);
  await page.screenshot({ path: join(evidence, "updates-fixture-desktop.png"), fullPage: true, animations: "disabled" });
  for (const width of [390, 320, 768, 1536]) {
    await page.setViewportSize({ width, height: 844 });
    await healthy(page, width);
    await expect(update).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("opt-in public GitHub check renders real commits without starting installation", async ({ page }) => {
  test.skip(process.env.STOCC_LIVE_GITHUB !== "1", "Requires explicit read-only public GitHub access.");
  await page.setViewportSize({ width: 1536, height: 1024 });
  const errors = await login(page);
  await page.goto("/settings/updates");
  const result = page.waitForResponse((response) => response.url().endsWith("/api/v1/system/updates/check"));
  await page.getByRole("button", { name: "Güncellemeleri kontrol et", exact: true }).click();
  const response = await result;
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  expect(data.error_code).toBeNull();
  expect(data.commits.length).toBeGreaterThan(0);
  expect(data.installed_revision).toBeNull(); // QA is intentionally an unversioned worktree build.
  expect(data.automatic).toBe(false);
  expect(data.agent_online).toBe(false);
  const first = page.locator(".commit-heading a").first();
  await expect(first).toHaveAttribute("href", `https://github.com/KES-KING/NetStudio/commit/${data.latest_revision}`);
  await expect(page.getByRole("button", { name: "Güncellemeyi kur", exact: true })).toBeDisabled();
  await healthy(page, 1536);
  await page.screenshot({ path: join(evidence, "updates-live-desktop.png"), animations: "disabled" });
  expect(errors).toEqual([]);
});
