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

async function expectVisibleControlsInsideViewport(page: Page, width: number) {
  const escaped = await page.locator([
    ".toolbar-actions button",
    ".page-heading .button-link",
    ".management-toolbar button",
    ".form-actions button",
    ".small-actions button",
    ".settings-tabs a",
    ".topology-commandbar > button",
    ".device-topology-camera button",
    ".pagination button",
    ".row-actions button",
    ".panel-heading > button",
    ".panel-heading > .button-link",
  ].join(", ")).evaluateAll(
    (elements, viewportWidth) => elements
      .filter((element) => {
        const style = getComputedStyle(element);
        return !element.closest(".table-scroll, .chassis-scroll, .topology-stage") &&
          style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
      })
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return { text: element.textContent?.trim().slice(0, 60), left: rect.left, right: rect.right };
      })
      .filter((rect) => rect.left < -0.5 || rect.right > Number(viewportWidth) + 0.5),
    width,
  );
  expect(escaped).toEqual([]);
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
  await dialog.locator('select[name="catalog_vendor"]').selectOption("Huawei");
  await dialog
    .locator('select[name="configured_profile_id"]')
    .selectOption("huawei_vrp_v200");
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

test("primary pages keep action groups and tabs inside narrow viewports", async ({ page }) => {
  await page.setViewportSize({ width: 1536, height: 900 });
  await login(page);
  const routes = [
    { path: "/", ready: ".inventory-list" },
    { path: "/topology", ready: "h1" },
    { path: "/jobs", ready: "h1" },
    { path: "/audit", ready: "h1" },
    { path: "/settings", ready: "h1" },
    { path: "/settings/users", ready: "h1" },
    { path: "/settings/network-probes", ready: "h1" },
    { path: "/settings/updates", ready: "h1" },
  ];
  for (const width of [320, 768, 1536]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of routes) {
      await page.goto(route.path);
      await expect(page.locator(route.ready).first()).toBeVisible();
      await expectNoPageOverflow(page, width);
      await expectVisibleControlsInsideViewport(page, width);
    }
  }
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
      const layout = await page.locator(".console-layout").boundingBox();
      expect(main!.x).toBe(232);
      expect(main!.width).toBe(layout!.width - 232);
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
