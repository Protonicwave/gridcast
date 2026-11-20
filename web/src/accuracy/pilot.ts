/** The 2025 pilot's figures for NESO's national forecast, from data/pilot_national_2025.json, to three decimal places. */
export const PILOT = {
  halfHours: 17477,
  maeGPerKwh: 9.282,
  intervalGPerKwh: { low: 8.941, high: 9.694 },
  p95AbsoluteErrorG: 26,
  /** Mean absolute error by hour of the UTC day, 00:00 first. */
  maeByHourUtc: [6.383, 6.186, 6.176, 6.152, 9.047, 11.449, 11.38, 10.33, 10.497, 9.815, 8.082, 7.081, 5.766, 6.223, 8.777, 12.733, 12.84, 9.555, 8.141, 8.597, 10.166, 13.504, 13.412, 10.433],
  windowHours: 3,
  regretThreshold: 0.1,
  /** Share of days on which the forecast's cleanest window came within the threshold of the day's actual best. */
  shareWithinThreshold: 0.92,
  shareExactBest: 0.26,
} as const;
