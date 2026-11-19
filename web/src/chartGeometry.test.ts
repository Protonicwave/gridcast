import { expect, it } from "vitest";
import { chartScales, hourTicks, niceCeiling, rampColour, stepPath, valueTicks } from "./chartGeometry";

const HALF_HOUR_MS = 1_800_000;

it.each([
  [0, 100],
  [40, 100],
  [100, 100],
  [101, 150],
  [212, 250],
  [250, 250],
])("rounds a highest value of %i up to an axis top of %i", (max, top) => {
  expect(niceCeiling(max)).toBe(top);
});

it("labels the value axis every 50 g up to 200, and every 100 g above", () => {
  expect(valueTicks(150)).toEqual([0, 50, 100, 150]);
  expect(valueTicks(200)).toEqual([0, 50, 100, 150, 200]);
  expect(valueTicks(350)).toEqual([0, 100, 200, 300]);
});

it("draws one flat step per half hour", () => {
  const x = (slot: number) => slot * 10;
  const y = (value: number) => 100 - value;
  expect(stepPath([20, 50, 50], x, y)).toBe("M0.0 80.0H10.0V50.0H20.0V50.0H30.0");
});

it("draws a single half hour as one step", () => {
  expect(stepPath([10], (slot) => slot * 4, (value) => value)).toBe("M0.0 10.0H4.0");
});

it("scales slots across the plot and values from its bottom to its top", () => {
  const scales = chartScales(636, 96, 212);
  expect(scales.width).toBe(636);
  expect(scales.height).toBe(260);
  expect(scales.top).toBe(250);
  expect(scales.x(0)).toBe(scales.margin.left);
  expect(scales.x(96)).toBe(636 - scales.margin.right);
  expect(scales.y(0)).toBe(scales.plotBottom);
  expect(scales.y(250)).toBe(scales.margin.top);
});

it("makes the chart shorter on a narrow screen and never narrower than 280 px", () => {
  expect(chartScales(343, 96, 100).height).toBe(220);
  expect(chartScales(0, 96, 100).width).toBe(280);
});

it("finds the half hour under a point, clamped to the series", () => {
  const scales = chartScales(636, 96, 212);
  expect(scales.slotAt(scales.x(10.5))).toBe(10);
  expect(scales.slotAt(0)).toBe(0);
  expect(scales.slotAt(10_000)).toBe(95);
});

it("ticks every six UK hours and names the day at midnight", () => {
  const ticks = hourTicks(Date.parse("2026-11-19T15:00Z"), 24, HALF_HOUR_MS);
  expect(ticks).toEqual([
    { slot: 6, label: "18", isDayStart: false },
    { slot: 18, label: "Fri", isDayStart: true },
  ]);
});

it("keeps hour ticks on UK hours across the October clock change", () => {
  // 23:00 BST on Saturday 24 October; the 25th has 25 hours.
  const ticks = hourTicks(Date.parse("2026-10-24T22:00Z"), 48, HALF_HOUR_MS);
  expect(ticks).toEqual([
    { slot: 2, label: "Sun", isDayStart: true },
    { slot: 16, label: "06", isDayStart: false },
    { slot: 28, label: "12", isDayStart: false },
    { slot: 40, label: "18", isDayStart: false },
  ]);
});

it("leaves the first and last edges unlabelled", () => {
  // 00:00 to 06:00 UK time, both on tick hours.
  expect(hourTicks(Date.parse("2026-11-20T00:00Z"), 12, HALF_HOUR_MS)).toEqual([]);
});

it.each([
  [0, "oklch(0.950 0.045 165.0)"],
  [-20, "oklch(0.950 0.045 165.0)"],
  [125, "oklch(0.710 0.105 110.0)"],
  [300, "oklch(0.360 0.080 35.0)"],
  [900, "oklch(0.360 0.080 35.0)"],
])("colours %i g per kWh as %s", (value, colour) => {
  expect(rampColour(value)).toBe(colour);
});
