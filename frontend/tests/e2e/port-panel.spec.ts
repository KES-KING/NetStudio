import { expect, test } from "@playwright/test";

test("opens an accessible port detail from the fixture panel", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Stocc NetStudio")).toBeVisible();
  await expect(page.getByText("28 PORT")).toBeVisible();
  await page.getByRole("button", { name: "Gi0/1, up" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("GigabitEthernet0/1");
  await expect(page.getByRole("dialog")).toContainText("kaynak: fixture");
  await expect(page.getByRole("button", { name: "Değişiklik planı" })).toBeDisabled();
});

