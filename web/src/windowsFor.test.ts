import { expect, it } from "vitest";
import { type DurationHours, type DurationWindows, type Outlook, windowsFor } from "./forecastApi";

function windows(mean: number): DurationWindows {
  return { cleanest: { start: 0, meanGPerKwh: mean }, dirtiest: { start: 1, meanGPerKwh: mean + 10 }, timingMatters: true };
}

function outlookWith(entries: [DurationHours, DurationWindows][]): Outlook {
  return { regionId: 13, regionName: "London", fetchedAtMs: 0, firstSlotStartMs: 0, slotMs: 1_800_000, intensities: [1, 2, 3, 4], windows: new Map(entries) };
}

it("gives the chosen length when the forecast is long enough for it", () => {
  const outlook = outlookWith([[1, windows(10)], [2, windows(20)]]);
  expect(windowsFor(outlook, 1)).toEqual([1, windows(10)]);
});

it("gives the longest length that fits when the chosen one does not", () => {
  const outlook = outlookWith([[1, windows(10)], [2, windows(20)]]);
  expect(windowsFor(outlook, 4)).toEqual([2, windows(20)]);
});

it("rejects an outlook with no windows, naming what was expected", () => {
  expect(() => windowsFor(outlookWith([]), 3)).toThrow("expected an outlook with at least one duration's windows");
});
