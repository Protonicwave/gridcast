import { expect, test } from "@playwright/test";

const MIN_PATH_LENGTH = 200;
const REGION_COUNT = 14;
const BAND_COUNT = 4;

test.beforeAll(() => {
  if (!process.env["SITE_URL"]) {
    throw new Error("SITE_URL must name the page to check, for example https://protonicwave.github.io/gridcast/");
  }
});

test("the live page draws London's answer and forecast chart", async ({ page }) => {
  await page.goto("./?region=13");

  // The loading state already has a heading, so the drawn series is what proves the forecast arrived.
  const series = page.locator("path.series");
  await expect(series).toBeAttached({ timeout: 30_000 });
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".answer__label")).toContainText("London");

  const seriesPath = await series.getAttribute("d");
  expect(seriesPath?.length ?? 0).toBeGreaterThan(MIN_PATH_LENGTH);

  await expect(page.locator(".map .region")).toHaveCount(REGION_COUNT);
});

test("the accuracy page shows NESO's error by horizon", async ({ page }) => {
  await page.goto("./#accuracy");

  await expect(page.getByRole("heading", { name: "How good is the forecast?" })).toBeVisible();
  const nesoRow = page.getByRole("row", { name: /^NESO/ });
  await expect(nesoRow).toBeVisible({ timeout: 30_000 });
  await expect(nesoRow.getByRole("cell")).toHaveCount(BAND_COUNT);
  await expect(page.getByRole("alert")).toHaveCount(0);
});
