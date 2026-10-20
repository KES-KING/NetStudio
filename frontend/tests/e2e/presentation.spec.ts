import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { interfaceTokens, theme } from "../../lib/theme";

test.skip(!process.env.NETSTUDIO_QA, "Requires the isolated QA application.");
const evidence = join(tmpdir(), "netstudio-presentation");

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page
    .getByLabel("Parola", { exact: true })
    .fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "QA-Core-01", exact: true }),
  ).toBeVisible();
  await mkdir(evidence, { recursive: true });
}

async function expectNoPageOverflow(page: Page, width: number) {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(width);
}

test("white content, graphite navigation and stable ECharts across filtering", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  await login(page);
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await expect(page.locator("body")).toHaveCSS("font-size", "14px");
  await expect(page.locator(".sidebar")).toHaveCSS(
    "background-color",
    "rgb(39, 43, 48)",
  );
  await expect(page.locator(".sidebar [aria-current=page]")).toHaveCSS(
    "background-color",
    "rgb(66, 71, 77)",
  );
  const tokens = await page.locator("html").evaluate((element) => {
    const css = getComputedStyle(element);
    return Object.fromEntries(
      ["accent", "green", "tx", "ui-soft", "ui-radius"].map((key) => [
        key,
        css.getPropertyValue(`--${key}`).trim(),
      ]),
    );
  });
  expect(tokens).toEqual({
    accent: theme.accent,
    green: theme.green,
    tx: theme.tx,
    "ui-soft": interfaceTokens["ui-soft"],
    "ui-radius": "0px",
  });
  const surfaces = page.locator(
    ".chart-panel, .device-row-wrapper, button, input, select, .status",
  );
  expect(
    await surfaces.evaluateAll((elements) =>
      elements.every((element) => {
        const css = getComputedStyle(element);
        return (
          css.borderRadius === "0px" &&
          css.boxShadow === "none" &&
          css.backgroundImage === "none"
        );
      }),
    ),
  ).toBe(true);

  const charts = page.locator("[data-chart=echarts]");
  await expect(charts.first().locator("svg")).toBeVisible();
  const instance = await charts.first().getAttribute("_echarts_instance_");
  expect(instance).toBeTruthy();
  await expect(page.locator(".summary-grid .panel-heading h2")).toHaveText([
    "Cihaz erişilebilirliği",
    "Aktif port oranı",
    "Arayüz trafiği",
    "Kapasite kullanımı",
  ]);
  await expect(charts.first()).toHaveCSS("height", "170px");
  const chartBounds = await page.locator(".summary-grid").boundingBox();
  const listBounds = await page.locator(".inventory-list").boundingBox();
  expect(chartBounds!.y + chartBounds!.height).toBeLessThan(listBounds!.y);

  await page.getByLabel("Cihaz ara", { exact: true }).fill("QA-Core-01");
  await expect(page.locator(".device-row")).toHaveCount(1);
  await expect(page.locator(".refresh-info")).toContainText("1 cihaz");
  await expect(charts.first()).toHaveAttribute("_echarts_instance_", instance!);
  await page.getByLabel("Cihaz ara", { exact: true }).fill("");
  await expect(page.locator(".device-row")).not.toHaveCount(1);
  await page.getByRole("heading", { name: "Ağ cihazları", exact: true }).click();
  await page.screenshot({ path: join(evidence, "dashboard-desktop.png") });

  const sidebar = page.locator(".sidebar");
  const sidebarBefore = await sidebar.boundingBox();
  expect(sidebarBefore!.y).toBe(68);
  expect(sidebarBefore!.height).toBe(1024 - 68);
  await page.evaluate(() => window.scrollTo(0, 850));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  expect(await sidebar.boundingBox()).toEqual(sidebarBefore);
  await expect(page.locator(".sidebar-footer")).toBeInViewport();
  await page.screenshot({ path: join(evidence, "sidebar-scrolled-desktop.png") });
  await page.getByRole("button", { name: "Çıkış", exact: true }).click();
});

test("keyboard focus, form surfaces, escape dismissal and activity table", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  await page.getByLabel("Cihaz ara", { exact: true }).focus();
  await page.keyboard.press("Tab");
  const type = page.getByRole("combobox", { name: "Cihaz türü", exact: true });
  await expect(type).toBeFocused();
  await expect(type).toHaveCSS("outline-style", "solid");
  await expect(type).toHaveCSS("outline-width", "2px");
  await page.getByRole("button", { name: "Cihaz Ekle", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS("border-radius", "0px");
  await expect(dialog.getByLabel("Cihaz adı", { exact: true })).toHaveCSS(
    "font-weight",
    "400",
  );
  await dialog
    .getByRole("combobox", { name: "Kimlik doğrulama", exact: true })
    .selectOption("private_key");
  await expect(
    dialog.getByLabel("Özel anahtar", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: join(evidence, "device-form-desktop.png") });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Cihaz Ekle", exact: true }),
  ).toBeFocused();
  await page
    .getByRole("link", { name: "Denetim kayıtları", exact: true })
    .click();
  await expect(page.getByRole("table")).toBeVisible();
  await expectNoPageOverflow(page, 1280);
  await page.screenshot({ path: join(evidence, "audit-desktop.png") });
  await page.getByRole("button", { name: "Çıkış", exact: true }).click();
});

for (const width of [320, 768, 1024, 1920, 2560]) {
  test(`dashboard, detail and form remain usable at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await login(page);
    await expect(page.locator(".summary-grid .chart-loading")).toHaveCount(0);
    await expect(page.locator("[data-chart=echarts] svg").first()).toBeVisible();
    await expectNoPageOverflow(page, width);
    if (width >= 1700) {
      const main = await page.locator(".main-content").boundingBox();
      expect(main!.x).toBe(232);
      expect(main!.width).toBe(width - 232);
      await expect(page.locator(".main-content")).toHaveCSS("max-width", "none");
      await page.screenshot({ path: join(evidence, `dashboard-${width}.png`) });
    }
    await expect(page.locator(".echart").first()).toHaveCSS(
      "height",
      width <= 700 ? "180px" : width >= 1700 ? "200px" : "170px",
    );
    await page.getByRole("button", { name: "Cihaz Ekle", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    expect(
      await dialog.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
    ).toBe(true);
    await page.keyboard.press("Escape");
    await page.getByRole("link", { name: "QA-Core-01", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "IP topolojisi", exact: true }),
    ).toBeVisible();
    await expectNoPageOverflow(page, width);
    await page.screenshot({
      path: join(evidence, `detail-${width}.png`),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Çıkış", exact: true }).click();
  });
}
