import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

test.skip(!process.env.STOCC_QA, "Requires the isolated QA application.");

test("automatic key discovery, explicit trust and polling settings on desktop and mobile", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.setViewportSize({ width: 1536, height: 1024 });
  await page.goto("/");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
  await expect(page.getByRole("region", { name: "Otomatik veri toplama" })).toBeVisible();
  await page.getByRole("button", { name: "Bağlantı bilgileri", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Anahtarı bul ve bağlantıyı hazırla" }).click();
  await expect(dialog.getByText(/^Bulunan: SHA256:/)).toBeVisible({ timeout: 20000 });
  const found = (await dialog.getByText(/^Bulunan: SHA256:/).innerText()).replace("Bulunan: ", "");
  const trustedLab = await (await page.request.get(process.env.STOCC_QA_SSH_KEY_URL ?? "http://127.0.0.1:12223")).json();
  expect(found).toBe(trustedLab.fingerprint);
  await expect(dialog.getByText(/^Önceki: SHA256:/)).toBeVisible();
  const checkbox = dialog.getByRole("checkbox", { name: /Fingerprint’i güvenilir kaynaktan doğruladım/ });
  await dialog.getByRole("button", { name: "Anahtarı onayla", exact: true }).click();
  await expect(checkbox).toBeFocused();
  await checkbox.check();
  const evidence = join(tmpdir(), "stocc-netstudio-automation");
  await mkdir(evidence, { recursive: true });
  await page.screenshot({ path: join(evidence, "key-approval-desktop.png"), fullPage: true });
  await dialog.getByRole("button", { name: "Anahtarı onayla", exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText("Host anahtarı onaylandı");
  await dialog.getByRole("button", { name: "Kapat", exact: true }).click();
  await page.getByRole("button", { name: "Bağlantıyı test et", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("İş: Tamamlandı", { timeout: 20000 });
  await page.getByText("Toplama politikasını düzenle", { exact: true }).click();
  await expect(page.getByLabel("Portlar ve trafik (saniye)")).toBeVisible();
  await page.getByLabel("Portlar ve trafik (saniye)").fill("45");
  await Promise.all([page.waitForResponse(r => r.url().endsWith("/polling") && r.request().method() === "PUT"),
    page.getByRole("button", { name: "Toplama ayarlarını kaydet" }).click()]);
  await expect(page.getByRole("button", { name: "Toplama ayarlarını kaydet" })).toBeEnabled();
  await expect(page.getByLabel("Portlar ve trafik (saniye)")).toHaveValue("45");
  await page.getByLabel("Portlar ve trafik (saniye)").fill("30");
  await Promise.all([page.waitForResponse(r => r.url().endsWith("/polling") && r.request().method() === "PUT"),
    page.getByRole("button", { name: "Toplama ayarlarını kaydet" }).click()]);
  await expect(page.getByRole("button", { name: "Toplama ayarlarını kaydet" })).toBeEnabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Bağlantı bilgileri", exact: true }).click();
  await dialog.getByLabel("SSH uyumluluk profili").selectOption("advanced");
  await expect(dialog.getByRole("listbox", { name: "Anahtar değişimi", exact: true })).toBeVisible();
  await expect(dialog.getByLabel("Bu cihazda eski SSH algoritmalarına izin ver")).not.toBeChecked();
  await dialog.getByText(/İsteğe bağlı SNMPv3/).click();
  await expect(dialog.getByRole("combobox", { name: "Kimlik doğrulama algoritması", exact: true })).toHaveValue("sha256");
  await expect(dialog.getByLabel("SNMP doğrulama parolası")).toHaveValue("");
  await dialog.getByLabel("SNMP doğrulama parolası").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(evidence, "connection-mobile.png"), fullPage: false });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await dialog.getByRole("button", { name: "Kapat", exact: true }).click();
  expect(errors).toEqual([]);
});

test("independent worker continues scheduled reads after the browser is closed", async ({ page, request }) => {
  test.setTimeout(90000);
  const origin = process.env.PLAYWRIGHT_BASE_URL!;
  expect(new URL(origin).hostname).toBe("127.0.0.1");
  await page.goto("/");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ağ cihazları", exact: true })).toBeVisible();
  const session = await (await page.request.get("/api/v1/session/me")).json();
  const headers = { origin, "x-csrf-token": session.csrf_token };
  const devices = await (await page.request.get("/api/v1/devices")).json();
  const lab = devices.find((device: { name: string; site: string }) =>
    device.name === "QA-Core-01" && device.site === "TEST FIXTURE / isolated");
  expect(lab).toBeTruthy();
  const created = await page.request.post("/api/v1/devices", { headers, data: {
    name: `QA-Auto-${Date.now()}`, site: lab.site, management_address: lab.management_address,
    ssh_port: lab.ssh_port, collector: "linux_ssh", ssh_profile: "auto",
    credentials: { username: "lab", password: "lab-secret" },
  } });
  expect(created.status()).toBe(201);
  const device = await created.json(), base = `/api/v1/devices/${device.id}`;
  const keyUrl = process.env.STOCC_QA_SSH_KEY_URL ?? "http://127.0.0.1:12223";
  expect(new URL(keyUrl).hostname).toBe("127.0.0.1");
  const knownKey = await (await page.request.get(keyUrl)).json();
  expect((await page.request.put(base + "/host-key", { headers, data: knownKey })).status()).toBe(200);
  await page.getByRole("button", { name: "Çıkış", exact: true }).click();
  const closedAt = Date.now();
  await page.close();
  // This second API-only session observes the worker; it never submits a poll.
  const auth = await request.post("/api/v1/session/login", { headers: { origin },
    data: { username: "qa-admin", password: "test-only-password-1234" } });
  expect(auth.status()).toBe(200);
  const observerHeaders = { origin, "x-csrf-token": (await auth.json()).csrf_token };
  try {
    await expect.poll(async () => {
      const response = await request.get(base + "/observations/latest");
      if (!response.ok()) return false;
      const latest = await response.json();
      return latest?.groups?.fast?.quality === "ok" &&
        Date.parse(latest.groups.fast.observed_at) > closedAt + 1000;
    }, { timeout: 65000, intervals: [1000, 2000] }).toBe(true);
    const jobs = await (await request.get("/api/v1/jobs")).json();
    expect(jobs.some((job: { device_id: string; requested_by: string; status: string }) =>
      job.device_id === device.id && job.requested_by === "system:collector" && job.status === "succeeded")).toBe(true);
  } finally {
    // Stop only this test's automatic reads; retain the isolated evidence.
    const policy = await (await request.get(base + "/polling")).json();
    expect((await request.put(base + "/polling", { headers: observerHeaders,
      data: { ...policy.settings, enabled: false } })).status()).toBe(200);
    await request.post("/api/v1/session/logout", { headers: observerHeaders });
  }
});
