import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

test.describe.configure({ mode: "serial" });
test.skip(
  !process.env.NETSTUDIO_QA,
  "Requires an isolated seeded QA Docker project, never production.",
);

const origin = process.env.PLAYWRIGHT_BASE_URL!;
const password = "qa-compatibility-password-123";
const suffix = Date.now();
const viewer = `qa-compat-viewer-${suffix}`;
const legacyName = `QA-Legacy-Huawei-${suffix}`;
let viewerId = "";
let legacyDeviceId = "";

async function adminHeaders(request: APIRequestContext) {
  expect(new URL(origin).hostname).toBe("127.0.0.1");
  const response = await request.post("/api/v1/session/login", {
    headers: { origin },
    data: { username: "qa-admin", password: "test-only-password-1234" },
  });
  expect(response.status()).toBe(200);
  return {
    origin,
    "x-csrf-token": (await response.json()).csrf_token as string,
  };
}

test.beforeAll(async ({ request }) => {
  const headers = await adminHeaders(request);
  const userResponse = await request.post("/api/v1/users", {
    headers,
    data: {
      username: viewer,
      display_name: "QA Compatibility Viewer",
      password,
      role: "viewer",
      sites: ["TEST FIXTURE / isolated"],
    },
  });
  expect(userResponse.status()).toBe(201);
  viewerId = (await userResponse.json()).id;

  // This record deliberately enters through the legacy alias so the UI must
  // require an explicit canonical profile choice instead of silently relabeling it.
  const deviceResponse = await request.post("/api/v1/devices", {
    headers,
    data: {
      name: legacyName,
      management_address: "192.0.2.240",
      site: "TEST FIXTURE / isolated",
      vendor: "Huawei",
      model: "S5700-LONG-COMPATIBILITY-LABEL-FIXTURE",
      collector: "huawei_vrp",
    },
  });
  expect(deviceResponse.status()).toBe(201);
  legacyDeviceId = (await deviceResponse.json()).id;
  await request.post("/api/v1/session/logout", { headers });
});

test.afterAll(async ({ request }) => {
  if (!viewerId) return;
  const headers = await adminHeaders(request);
  const response = await request.delete(`/api/v1/users/${viewerId}`, {
    headers,
    data: { confirmation_username: viewer },
  });
  expect([200, 404]).toContain(response.status());
  await request.post("/api/v1/session/logout", { headers });
});

function observeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (!["warning", "error"].includes(message.type())) return;
    if (
      message.location().url.endsWith("/api/v1/session/me") &&
      message.text().includes("401")
    )
      return;
    errors.push(`${message.type()}: ${message.text()}`);
  });
  return errors;
}

async function login(page: Page, username: string, secret: string) {
  await page.goto("/");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill(username);
  await page.getByLabel("Parola", { exact: true }).fill(secret);
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ağ cihazları", exact: true }),
  ).toBeVisible();
}

async function expectNoHorizontalOverflow(page: Page, width: number) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    width,
  );
}

test("catalog-driven add form exposes supported, experimental, planned and unsupported states", async ({
  page,
}) => {
  const errors = observeErrors(page);
  await page.setViewportSize({ width: 390, height: 520 });
  await page.emulateMedia({ reducedMotion: "reduce" });

  await login(page, "qa-admin", "test-only-password-1234");
  // UI-contract fixture only: a catalog release label must still avoid claiming
  // physical or production acceptance for an individual device. Fetch through
  // the authenticated browser context first; do not recurse from a route handler.
  const catalogResponse = await page.request.get("/api/v1/driver-catalog");
  expect(catalogResponse.ok()).toBeTruthy();
  const catalog = await catalogResponse.json();
  const ios = catalog.profiles.find((profile: { id: string }) => profile.id === "cisco_ios");
  ios.release_status = "supported";
  await page.route("**/api/v1/driver-catalog", (route) =>
    route.fulfill({ json: catalog }),
  );

  await page.getByRole("button", { name: "Cihaz Ekle", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Cihaz adı", { exact: true })).toBeFocused();

  const vendor = dialog.locator('select[name="catalog_vendor"]');
  const profile = dialog.locator('select[name="configured_profile_id"]');
  await expect(vendor).toBeEnabled();
  await vendor.selectOption({ value: "Cisco" });
  await expect(profile.locator("option[value=cisco_business]")).toHaveAttribute("disabled", "");
  await profile.selectOption("cisco_ios");
  await expect(dialog.getByText("Katalogda desteklenen profil · cihaz kapsamı ayrıca doğrulanır", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Fixture doğrulandı · fiziksel kabul değil", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("radio", { name: /SSH/ })).toBeEnabled();
  await expect(dialog.getByRole("radio", { name: /SNMPv3/ })).toBeEnabled();
  await expect(dialog.getByLabel("Cihaz parolası", { exact: true })).toHaveValue("");
  await dialog.locator('select[name="method"]').selectOption("private_key");
  await expect(dialog.getByLabel("Özel anahtar", { exact: true })).toHaveValue("");

  await vendor.selectOption({ value: "HPE Aruba Networking" });
  await expect(profile.locator("option[value=aruba_aoscx]")).toBeEnabled();
  await expect(profile.locator("option[value=aruba_aoss]")).toBeEnabled();
  await expect(profile.locator("option[value=hpe_comware]")).toBeEnabled();
  await vendor.selectOption({ value: "H3C" });
  await expect(profile.locator("option[value=h3c_comware7]")).toBeEnabled();
  await expect(profile.locator("option[value=h3c_comware5]")).toHaveAttribute("disabled", "");
  await expect(profile.locator("option[value=h3c_comware9]")).toHaveAttribute("disabled", "");

  await vendor.selectOption({ value: "TP-Link" });
  await expect(profile.locator("option[value=tplink_omada_managed]")).toHaveAttribute("disabled", "");
  await expect(profile.locator("option[value=tplink_easy_smart]")).toHaveAttribute("disabled", "");
  await expect(dialog.getByText(/henüz seçilemeyen profiller/)).toBeVisible();

  await dialog.getByRole("button", { name: "Cihazı kaydet", exact: true }).click();
  const error = dialog.getByRole("alert").last();
  await expect(error).toContainText("Zorunlu alanları");
  await expect(error).toBeFocused();
  await expectNoHorizontalOverflow(page, 390);
  expect(await dialog.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("legacy profile migration requires confirmation and viewer sees read-only evidence", async ({
  page,
}) => {
  const errors = observeErrors(page);
  await page.setViewportSize({ width: 1536, height: 900 });
  await login(page, "qa-admin", "test-only-password-1234");
  await page.goto(`/devices/${legacyDeviceId}`);
  const panel = page.getByRole("region", { name: "Uyumluluk" });
  await expect(panel).toContainText("Legacy veya belirsiz cihaz kimliği sessizce yeniden sınıflandırılmadı");
  await expect(panel.getByText("Production kabulü: Yok", { exact: true })).toBeVisible();
  await expect(panel).not.toContainText("Destekleniyor · fiziksel kapsam eşleşti");

  const editor = panel.locator(".compatibility-profile-editor");
  await expect(editor).toHaveAttribute("open", "");
  await expect(editor.locator('select[name="configured_profile_id"]')).toHaveValue("huawei_vrp_v200");
  await editor.getByLabel(/Bu seçimin legacy sınıflandırmayı/).check();
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/devices/${legacyDeviceId}/driver-profile`) &&
      response.request().method() === "PUT",
  );
  await editor.getByRole("button", { name: "Kanonik profili kaydet", exact: true }).click();
  expect((await saved).status()).toBe(200);
  await expect(panel.getByRole("definition").filter({ hasText: /^Bağımsız yönetim$/ })).toBeVisible();
  await expectNoHorizontalOverflow(page, 1536);

  await page.getByRole("button", { name: "Çıkış", exact: true }).click();
  await login(page, viewer, password);
  await page.setViewportSize({ width: 390, height: 520 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/devices/${legacyDeviceId}`);
  const viewerPanel = page.getByRole("region", { name: "Uyumluluk" });
  await expect(viewerPanel.getByText("Production kabulü: Yok", { exact: true })).toBeVisible();
  await expect(viewerPanel.locator(".compatibility-profile-editor")).toHaveCount(0);
  await expectNoHorizontalOverflow(page, 390);
  expect(errors).toEqual([]);
});
