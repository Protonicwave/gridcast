import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import { PILOT } from "./pilot";

interface PilotFile {
  readonly errors: { readonly n: number; readonly mae: number; readonly mae_ci95_low: number; readonly mae_ci95_high: number; readonly p95_absolute_error: number };
  readonly mae_by_hour_utc: Readonly<Record<string, number>>;
  readonly window_pilot: { readonly window_hours: number; readonly regret_threshold: number; readonly share_regret_at_most_threshold: number; readonly share_windows_coincide: number };
}

const file = JSON.parse(readFileSync(resolve(process.cwd(), "../data/pilot_national_2025.json"), "utf8")) as PilotFile;
const THREE_DECIMALS = 3;
const TWO_DECIMALS = 2;

it("states the pilot's error figures as the data file records them", () => {
  expect(PILOT.halfHours).toBe(file.errors.n);
  expect(PILOT.maeGPerKwh).toBeCloseTo(file.errors.mae, THREE_DECIMALS - 1);
  expect(PILOT.intervalGPerKwh.low).toBeCloseTo(file.errors.mae_ci95_low, THREE_DECIMALS - 1);
  expect(PILOT.intervalGPerKwh.high).toBeCloseTo(file.errors.mae_ci95_high, THREE_DECIMALS - 1);
  expect(PILOT.p95AbsoluteErrorG).toBe(file.errors.p95_absolute_error);
});

it("states the error for each hour of the day as the data file records it", () => {
  const fromFile = Array.from({ length: 24 }, (_, hour) => file.mae_by_hour_utc[String(hour)]);
  expect(PILOT.maeByHourUtc).toHaveLength(24);
  PILOT.maeByHourUtc.forEach((value, hour) => {
    expect(value).toBeCloseTo(fromFile[hour] ?? Number.NaN, THREE_DECIMALS - 1);
  });
});

it("states the window pilot's shares as the data file records them", () => {
  expect(PILOT.windowHours).toBe(file.window_pilot.window_hours);
  expect(PILOT.regretThreshold).toBe(file.window_pilot.regret_threshold);
  expect(PILOT.shareWithinThreshold).toBeCloseTo(file.window_pilot.share_regret_at_most_threshold, TWO_DECIMALS);
  expect(PILOT.shareExactBest).toBeCloseTo(file.window_pilot.share_windows_coincide, TWO_DECIMALS);
});
