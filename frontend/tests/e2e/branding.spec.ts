import { expect, test } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

test.skip(!process.env.STOCC_QA, "Requires the isolated QA application.");

for (const [name, viewport] of [
  ["desktop", { width: 1280, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test(`brand assets, favicon and home navigation on ${name}`, async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (!["error", "warning"].includes(message.type())) return;
      if (
        message.location().url.endsWith("/api/v1/session/me") &&
        message.text().includes("401")
      )
        return;
      errors.push(message.text());
    });
    const evidence = join(tmpdir(), "stocc-netstudio-branding");
    await mkdir(evidence, { recursive: true });
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page).toHaveTitle("Stocc NetStudio");
    await expect(
      page.getByRole("heading", { name: "Yönetim oturumu" }),
    ).toBeVisible();
    await expect(
      page.getByRole("img", { name: "NetStudio", exact: true }),
    ).toBeVisible();
    await expect(page.locator("nextjs-portal")).toHaveCount(0);
    await expect(page.locator(".login-brand")).toHaveCSS(
      "background-color",
      "rgba(0, 0, 0, 0)",
    );

    for (const asset of ["netstudio-logo.png", "netstudio-emblem.png"]) {
      const response = await request.get(`/branding/${asset}`);
      expect(response.status()).toBe(200);
      expect(
        (await response.body()).equals(
          await readFile(join("public/branding", asset)),
        ),
      ).toBe(true);
    }
    const iconPath = await page
      .locator('link[rel="icon"]')
      .getAttribute("href");
    expect(iconPath).toBeTruthy();
    const icon = await request.get(iconPath!);
    expect(icon.status()).toBe(200);
    expect(icon.headers()["content-type"]).toContain("image/png");
    const bytes = await icon.body();
    expect([bytes.readUInt32BE(16), bytes.readUInt32BE(20)]).toEqual([64, 64]);
    const alpha = await page.evaluate(async (base64) => {
      const image = new Image();
      image.src = `data:image/png;base64,${base64}`;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 64;
      const context = canvas.getContext("2d")!;
      context.drawImage(image, 0, 0);
      const pixels = context.getImageData(0, 0, 64, 64).data;
      return {
        corner: pixels[3],
        visible: pixels.some((value, index) => index % 4 === 3 && value > 0),
      };
    }, bytes.toString("base64"));
    expect(alpha).toEqual({ corner: 0, visible: true });
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: join(evidence, `login-${name}.png`) });

    await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
    await page
      .getByLabel("Parola", { exact: true })
      .fill("test-only-password-1234");
    await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Ağ cihazları", exact: true }),
    ).toBeVisible();
    const brand = page.getByRole("link", {
      name: "NetStudio — Ağ cihazları",
      exact: true,
    });
    await expect(brand).toBeVisible();
    await expect(brand).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(page.locator(".topbar")).toHaveCSS(
      "background-color",
      "rgb(221, 225, 229)",
    );
    await expect(page.locator(".topbar")).toHaveCSS("color", "rgb(23, 26, 31)");
    await expect(
      page.getByRole("button", { name: "Çıkış", exact: true }),
    ).toHaveCSS("color", "rgb(23, 26, 31)");
    await expect(
      brand.locator(name === "mobile" ? ".brand-emblem" : ".brand-wordmark"),
    ).toBeVisible();
    await expect(
      brand.locator(name === "mobile" ? ".brand-wordmark" : ".brand-emblem"),
    ).toBeHidden();
    if (name === "mobile")
      await page.getByRole("button", { name: "Menü", exact: true }).click();

    const repositoryUrl = "https://github.com/KES-KING/stocc-netstudio";
    const repository = page.getByRole("link", {
      name: "NetStudio GitHub reposu (yeni sekmede açılır)",
      exact: true,
    });
    await expect(repository).toBeInViewport();
    await expect(repository).toHaveAttribute("href", repositoryUrl);
    await expect(repository).toHaveAttribute("target", "_blank");
    await expect(repository).toHaveAttribute("rel", "noopener noreferrer");
    await expect(repository).toHaveCSS("border-radius", "0px");
    const position = await repository.boundingBox();
    expect(position!.width).toBeGreaterThanOrEqual(44);
    expect(position!.height).toBeGreaterThanOrEqual(44);
    if (name === "desktop") {
      await page.evaluate(() => window.scrollTo(0, 600));
      expect((await repository.boundingBox())!.y).toBe(position!.y);
      expect(position!.y + position!.height).toBe(viewport.height - 20);
    }
    await repository.focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(repository).toBeFocused();
    await expect(repository).toHaveCSS("outline-style", "solid");
    await page.locator(".sidebar").screenshot({
      path: join(evidence, `github-sidebar-${name}.png`),
    });
    await page.locator(".sidebar-footer").screenshot({
      path: join(evidence, `github-footer-${name}.png`),
    });

    // Verify real link activation/new-tab isolation without depending on GitHub uptime.
    // Only the external destination is stubbed; the app still uses its real QA API.
    await page.context().route(repositoryUrl, (route) => route.fulfill({
      contentType: "text/plain",
      body: "Repository destination",
    }));
    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      page.keyboard.press("Enter"),
    ]);
    await popup.waitForURL(repositoryUrl);
    expect(await popup.evaluate(() => window.opener === null)).toBe(true);
    await popup.close();
    await page.context().unroute(repositoryUrl);

    await page.getByRole("link", { name: "İş geçmişi", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "İş geçmişi", exact: true }),
    ).toBeVisible();
    await brand.click();
    await expect(page).toHaveURL(
      new URL("/", process.env.PLAYWRIGHT_BASE_URL!).toString(),
    );
    await expect(
      page.getByRole("heading", { name: "Ağ cihazları", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(viewport.width);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: join(evidence, `header-${name}.png`) });
    await page.locator(".topbar").screenshot({
      path: join(evidence, `navbar-${name}.png`),
    });
    await page.getByRole("button", { name: "Çıkış", exact: true }).click();
    await expect(
      page.getByRole("img", { name: "NetStudio", exact: true }),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
}
