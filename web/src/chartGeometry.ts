/** Geometry and colour for the 48-hour chart, kept apart from React so it can be tested directly. */

import { isOnTheHour, localHour, shortWeekday } from "./time";

const MIN_WIDTH_PX = 280;
const NARROW_WIDTH_PX = 520;
const HEIGHT_PX = 260;
const NARROW_HEIGHT_PX = 220;
const MARGIN = { left: 36, right: 6, top: 30, bottom: 44 } as const;
const MIN_AXIS_TOP_G_PER_KWH = 100;
const AXIS_STEP_G_PER_KWH = 50;
const HOURS_BETWEEN_TICKS = 6;
const RAMP_MAX_G_PER_KWH = 300;

/** Value, lightness, chroma and hue. Lightness falls steadily, so the order survives colour blindness. */
const RAMP_STOPS = [
  [0, 0.95, 0.045, 165],
  [50, 0.86, 0.08, 150],
  [100, 0.76, 0.1, 125],
  [150, 0.66, 0.11, 95],
  [200, 0.56, 0.11, 70],
  [250, 0.46, 0.1, 50],
  [300, 0.36, 0.08, 35],
] as const;

export interface ChartScales {
  readonly width: number;
  readonly height: number;
  readonly margin: typeof MARGIN;
  readonly plotBottom: number;
  /** The value at the top of the axis, in g per kWh. */
  readonly top: number;
  readonly x: (slot: number) => number;
  readonly y: (value: number) => number;
  /** The half hour under a horizontal position in chart units, clamped to the series. */
  readonly slotAt: (px: number) => number;
}

export interface HourTick {
  readonly slot: number;
  readonly label: string;
  readonly isDayStart: boolean;
}

export function niceCeiling(max: number): number {
  return Math.max(MIN_AXIS_TOP_G_PER_KWH, Math.ceil(max / AXIS_STEP_G_PER_KWH) * AXIS_STEP_G_PER_KWH);
}

export function valueTicks(top: number): number[] {
  const step = top > 200 ? 100 : 50;
  return Array.from({ length: Math.floor(top / step) + 1 }, (_, i) => i * step);
}

export function chartScales(availableWidthPx: number, slotCount: number, maxValue: number): ChartScales {
  const width = Math.max(availableWidthPx, MIN_WIDTH_PX);
  const height = width < NARROW_WIDTH_PX ? NARROW_HEIGHT_PX : HEIGHT_PX;
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotBottom = height - MARGIN.bottom;
  const top = niceCeiling(maxValue);
  return {
    width,
    height,
    margin: MARGIN,
    plotBottom,
    top,
    x: (slot) => MARGIN.left + (slot / slotCount) * plotWidth,
    y: (value) => MARGIN.top + (1 - value / top) * (plotBottom - MARGIN.top),
    slotAt: (px) => Math.min(Math.max(Math.floor(((px - MARGIN.left) / plotWidth) * slotCount), 0), slotCount - 1),
  };
}

/** Step line through half-hourly values, one flat segment per slot. */
export function stepPath(values: readonly number[], x: (slot: number) => number, y: (value: number) => number): string {
  return values
    .map((value, i) => `${i === 0 ? `M${x(0).toFixed(1)} ` : "V"}${y(value).toFixed(1)}H${x(i + 1).toFixed(1)}`)
    .join("");
}

/** Every sixth UK hour inside the series, with the weekday in place of midnight. */
export function hourTicks(firstSlotStartMs: number, slotCount: number, slotMs: number): HourTick[] {
  const ticks: HourTick[] = [];
  for (let slot = 1; slot < slotCount; slot += 1) {
    const ms = firstSlotStartMs + slot * slotMs;
    const hour = localHour(ms);
    if (!isOnTheHour(ms) || hour % HOURS_BETWEEN_TICKS !== 0) continue;
    const isDayStart = hour === 0;
    ticks.push({ slot, label: isDayStart ? shortWeekday(ms) : String(hour).padStart(2, "0"), isDayStart });
  }
  return ticks;
}

export function rampColour(value: number): string {
  const clamped = Math.min(Math.max(value, 0), RAMP_MAX_G_PER_KWH);
  const upperIndex = Math.max(RAMP_STOPS.findIndex(([stop]) => clamped <= stop), 1);
  // Both indices lie inside RAMP_STOPS: the clamp keeps the value within the first and last stops.
  const [lowValue, lowL, lowC, lowH] = RAMP_STOPS[upperIndex - 1] ?? RAMP_STOPS[0];
  const [highValue, highL, highC, highH] = RAMP_STOPS[upperIndex] ?? RAMP_STOPS[0];
  const t = (clamped - lowValue) / (highValue - lowValue);
  const mix = (a: number, b: number) => a + (b - a) * t;
  return `oklch(${mix(lowL, highL).toFixed(3)} ${mix(lowC, highC).toFixed(3)} ${mix(lowH, highH).toFixed(1)})`;
}
