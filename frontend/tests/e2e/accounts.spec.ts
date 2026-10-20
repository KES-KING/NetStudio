import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

test.describe.configure({ mode: "serial" });
test.skip(!process.env.STOCC_QA, "Requires the isolated QA deployment, never production.");
const origin = process.env.PLAYWRIGHT_BASE_URL!;
const password = "qa-users-test-password-123";
const prefix = `qa-users-${Date.now()}`;
const evidence = join(tmpdir(), "stocc-netstudio-accounts");
const created: { id: string; username: string }[] = [];
const names = { superadmin: `${prefix}-admin`, engineer: `${prefix}-engineer`, viewer: `${prefix}-viewer` };

async function admin(request: APIRequestContext) {
  const response = await request.post("/api/v1/session/login", {
    headers: { origin }, data: { username: "qa-admin", password: "test-only-password-1234" },
  });
  expect(response.status(), "An unchanged disposable QA administrator is required").toBe(200);
  return { origin, "x-csrf-token": (await response.json()).csrf_token as string };
}
test.beforeAll(async ({ request }) => {
  expect(new URL(origin).hostname).toBe("127.0.0.1");
  const headers = await admin(request);
  const devices = await (await request.get("/api/v1/devices")).json();
  expect(devices.some((device: { name: string; site: string }) => device.name === "QA-Core-01" && device.site === "TEST FIXTURE / isolated")).toBeTruthy();
  // The disposable SSH container can rotate its key during an image rebuild.
  // Trust only the independently supplied key of this exact isolated fixture.
  const core = devices.find((device: { name: string }) => device.name === "QA-Core-01");
  const keyUrl = process.env.STOCC_QA_SSH_KEY_URL;
  if (keyUrl) {
    expect(new URL(keyUrl).hostname).toBe("127.0.0.1");
    const trustedLab = await (await request.get(keyUrl)).json();
    if (core.host_key_fingerprint !== trustedLab.fingerprint) {
      expect((await request.put(`/api/v1/devices/${core.id}/host-key`, { headers,
        data: { public_key: trustedLab.public_key, fingerprint: trustedLab.fingerprint, replace_existing: true },
      })).status()).toBe(200);
    }
  }
  for (const role of ["superadmin", "engineer", "viewer"] as const) {
    const response = await request.post("/api/v1/users", { headers, data: {
      username: names[role], display_name: `QA ${role}`, password, role, sites: role === "superadmin" ? ["*"] : ["TEST FIXTURE / isolated"],
    } });
    expect(response.ok()).toBeTruthy(); created.push(await response.json());
  }
  await request.post("/api/v1/session/logout", { headers });
  await mkdir(evidence, { recursive: true });
});
test.afterAll(async ({ request }) => {
  if (!created.length) return;
  const headers = await admin(request);
  // Delete only the disposable users created by this run; retain their audit history.
  for (const user of created) {
    const response = await request.delete(`/api/v1/users/${user.id}`, { headers, data: { confirmation_username: user.username } });
    expect([200, 404]).toContain(response.status());
  }
  await request.post("/api/v1/session/logout", { headers });
});

async function login(page: Page, username: string, secret = password) {
  await page.goto("/");
  await expect(page).toHaveTitle("Stocc NetStudio");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill(username);
  await page.getByLabel("Parola", { exact: true }).fill(secret);
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ağ cihazları", exact: true })).toBeVisible();
}
function observeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (!["warning", "error"].includes(message.type())) return;
    if (message.location().url.endsWith("/api/v1/session/me") && message.text().includes("401")) return;
    errors.push(`${message.type()}: ${message.text()}`);
  });
  return errors;
}
async function healthy(page: Page, width: number) {
  await expect(page).toHaveTitle("Stocc NetStudio");
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  expect(await page.locator("main").innerText()).not.toBe("");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

test("superadmin creates, edits, audits and deletes a user from the account workspace", async ({ page }) => {
  const errors = observeErrors(page);
  await page.setViewportSize({ width: 1536, height: 1080 });
  await login(page, names.superadmin);
  await page.locator(".topbar .account-link").click();
  await expect(page).toHaveURL(`${origin}/account`);
  await expect(page.getByRole("heading", { name: "Hesabım", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Kullanıcı oluştur", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const username = `${prefix}-created`;
  await dialog.getByLabel("Kullanıcı adı", { exact: true }).fill(username);
  await dialog.getByLabel("Görünen ad", { exact: true }).fill("QA Created User");
  await dialog.getByLabel("Parola", { exact: true }).fill(password);
  await dialog.getByLabel("Parola tekrar", { exact: true }).fill(password);
  const createResponse = page.waitForResponse((response) => response.url() === `${origin}/api/v1/users` && response.request().method() === "POST");
  await dialog.getByRole("button", { name: "Kaydet", exact: true }).click();
  const response = await createResponse;
  expect(response.status()).toBe(201);
  const user = await response.json(); created.push(user);
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: `${username} kullanıcısını düzenle`, exact: true }).click();
  await dialog.getByLabel("Görünen ad", { exact: true }).fill("QA Edited User");
  await dialog.getByRole("combobox", { name: "Yetki rolü", exact: true }).selectOption("engineer");
  await dialog.getByRole("button", { name: "Kaydet", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("QA Edited User", { exact: true })).toBeVisible();
  await healthy(page, 1536);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(evidence, "account-superadmin.png"), fullPage: true });

  await page.getByRole("link", { name: "Denetim kayıtları", exact: true }).click();
  await page.getByRole("combobox", { name: "Olay", exact: true }).selectOption("user.updated");
  await page.getByLabel("Hedef kimliği", { exact: true }).fill(user.id);
  await page.getByRole("button", { name: "Filtrele", exact: true }).click();
  await expect(page.locator(".audit-table tbody tr")).toHaveCount(1);
  await page.locator(".audit-table").getByRole("button", { name: /olay ayrıntıları/ }).click();
  await expect(page.getByRole("region", { name: "Olay ayrıntıları" })).toContainText("QA Edited User");
  await expect(page.locator(".audit-json")).toContainText('"before"');
  await expect(page.locator(".audit-json")).not.toContainText(password);
  await healthy(page, 1536);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(evidence, "audit-superadmin.png"), fullPage: true });

  await page.locator(".sidebar-account-link").click();
  await page.getByRole("button", { name: `${username} kullanıcısını sil`, exact: true }).click();
  await dialog.getByLabel("Onay için kullanıcı adı", { exact: true }).fill(username);
  await dialog.getByRole("button", { name: "Kullanıcıyı sil", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("Kullanıcı silindi. Denetim geçmişi korundu.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Çıkış", exact: true }).click();
  expect(errors).toEqual([]);
});

test("viewer edits own profile, persists an avatar and changes password without admin access", async ({ page }) => {
  const errors = observeErrors(page);
  await page.setViewportSize({ width: 1536, height: 1080 });
  await login(page, names.viewer);
  await expect(page.getByRole("link", { name: "Denetim kayıtları", exact: true })).toHaveCount(0);
  await page.locator(".topbar .account-link").click();
  await expect(page.locator(".user-directory")).toHaveCount(0);
  await page.getByLabel("Görünen ad", { exact: true }).fill("QA Personal Profile");
  await page.getByRole("button", { name: "Profili kaydet", exact: true }).click();
  await expect(page.locator(".topbar .account-link")).toContainText("QA Personal Profile");
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = canvas.height = 32;
    const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#365a73"; ctx.fillRect(0, 0, 32, 32);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.getByLabel("Avatar görseli", { exact: true }).setInputFiles({ name: "qa-avatar.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await page.getByRole("button", { name: "Avatarı yükle", exact: true }).click();
  await expect(page.locator(".topbar .user-avatar img")).toBeVisible();
  await page.reload();
  await expect(page.locator(".topbar .user-avatar img")).toBeVisible();
  // Visibility precedes decoding of the authenticated image after reload.
  await expect.poll(() => page.locator(".topbar .user-avatar img").evaluate(
    (image) => (image as HTMLImageElement).naturalWidth)).toBe(32);
  await page.getByRole("button", { name: "Avatarı kaldır", exact: true }).click();
  await expect(page.locator(".topbar .user-avatar img")).toHaveCount(0);
  await page.getByLabel("Mevcut parola", { exact: true }).fill(password);
  await page.getByLabel("Yeni parola", { exact: true }).fill(`${password}-changed`);
  await page.getByLabel("Yeni parola tekrar", { exact: true }).fill(`${password}-changed`);
  await page.getByRole("button", { name: "Parolayı değiştir", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Yönetim oturumu", exact: true })).toBeVisible();
  await login(page, names.viewer, `${password}-changed`);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
  await page.getByRole("button", { name: "Çıkış", exact: true }).click();
  expect(errors).toEqual([]);
});

test("mobile engineer account navigation and audit protection", async ({ page }) => {
  const errors = observeErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, names.engineer);
  await page.getByRole("button", { name: "Menü", exact: true }).click();
  await page.locator(".sidebar-account-link").click();
  await expect(page.getByRole("heading", { name: "Hesabım", exact: true })).toBeVisible();
  await expect(page.locator(".sidebar")).toBeHidden();
  await expect(page.locator(".user-directory")).toHaveCount(0);
  await healthy(page, 390);
  await page.screenshot({ path: join(evidence, "account-engineer-mobile.png"), fullPage: true });
  await page.goto(`${origin}/audit`);
  await expect(page.getByText("Bu sayfayı yalnız superadmin görüntüleyebilir.", { exact: true })).toBeVisible();
  expect((await page.request.get(`${origin}/api/v1/audit`)).status()).toBe(403);
  expect((await page.request.get(`${origin}/api/v1/users`)).status()).toBe(403);
  await page.getByRole("button", { name: "Çıkış", exact: true }).click();
  expect(errors).toEqual([]);
});

test("superadmin role change revokes an engineer's live SSH connection", async ({ page, request }) => {
  await page.setViewportSize({ width: 1536, height: 1080 });
  await login(page, names.engineer);
  await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
  await page.getByRole("button", { name: "SSH", exact: true }).click();
  await expect(page.getByText("Bağlandı", { exact: true })).toBeVisible({ timeout: 20000 });
  const headers = await admin(request);
  const engineer = created.find((user) => user.username === names.engineer)!;
  expect((await request.patch(`/api/v1/users/${engineer.id}`, { headers, data: { role: "viewer" } })).status()).toBe(200);
  await expect(page.getByText("Oturum veya yetki geçersiz", { exact: true })).toBeVisible({ timeout: 5000 });
  expect((await page.request.get(`${origin}/api/v1/session/me`)).status()).toBe(401);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Yönetim oturumu", exact: true })).toBeVisible();
  await request.post("/api/v1/session/logout", { headers });
});
