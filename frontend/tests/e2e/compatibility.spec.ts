import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test.describe.configure({ mode: "serial" });
test.skip(
  !process.env.NETSTUDIO_QA,
  "Requires an isolated seeded QA Docker project, never production.",
);

const origin = process.env.PLAYWRIGHT_BASE_URL!;
const password = "qa-compatibility-password-123";
const suffix = Date.now();
const evidenceDir = join(tmpdir(), "netstudio-qa");
const viewer = `qa-compat-viewer-${suffix}`;
const legacyName = `QA-Legacy-Huawei-${suffix}`;
const controllerDeviceName = `QA-Meraki-Controller-${suffix}`;
const swosDeviceName = `QA-MikroTik-SwOS-${suffix}`;
let viewerId = "";
let legacyDeviceId = "";
let controllerDeviceId = "";
let swosDeviceId = "";
let controllerId = "";

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
  mkdirSync(evidenceDir, { recursive: true });
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

  const controllerDeviceResponse = await request.post("/api/v1/devices", {
    headers,
    data: {
      name: controllerDeviceName,
      management_address: "192.0.2.241",
      site: "TEST FIXTURE / isolated",
      vendor: "Cisco Meraki",
      model: "MS225-24P",
      configured_profile_id: "cisco_meraki_ms",
      management_mode: "cloud_managed",
    },
  });
  expect(controllerDeviceResponse.status()).toBe(201);
  controllerDeviceId = (await controllerDeviceResponse.json()).id;

  const swosDeviceResponse = await request.post("/api/v1/devices", {
    headers,
    data: {
      name: swosDeviceName,
      management_address: "192.0.2.242",
      site: "TEST FIXTURE / isolated",
      vendor: "MikroTik",
      model: "CSS610-8G-2S+",
      configured_profile_id: "mikrotik_swos",
      management_mode: "standalone",
    },
  });
  expect(swosDeviceResponse.status()).toBe(201);
  swosDeviceId = (await swosDeviceResponse.json()).id;
  await request.post("/api/v1/session/logout", { headers });
});

test.afterAll(async ({ request }) => {
  const headers = await adminHeaders(request);
  if (controllerDeviceId)
    await request.delete(`/api/v1/devices/${controllerDeviceId}/controller-binding`, { headers });
  if (controllerId) {
    const response = await request.delete(`/api/v1/controllers/${controllerId}`, { headers });
    expect([200, 404]).toContain(response.status());
  }
  if (viewerId) {
    const response = await request.delete(`/api/v1/users/${viewerId}`, {
      headers,
      data: { confirmation_username: viewer },
    });
    expect([200, 404]).toContain(response.status());
  }
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
  await expect(profile.locator("option[value=cisco_business]")).toBeEnabled();
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
  await expect(profile.locator("option[value=h3c_comware5]")).toBeEnabled();
  await expect(profile.locator("option[value=h3c_comware9]")).toBeEnabled();

  await vendor.selectOption({ value: "Huawei" });
  await expect(profile.locator("option[value=huawei_vrp_v600]")).toBeEnabled();
  await vendor.selectOption({ value: "Juniper" });
  await expect(profile.locator("option[value=juniper_junos_evolved]")).toBeEnabled();

  await vendor.selectOption({ value: "Dell Technologies" });
  await expect(profile.locator("option[value=dell_os10]")).toBeEnabled();
  await expect(profile.locator("option[value=dell_os9]")).toBeEnabled();
  await expect(profile.locator("option[value=dell_os6]")).toBeEnabled();
  await expect(profile.locator("option[value=dell_sonic]")).toBeEnabled();
  await vendor.selectOption({ value: "NVIDIA Networking" });
  await expect(profile.locator("option[value=nvidia_cumulus_linux]")).toBeEnabled();
  await expect(profile.locator("option[value=nvidia_onyx]")).toBeEnabled();
  await vendor.selectOption({ value: "Unknown" });
  await expect(profile.locator("option[value=sonic_nos]")).toBeEnabled();
  await vendor.selectOption({ value: "Extreme Networks" });
  await expect(profile.locator("option[value=extreme_exos]")).toBeEnabled();
  await expect(profile.locator("option[value=extreme_fabric_engine]")).toBeEnabled();
  await expect(profile.locator("option[value=extreme_slxos]")).toBeEnabled();
  await vendor.selectOption({ value: "Fortinet" });
  await expect(profile.locator("option[value=fortinet_fortiswitchos]")).toBeEnabled();
  await expect(
    profile.locator("option[value=fortinet_fortiswitch_fortilink]"),
  ).toBeEnabled();

  await vendor.selectOption({ value: "TP-Link" });
  await expect(profile.locator("option[value=tplink_omada_managed]")).toBeEnabled();
  await expect(profile.locator("option[value=tplink_omada_pro]")).toBeEnabled();
  await expect(profile.locator("option[value=tplink_easy_smart]")).toHaveAttribute("disabled", "");
  await vendor.selectOption({ value: "MikroTik" });
  await expect(profile.locator("option[value=mikrotik_swos]")).toBeEnabled();
  await profile.selectOption("mikrotik_swos");
  await expect(dialog.getByRole("radio", { name: /SNMPv2c/ })).toBeEnabled();
  await expect(dialog.getByText(/superadmin SNMPv2c riskini/)).toBeVisible();
  await vendor.selectOption({ value: "Cisco Meraki" });
  await profile.selectOption("cisco_meraki_ms");
  await expect(dialog.getByRole("radio", { name: /Üretici \/ controller API/ })).toBeEnabled();
  await vendor.selectOption({ value: "HPE Aruba Networking" });
  await expect(profile.locator("option[value=aruba_instant_on]")).toHaveAttribute("disabled", "");
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

test("signed release scope is visible without exposing controlled evidence", async ({
  page,
}) => {
  const errors = observeErrors(page);
  await page.setViewportSize({ width: 1536, height: 900 });
  await login(page, "qa-admin", "test-only-password-1234");

  const catalogResponse = await page.request.get("/api/v1/driver-catalog");
  const compatibilityResponse = await page.request.get(
    `/api/v1/devices/${swosDeviceId}/compatibility`,
  );
  expect(catalogResponse.ok()).toBeTruthy();
  expect(compatibilityResponse.ok()).toBeTruthy();
  const catalog = await catalogResponse.json();
  const compatibility = await compatibilityResponse.json();
  const swos = catalog.profiles.find(
    (candidate: { id: string }) => candidate.id === "mikrotik_swos",
  );
  swos.release_status = "supported";
  compatibility.release_status = "supported";
  compatibility.verification_status = "physical_validated";
  compatibility.acceptance = {
    highest_level: "physical_validated",
    matching_unexpired_records: 5,
    production_accepted: false,
  };
  compatibility.release_decision = {
    decision_id: "decision-s11-browser-fixture",
    payload_sha256: "a".repeat(64),
    signer_key_id: "release-browser-fixture",
    signed_at: "2026-10-24T09:00:00Z",
    expires_at: "2027-01-22T09:00:00Z",
    accepted_vendor: "MikroTik",
    accepted_model_family: "CSS610-*",
    accepted_exact_model: "CSS610-8G-2S+",
    accepted_hardware_revision: "r2",
    accepted_os_family: "SwOS",
    accepted_os_version: "2.18",
    accepted_management_mode: "standalone",
    accepted_transport: "snmp",
    accepted_security_profile: "snmpv2c_read_only_acl_isolated",
    benchmark_status: "pass",
    rollout_stage: "general",
    blocked_reasons: [],
    production_accepted: false,
  };
  await page.route("**/api/v1/driver-catalog", (route) =>
    route.fulfill({ json: catalog }),
  );
  await page.route(
    `**/api/v1/devices/${swosDeviceId}/compatibility`,
    (route) => route.fulfill({ json: compatibility }),
  );

  await page.goto(`/devices/${swosDeviceId}`);
  const panel = page.getByRole("region", { name: "Uyumluluk" });
  await expect(
    panel.getByText("Destekleniyor · fiziksel kapsam eşleşti", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByText("Production kabulü: Yok", { exact: true })).toBeVisible();
  await panel.getByText("İmzalı yayın kararı", { exact: true }).click();
  await expect(
    panel.getByText("Kapsam: MikroTik · CSS610-8G-2S+ · donanım r2", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByText("OS: SwOS · 2.18", { exact: true })).toBeVisible();
  await expect(
    panel.getByText("Yönetim/transport: Bağımsız yönetim · SNMP", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByText("Rollout: general", { exact: true })).toBeVisible();
  await expect(panel.getByText(`SHA-256: ${"a".repeat(64)}`, { exact: true })).toBeVisible();
  await expect(panel).not.toContainText("CONTROLLED");
  await expectNoHorizontalOverflow(page, 1536);
  await page.screenshot({
    path: join(evidenceDir, "s11-release-decision-desktop.png"),
    fullPage: false,
    animations: "disabled",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page, 390);
  await expect(panel.getByText("İmzalı yayın kararı", { exact: true })).toBeVisible();
  await panel.locator(".compatibility-release").screenshot({
    path: join(evidenceDir, "s11-release-decision-mobile.png"),
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});

test("SwOS SNMPv2c risk approval is explicit, redacted and revocable", async ({
  page,
}) => {
  const errors = observeErrors(page);
  await page.setViewportSize({ width: 1536, height: 900 });
  await login(page, "qa-admin", "test-only-password-1234");
  await page.goto(`/devices/${swosDeviceId}`);
  await expect(page.getByRole("heading", { name: swosDeviceName, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Bağlantı bilgileri", exact: true }).click();

  const dialog = page.getByRole("dialog");
  await dialog.getByText(/SNMPv2c · şifrelenmemiş uyumluluk istisnası/).click();
  await expect(dialog.getByText(/SNMPv2c kimlik doğrulama ve şifreleme sağlamaz/)).toBeVisible();
  await dialog.getByLabel("SNMP community", { exact: true }).fill("test-only-browser-community");
  await dialog.getByLabel(/yalnız GET, GETNEXT ve GETBULK/).check();
  await dialog.getByLabel(/Cihaz ACL’si/).check();
  await dialog.getByLabel(/ayrılmış yönetim VLAN\/VRF/).check();
  await dialog.getByLabel(/ağda şifrelenmediğini/).check();
  const saved = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/devices/${swosDeviceId}/snmp-v2c-credentials`) &&
    response.request().method() === "PUT",
  );
  await dialog.getByRole("button", { name: "SNMPv2c riskini onayla ve kaydet", exact: true }).click();
  const savedResponse = await saved;
  expect(savedResponse.status()).toBe(200);
  expect(await savedResponse.text()).not.toContain("test-only-browser-community");
  await expect(dialog.getByRole("status")).toContainText("risk onayı");
  await expect(dialog.getByLabel("SNMP community", { exact: true })).toHaveValue("");
  await expect(dialog.getByRole("button", { name: "SNMPv2c onayını ve community kaydını kaldır", exact: true })).toBeVisible();
  await page.screenshot({
    path: join(evidenceDir, "s10-snmpv2c-desktop.png"),
    fullPage: false,
    animations: "disabled",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page, 390);
  const bounds = await dialog.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: join(evidenceDir, "s10-snmpv2c-mobile.png"),
    fullPage: false,
    animations: "disabled",
  });

  const catalogResponse = await page.request.get("/api/v1/driver-catalog");
  expect(catalogResponse.ok()).toBeTruthy();
  const disabledCatalog = await catalogResponse.json();
  disabledCatalog.features.snmp_v2c_enabled = false;
  const disabledSwos = disabledCatalog.profiles.find(
    (candidate: { id: string }) => candidate.id === "mikrotik_swos",
  );
  disabledSwos.available = false;
  disabledSwos.selectable = false;
  disabledSwos.availability_reason = "snmp_v2c_installation_disabled";
  disabledSwos.transports.snmp.state = "unsupported_by_policy";
  await page.route("**/api/v1/driver-catalog", (route) =>
    route.fulfill({ json: disabledCatalog }),
  );
  await page.reload();
  await page.getByRole("button", { name: "Bağlantı bilgileri", exact: true }).click();
  const disabledDialog = page.getByRole("dialog");
  await disabledDialog.getByText(/SNMPv2c · şifrelenmemiş uyumluluk istisnası/).click();
  await expect(disabledDialog.getByText(/Kurulum genelinde SNMPv2c kapalıdır/)).toBeVisible();
  await expect(disabledDialog.getByLabel("SNMP community", { exact: true })).toHaveCount(0);
  await expect(disabledDialog.getByRole("button", { name: "SNMPv2c onayını ve community kaydını kaldır", exact: true })).toBeVisible();

  const removed = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/devices/${swosDeviceId}/snmp-credentials`) &&
    response.request().method() === "DELETE",
  );
  await disabledDialog.getByRole("button", { name: "SNMPv2c onayını ve community kaydını kaldır", exact: true }).click();
  expect((await removed).status()).toBe(200);
  await expect(disabledDialog.getByRole("status")).toContainText("kaldırıldı");
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("controller API settings create a redacted credential and bind the device", async ({
  page,
}) => {
  const errors = observeErrors(page);
  await page.setViewportSize({ width: 1536, height: 900 });
  await login(page, "qa-admin", "test-only-password-1234");
  await page.goto(`/devices/${controllerDeviceId}`);
  await expect(page).toHaveTitle("NetStudio");
  await expect(page.getByRole("heading", { name: controllerDeviceName, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Bağlantı bilgileri", exact: true }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("API yönetimi SSH’den ayrıdır");
  await dialog.getByLabel("Kayıt adı", { exact: true }).fill(`QA Meraki ${suffix}`);
  await dialog.getByLabel("Organization ID", { exact: true }).fill("org-test");
  await dialog.getByLabel("Controller site / network ID", { exact: true }).fill("N_test");
  const created = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/controllers") && response.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Controller kaydını oluştur", exact: true }).click();
  const createdResponse = await created;
  expect(createdResponse.status()).toBe(201);
  controllerId = (await createdResponse.json()).id;
  await expect(dialog.getByRole("status")).toContainText("Controller kaydı oluşturuldu");

  await dialog.getByLabel("Bearer erişim tokenı", { exact: true }).fill("test-only-meraki-bearer-token-12345");
  const credentialSaved = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/controllers/${controllerId}/credentials`) &&
    response.request().method() === "PUT",
  );
  await dialog.getByRole("button", { name: "API erişimini kaydet", exact: true }).click();
  expect((await credentialSaved).status()).toBe(200);
  await expect(dialog.getByText(/Salt-okunur API erişimi · tanımlı$/)).toBeVisible();

  await dialog.getByLabel("Controller cihaz kimliği / seri numarası", { exact: true }).fill("Q2XX-TEST-E2E");
  const bound = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/devices/${controllerDeviceId}/controller-binding`) &&
    response.request().method() === "PUT",
  );
  await dialog.getByRole("button", { name: "Cihaz eşlemesini kaydet", exact: true }).click();
  expect((await bound).status()).toBe(200);
  await expect(dialog.getByRole("status")).toContainText("controller içindeki kimliği");
  await expect(dialog.locator('input[name="token"]')).toHaveValue("");
  await page.screenshot({
    path: join(evidenceDir, "s08-controller-desktop.png"),
    fullPage: false,
    animations: "disabled",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page, 390);
  const bounds = await dialog.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: join(evidenceDir, "s08-controller-mobile.png"),
    fullPage: false,
    animations: "disabled",
  });
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
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
