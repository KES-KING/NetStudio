import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

test.skip(!process.env.NETSTUDIO_QA, "Only the isolated QA deployment may be changed.");

for (const width of [1536, 390]) {
  test(`Huawei collector and explicit device-only SSH profile at ${width}px`, async ({ page }) => {
    test.setTimeout(60_000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error" && !(message.text().includes("401") && message.location().url.endsWith("/session/me")))
        errors.push(message.text());
    });
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
    await page.goto("/");
    await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
    await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
    await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
    await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
    await expect(page.getByRole("heading", { name: "QA-Core-01", exact: true })).toBeVisible();
    const identifier = page.url().split("/").pop();
    const base = `/api/v1/devices/${identifier}`;
    const previous = await (await page.request.get(base)).json();
    const auth = await (await page.request.get("/api/v1/session/me")).json();
    const headers = { origin: process.env.PLAYWRIGHT_BASE_URL!, "x-csrf-token": auth.csrf_token };
    try {
      const compatibility = page.getByRole("region", { name: "Uyumluluk" });
      const profileEditor = compatibility.locator(".compatibility-profile-editor");
      if ((await profileEditor.getAttribute("open")) === null)
        await profileEditor.locator(":scope > summary").click();
      await profileEditor.locator('select[name="catalog_vendor"]').selectOption("Huawei");
      await profileEditor
        .locator('select[name="configured_profile_id"]')
        .selectOption("huawei_vrp_v200");
      await profileEditor.getByLabel(/Bu seçimin legacy sınıflandırmayı/).check();
      await profileEditor
        .getByRole("button", { name: "Kanonik profili kaydet", exact: true })
        .click();
      await expect(compatibility.getByRole("definition").filter({ hasText: /^Bağımsız yönetim$/ })).toBeVisible();
      const canonical = await (await page.request.get(base)).json();
      expect(canonical.collector).toBe("huawei_vrp");
      const standardProfile = await page.request.put(base + "/connection-settings", {
        headers, data: {
          collector: canonical.collector,
          configured_profile_id: canonical.configured_profile_id,
          management_mode: canonical.management_mode,
          ssh_profile: "standard",
        },
      });
      expect(standardProfile.ok()).toBeTruthy();
      await page.reload();

      await page.getByRole("button", { name: "Bağlantı bilgileri", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.getByLabel("SSH uyumluluk profili")).toHaveValue("standard");
      await expect(dialog.getByRole("option", { name: "Eski VRP", exact: true })).toHaveAttribute("value", "huawei_legacy");
      await dialog.getByLabel("SSH uyumluluk profili").selectOption("huawei_legacy");
      const confirmation = dialog.getByRole("checkbox", { name: "Bu cihaz için eski SSH algoritmalarının kullanımını onaylıyorum." });
      await expect(confirmation).toBeVisible();
      await expect(dialog).toContainText("cihaz başına .env izni gerekmez");
      await expect(dialog).toContainText("Host anahtarı doğrulaması korunur");
      await dialog.getByRole("button", { name: "SSH güvenlik profilini kaydet", exact: true }).click();
      await expect(confirmation).toBeFocused();
      expect((await (await page.request.get(base)).json()).ssh_profile).toBe("standard");
      await confirmation.check();
      await dialog.getByRole("button", { name: "SSH güvenlik profilini kaydet", exact: true }).focus();
      const evidence = join(tmpdir(), "netstudio-huawei");
      await mkdir(evidence, { recursive: true });
      await page.screenshot({ path: join(evidence, `connection-settings-${width}.png`) });
      await dialog.getByRole("button", { name: "SSH güvenlik profilini kaydet", exact: true }).click();
      await expect(dialog.getByRole("status")).toContainText("SSH güvenlik profili kaydedildi");
      await dialog.getByRole("button", { name: "Kapat", exact: true }).click();
      await page.reload();
      await expect(page.getByRole("button", { name: "Veri topla", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Bağlantıyı test et", exact: true }).click();
      await expect(page.getByRole("status").filter({ hasText: /^İş:/ })).toContainText("İş: Tamamlandı", { timeout: 20000 });
      const updated = await (await page.request.get(base)).json();
      expect(updated.collector).toBe("huawei_vrp");
      expect(updated.ssh_profile).toBe("huawei_legacy");
      expect(updated.physical_ports).toEqual(previous.physical_ports);
      expect(updated.host_key_fingerprint).toBe(previous.host_key_fingerprint);

      const refreshedEditor = compatibility.locator(".compatibility-profile-editor");
      if ((await refreshedEditor.getAttribute("open")) === null)
        await refreshedEditor.locator(":scope > summary").click();
      await refreshedEditor.locator('select[name="catalog_vendor"]').selectOption("Cisco");
      await refreshedEditor
        .locator('select[name="configured_profile_id"]')
        .selectOption("cisco_ios");
      await refreshedEditor.getByLabel(/Bu seçimin legacy sınıflandırmayı/).check();
      await refreshedEditor
        .getByRole("button", { name: "Kanonik profili kaydet", exact: true })
        .click();
      await expect.poll(async () => (await (await page.request.get(base)).json()).collector)
        .toBe("cisco_ios");
      await expect(page.getByRole("button", { name: "Veri topla", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      expect(errors).toEqual([]);
    } finally {
      const restored = await page.request.put(base + "/connection-settings", {
        headers, data: {
          collector: previous.collector,
          configured_profile_id: previous.configured_profile_id,
          management_mode: previous.management_mode,
          ssh_profile: previous.ssh_profile,
          legacy_ssh_confirmed: true,
        },
      });
      expect(restored.ok()).toBeTruthy();
    }
  });
}
