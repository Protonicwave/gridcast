import { expect, test } from "@playwright/test";

const MIN_PATH_LENGTH = 200;

test.beforeAll(() => {
  if (!process.env["SITE_URL"]) {
    throw new Error("SITE_URL must name the page to check, for example https://protonicwave.github.io/gridcast/");
  }
});

test("the live page draws London's answer and forecast chart", async ({ page }) => {
  await page.goto("./");

  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".answer__label")).toContainText("London");

  const seriesPath = await page.locator("path.series").getAttribute("d");
  expect(seriesPath?.length ?? 0).toBeGreaterThan(MIN_PATH_LENGTH);
});
